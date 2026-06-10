"""Standalone TargetWS server backed by a REAL LIBERO simulation.

Runs in the `liberopi` conda env (cloned from `libero`, py3.8) which has
libero + robosuite + mujoco. Deliberately self-contained: it does NOT import
the PhyAgentOS package (that would pull pydantic / py3.10+ syntax into py3.8).
It speaks the TargetWS msgpack-over-websocket wire format, so the runtime side
(`LiberoRemoteTargetProxy` + `LiberoTargetAdapter`, in the `paos` env) talks to
it transparently.

Launch (liberopi env):

  MUJOCO_GL=egl PYTHONWARNINGS=ignore \
  conda run -n liberopi python PhyAgentOS/runtime/targets/remote/libero/server.py \
    --host 0.0.0.0 --port 9002 \
    --benchmark-name libero_spatial --task-id 0 --init-state-id 0 \
    --camera-height 256 --camera-width 256 --max-steps 300 --num-steps-wait 10
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import traceback
from typing import Any, Dict

import numpy as np

try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None

# --- msgpack wire codec (kept byte-compatible with PhyAgentOS msgpack_codec) ---
import msgpack

RPC_VERSION = "phyagentos.runtime_rpc.v2"

# LIBERO dummy action keeps the gripper open while the scene settles.
LIBERO_DUMMY_ACTION = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0]


def _pack_array(obj: Any) -> Any:
    if isinstance(obj, (np.ndarray, np.generic)) and obj.dtype.kind in ("V", "O", "c"):
        raise ValueError("Unsupported dtype: %s" % obj.dtype)
    if isinstance(obj, np.ndarray):
        return {
            "__ndarray__": True,
            "data": obj.tobytes(),
            "dtype": obj.dtype.str,
            "shape": obj.shape,
        }
    if isinstance(obj, np.generic):
        return {"__npgeneric__": True, "data": obj.item(), "dtype": obj.dtype.str}
    return obj


def _unpack_array(obj: Dict[Any, Any]) -> Any:
    if obj.get("__ndarray__"):
        return np.ndarray(buffer=obj["data"], dtype=np.dtype(obj["dtype"]), shape=obj["shape"])
    if obj.get("__npgeneric__"):
        return np.dtype(obj["dtype"]).type(obj["data"])
    return obj


def packb(payload: Any) -> bytes:
    return msgpack.packb(payload, use_bin_type=True, default=_pack_array)


def unpackb(data: bytes) -> Any:
    return msgpack.unpackb(data, raw=False, object_hook=_unpack_array)


def make_response(request: Dict[str, Any], response_type: str, payload: Dict[str, Any]) -> bytes:
    return packb(
        {
            "version": RPC_VERSION,
            "type": response_type,
            "session_id": request.get("session_id"),
            "target_id": request.get("target_id"),
            "skillruntime_id": request.get("skillruntime_id"),
            "episode_id": request.get("episode_id"),
            "seq": int(request.get("seq", 0)),
            "timestamp_ns": time.time_ns(),
            "trace_id": request.get("trace_id"),
            "payload": payload,
        }
    )


class TargetProtocolError(Exception):
    pass


# --- real LIBERO runtime ------------------------------------------------------

LIBERO_DEFAULT_CONFIG = {
    "benchmark_name": "libero_spatial",
    "task_id": 0,
    "init_state_id": 0,
    "camera_height": 256,
    "camera_width": 256,
    "max_chunk_size": 50,
    "max_steps": 300,
    "num_steps_wait": 10,
    "record_dir": None,
    "record_fps": 20,
}


class LiberoRealRuntime:
    """Real LIBERO benchmark target runtime (one session == one episode)."""

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = dict(LIBERO_DEFAULT_CONFIG)
        self.config.update(config or {})
        self.session_id = None
        self.env = None
        self._env_key = None
        self.suite = None
        self.task = None
        self.init_states = None
        self.language = "LIBERO task"
        self.step_idx = 0
        self.success = False
        self.done = False
        self._total_reward = 0.0
        self._episode_chunks = []
        self._last_obs = None
        self._frames = []
        self._episode_idx = 0
        self._last_video_path = None
        self._last_status = {"accepted": True, "safety_status": "idle", "executed_steps": 0}

    # -- lifecycle --
    def _ensure_env(self):
        from libero.libero import benchmark, get_libero_path
        from libero.libero.envs import OffScreenRenderEnv
        import os

        bn = str(self.config["benchmark_name"])
        tid = int(self.config["task_id"])
        key = (bn, tid, int(self.config["camera_height"]), int(self.config["camera_width"]))
        if self.env is not None and self._env_key == key:
            return
        suite = benchmark.get_benchmark_dict()[bn]()
        task = suite.get_task(tid)
        bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
        if self.env is not None:
            try:
                self.env.close()
            except Exception:
                pass
        self.env = OffScreenRenderEnv(
            bddl_file_name=bddl,
            camera_heights=int(self.config["camera_height"]),
            camera_widths=int(self.config["camera_width"]),
        )
        self.suite = suite
        self.task = task
        self.init_states = suite.get_task_init_states(tid)
        self.language = str(getattr(task, "language", task.name))
        self._env_key = key

    def describe(self) -> Dict[str, Any]:
        self._ensure_env()
        return {
            "runtime": "LiberoRealRemoteTargetRuntime",
            "benchmark_name": self.config["benchmark_name"],
            "task_id": int(self.config["task_id"]),
            "task_description": self.language,
            "num_tasks": len(self._task_list()),
            "task_list": self._task_list(),
            "observation_schema": {
                "agentview_image": {"dtype": "uint8", "layout": "HWC"},
                "robot0_eye_in_hand_image": {"dtype": "uint8", "layout": "HWC"},
                "robot0_eef_pos": {"dtype": "float32", "shape": [3]},
                "robot0_eef_quat": {"dtype": "float32", "shape": [4]},
                "robot0_gripper_qpos": {"dtype": "float32", "shape": [2]},
            },
            "action_contract": {
                "id": "libero_delta_eef_gripper_v1",
                "shape": ["T", 7],
                "dtype": "float32",
                "normalized": False,
                "frame": "base",
                "max_chunk_size": int(self.config["max_chunk_size"]),
            },
        }

    def configure_session(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        self.session_id = ctx.get("session_id", self.session_id)
        self.config.update(ctx.get("libero", {}))
        return {"configured": True, "session_id": self.session_id, "libero": self._libero_metadata()}

    def start_session(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        self.session_id = ctx.get("session_id", self.session_id)
        return {"started": True, "session_id": self.session_id, "libero": self._libero_metadata()}

    def reset(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        self.session_id = ctx.get("session_id", self.session_id)
        self.config.update(ctx.get("libero", {}))
        self._ensure_env()
        self.env.reset()
        isid = int(self.config.get("init_state_id", 0))
        obs = self.env.set_init_state(self.init_states[isid])
        for _ in range(int(self.config.get("num_steps_wait", 10))):
            obs, _, _, _ = self.env.step(LIBERO_DUMMY_ACTION)
        # pi05 emits relative/delta end-effector actions; match the official
        # LiberoEnv which sets the OSC controller to delta mode after settling.
        for robot in self.env.robots:
            robot.controller.use_delta = True
        self.step_idx = 0
        self.success = False
        self.done = False
        self._total_reward = 0.0
        self._episode_chunks = []
        self._frames = []
        self._last_video_path = None
        self._record_frame(obs)
        self._last_obs = self._format_obs(obs)
        self._last_status = {
            "accepted": True,
            "safety_status": "ok",
            "executed_steps": 0,
            "target_step_index": 0,
            "success": False,
            "done": False,
            "reward": 0.0,
            "obs": self._last_obs,
        }
        return self._last_obs

    def observe(self, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if self._last_obs is None:
            raise TargetProtocolError("LIBERO observe before reset")
        return self._last_obs

    def action_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        actions = np.asarray(chunk.get("actions"), dtype=np.float32)
        if actions.ndim != 2 or actions.shape[1] != 7:
            raise TargetProtocolError("LIBERO expected actions [T,7], got %s" % (actions.shape,))
        if actions.shape[0] > int(self.config["max_chunk_size"]):
            raise TargetProtocolError("LIBERO action chunk too large: %d" % actions.shape[0])
        if not np.isfinite(actions).all():
            raise TargetProtocolError("LIBERO actions contain NaN or Inf")

        max_steps = int(self.config.get("max_steps", 300))
        chunk_reward = 0.0
        first_step = self.step_idx + 1
        obs = self._raw_obs
        for action in actions:
            obs, reward, done, _info = self.env.step(action.tolist())
            self.step_idx += 1
            chunk_reward += float(reward)
            self._record_frame(obs)
            if bool(done):
                self.success = True
                self.done = True
            if self.done or self.step_idx >= max_steps:
                break
        self._total_reward += chunk_reward
        self.done = self.done or self.step_idx >= max_steps
        self._last_obs = self._format_obs(obs)
        if self.done:
            self._last_video_path = self._write_video()
        executed = max(0, self.step_idx - first_step + 1)
        self._episode_chunks.append(
            {
                "chunk_id": chunk.get("chunk_id", "libero_chunk"),
                "first_step": first_step,
                "executed_steps": executed,
                "requested_steps": int(actions.shape[0]),
                "reward": chunk_reward,
                "success": bool(self.success),
                "done": bool(self.done),
                "action_shape": [int(actions.shape[0]), int(actions.shape[1])],
            }
        )
        self._last_status = {
            "chunk_id": chunk.get("chunk_id", "libero_chunk"),
            "accepted": True,
            "buffered_steps": 0,
            "executed_steps": self.step_idx,
            "target_step_index": self.step_idx,
            "need_replan": not self.success,
            "safety_status": "ok",
            "success": bool(self.success),
            "done": bool(self.done),
            "reward": chunk_reward,
            "obs": self._last_obs,
            "libero": self._libero_metadata(),
            "episode_summary": self._episode_summary(),
        }
        return dict(self._last_status)

    def execution_status(self) -> Dict[str, Any]:
        return dict(self._last_status)

    def cancel(self, reason: str) -> Dict[str, Any]:
        self._last_status = dict(self._last_status)
        self._last_status.update({"cancelled": True, "cancel_reason": reason})
        return {"cancelled": True, "reason": reason}

    def close(self) -> Dict[str, Any]:
        if self.env is not None:
            try:
                self.env.close()
            except Exception:
                pass
        self.env = None
        self._env_key = None
        return {"closed": True}

    # -- helpers --
    def _format_obs(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        self._raw_obs = obs
        # LIBERO renders images upside-down; flip vertically+horizontally to match training.
        agent = np.ascontiguousarray(np.asarray(obs["agentview_image"])[::-1, ::-1])
        wrist = np.ascontiguousarray(np.asarray(obs["robot0_eye_in_hand_image"])[::-1, ::-1])
        return {
            "observation_id": "libero_obs_%d" % self.step_idx,
            "agentview_image": agent.astype(np.uint8, copy=False),
            "robot0_eye_in_hand_image": wrist.astype(np.uint8, copy=False),
            "robot0_eef_pos": np.asarray(obs["robot0_eef_pos"], dtype=np.float32),
            "robot0_eef_quat": np.asarray(obs["robot0_eef_quat"], dtype=np.float32),
            "robot0_gripper_qpos": np.asarray(obs["robot0_gripper_qpos"], dtype=np.float32),
            "benchmark_name": self.config["benchmark_name"],
            "task_id": int(self.config["task_id"]),
            "init_state_id": int(self.config.get("init_state_id", 0)),
            "task_description": self.language,
            "timestamp_ns": time.time_ns(),
        }

    def _record_frame(self, raw_obs: Dict[str, Any]) -> None:
        if not self.config.get("record_dir"):
            return
        # Human-upright view: raw LIBERO images are rendered upside-down, so flip
        # vertically only. Show agentview + wrist side by side.
        agent = np.asarray(raw_obs["agentview_image"])[::-1]
        wrist = np.asarray(raw_obs["robot0_eye_in_hand_image"])[::-1]
        self._frames.append(np.ascontiguousarray(np.hstack([agent, wrist])))

    def _write_video(self):
        record_dir = self.config.get("record_dir")
        if not record_dir or not self._frames:
            return None
        if cv2 is None:
            print("[record] cv2 unavailable; skipping video", flush=True)
            return None
        os.makedirs(record_dir, exist_ok=True)
        self._episode_idx += 1
        tag = "success" if self.success else "fail"
        name = "ep_t%d_i%d_%02d_%s.mp4" % (
            int(self.config["task_id"]),
            int(self.config.get("init_state_id", 0)),
            self._episode_idx,
            tag,
        )
        path = os.path.join(record_dir, name)
        h, w = self._frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(path, fourcc, float(self.config.get("record_fps", 20)), (w, h))
        for frame in self._frames:
            writer.write(frame[:, :, ::-1])  # RGB -> BGR for OpenCV
        writer.release()
        print("[record] wrote %d frames -> %s (%s)" % (len(self._frames), path, tag), flush=True)
        return path

    def _libero_metadata(self) -> Dict[str, Any]:
        return {
            "benchmark_name": self.config["benchmark_name"],
            "task_id": int(self.config["task_id"]),
            "init_state_id": int(self.config.get("init_state_id", 0)),
            "step_index": self.step_idx,
            "task_description": self.language,
        }

    def _episode_summary(self) -> Dict[str, Any]:
        summary = {
            "benchmark_name": self.config["benchmark_name"],
            "task_id": int(self.config["task_id"]),
            "init_state_id": int(self.config.get("init_state_id", 0)),
            "task_description": self.language,
            "target_step_index": self.step_idx,
            "success": bool(self.success),
            "done": bool(self.done),
            "total_reward": float(self._total_reward),
            "num_action_chunks": len(self._episode_chunks),
            "chunks": list(self._episode_chunks),
            "final_observation_id": self._last_obs.get("observation_id") if self._last_obs else None,
        }
        if self._last_video_path:
            summary["video_path"] = self._last_video_path
        return summary

    def _task_list(self):
        if self.suite is None:
            return []
        num_tasks = int(
            getattr(self.suite, "n_tasks", 0)
            or getattr(self.suite, "num_tasks", 0)
            or len(getattr(self.suite, "tasks", []) or [])
        )
        tasks = []
        for task_id in range(num_tasks):
            try:
                task = self.suite.get_task(task_id)
            except Exception:
                continue
            item = {
                "task_id": task_id,
                "task_name": str(getattr(task, "name", "task_%d" % task_id)),
                "language": str(getattr(task, "language", getattr(task, "name", "task_%d" % task_id))),
            }
            problem_folder = getattr(task, "problem_folder", None)
            bddl_file = getattr(task, "bddl_file", None)
            if problem_folder is not None:
                item["problem_folder"] = str(problem_folder)
            if bddl_file is not None:
                item["bddl_file"] = str(bddl_file)
            tasks.append(item)
        return tasks


def _dispatch(runtime: LiberoRealRuntime, request: Dict[str, Any]) -> (str, Dict[str, Any]):
    rtype = request.get("type")
    payload = request.get("payload") or {}
    if rtype == "target.describe":
        return rtype, runtime.describe()
    if rtype == "target.configure_session":
        return rtype, runtime.configure_session(payload)
    if rtype == "target.start_session":
        return rtype, runtime.start_session(payload)
    if rtype == "target.reset":
        return rtype, runtime.reset(payload)
    if rtype == "target.observe":
        return "target.observation", runtime.observe(payload)
    if rtype == "target.action_chunk":
        return rtype, runtime.action_chunk(payload)
    if rtype == "target.execution_status":
        return rtype, runtime.execution_status()
    if rtype == "target.cancel":
        return rtype, runtime.cancel(str(payload.get("reason", "cancelled")))
    if rtype == "target.close":
        return rtype, runtime.close()
    raise TargetProtocolError("unsupported target RPC type: %s" % rtype)


async def serve(runtime: LiberoRealRuntime, host: str, port: int) -> None:
    import websockets

    async def handler(ws):
        async for message in ws:
            if isinstance(message, str):
                await ws.send(packb({"version": RPC_VERSION, "type": "runtime.error", "seq": 0,
                                     "timestamp_ns": time.time_ns(),
                                     "payload": {"error_code": "BAD_PAYLOAD", "message": "expected binary msgpack"}}))
                continue
            request = unpackb(message)
            try:
                rtype, payload = _dispatch(runtime, request)
                await ws.send(make_response(request, rtype, payload))
            except Exception as exc:  # noqa: BLE001
                await ws.send(
                    make_response(
                        request,
                        "runtime.error",
                        {"error_code": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()},
                    )
                )

    async with websockets.serve(handler, host, port, max_size=None, compression=None):
        print("LIBERO real target server listening on ws://%s:%d" % (host, port), flush=True)
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9002)
    parser.add_argument("--benchmark-name", default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--init-state-id", type=int, default=0)
    parser.add_argument("--camera-height", type=int, default=256)
    parser.add_argument("--camera-width", type=int, default=256)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--num-steps-wait", type=int, default=10)
    parser.add_argument("--record-dir", default=None, help="if set, write an mp4 per episode here")
    parser.add_argument("--record-fps", type=int, default=20)
    args = parser.parse_args()
    runtime = LiberoRealRuntime(
        {
            "benchmark_name": args.benchmark_name,
            "task_id": args.task_id,
            "init_state_id": args.init_state_id,
            "camera_height": args.camera_height,
            "camera_width": args.camera_width,
            "max_steps": args.max_steps,
            "num_steps_wait": args.num_steps_wait,
            "record_dir": args.record_dir,
            "record_fps": args.record_fps,
        }
    )
    asyncio.run(serve(runtime, args.host, args.port))


if __name__ == "__main__":
    main()
