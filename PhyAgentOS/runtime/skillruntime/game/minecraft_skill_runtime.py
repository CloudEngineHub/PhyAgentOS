"""Minecraft skill runtime: drives an episode on a MinecraftTarget."""

from __future__ import annotations

import logging
import time
from typing import Any

from PhyAgentOS.runtime.schemas import AdapterPlan, SessionResult, SessionSpec
from PhyAgentOS.runtime.skillruntime.base import BaseSkillRuntime
from PhyAgentOS.runtime.watchdog.errors import SessionTimeoutError

logger = logging.getLogger(__name__)


class MinecraftSkillRuntime(BaseSkillRuntime):
    """Execute a Minecraft episode: observe → pick_action → step → repeat."""

    runtime_kind = "builtin"

    def start(self, skill_ctx) -> None:
        pass

    def cancel(self, skill_ctx, reason: str) -> None:
        pass

    def snapshot(self, skill_ctx) -> dict:
        return {"status": "idle"}

    def run(
        self,
        session: SessionSpec,
        target,
        target_adapter,
        policy_adapter,
        action_bridges,
        policy_client,
        adapter_plan: AdapterPlan,
    ) -> SessionResult:
        target.build()
        session_ctx = session.model_dump(mode="json")
        session_ctx["adapter_plan"] = adapter_plan.model_dump(mode="json")

        target.configure_session({
            "session_id": session.session_id,
            "task_description": session.task_description,
            "target_ref": session.target_ref,
            "skillruntime_ref": session.skillruntime_ref,
        })

        raw_obs = target.reset(session_ctx)
        num_steps = 0
        total_reward = 0.0
        start_time = time.monotonic()
        timeout_s = session.timeouts.execute_timeout_s

        action_plan: list[dict[str, Any]] = _extract_action_plan(session)

        for step_idx in range(session.execution.max_steps):
            if time.monotonic() - start_time > timeout_s:
                raise SessionTimeoutError(
                    f"session {session.session_id} exceeded {timeout_s}s"
                )

            target_info = {
                "step_index": step_idx,
                "task_description": session.task_description,
            }
            runtime_obs = target_adapter.to_runtime_observation(raw_obs, target_info)

            if step_idx >= len(action_plan):
                return SessionResult(
                    status="succeeded",
                    success=True,
                    num_steps=num_steps,
                    return_value=total_reward,
                )

            action = _pick_action(action_plan, step_idx, runtime_obs)

            bridged_action = action
            for bridge in action_bridges:
                bridged_action = bridge.apply(bridged_action, target_info)

            transition = target.step(bridged_action)
            num_steps += 1
            raw_obs = transition.get("obs", target.observe())

            if action.get("type") == "move" and action.get("params", {}).get("absolute"):
                raw_obs = _wait_for_arrival(
                    target, raw_obs,
                    target_xyz=(
                        float(action["params"]["dx"]),
                        float(action["params"]["dy"]),
                        float(action["params"]["dz"]),
                    ),
                    timeout_s=min(30.0, timeout_s - (time.monotonic() - start_time)),
                    step_delay=0.5,
                )

            total_reward += float(transition.get("reward", 0.0))

            if bool(transition.get("done", False)) or bool(
                transition.get("info", {}).get("success", False)
            ):
                return SessionResult(
                    status="succeeded",
                    success=True,
                    num_steps=num_steps,
                    return_value=total_reward,
                    metadata={"done": True},
                )

        return SessionResult(
            status="failed",
            success=False,
            num_steps=num_steps,
            return_value=total_reward,
            error_code="MAX_STEPS_EXCEEDED",
            error_message="session reached max_steps without success",
        )


def _extract_action_plan(session: SessionSpec) -> list[dict[str, Any]]:
    hints = session.runtime_hints
    queries = hints.perception_queries if hints else []
    plan: list[dict[str, Any]] = []
    for q in queries:
        if isinstance(q, dict) and "type" in q:
            plan.append(q)
    return plan


def _pick_action(
    action_plan: list[dict[str, Any]],
    step_idx: int,
    runtime_obs: dict[str, Any],
) -> dict[str, Any]:
    """Pick the next action, resolving dynamic targets at runtime."""
    action = action_plan[step_idx].copy()

    if action.get("type") == "move":
        target_type = action.get("params", {}).get("target")
        if target_type:
            entity = _find_nearest_entity(runtime_obs, target_type)
            if entity is None:
                label = "player nearby" if target_type == "player" else f"any {target_type} nearby"
                return {"type": "chat", "params": {"message": f"I can't see {label}."}}
            logger.info("resolved target %s → (%.1f, %.1f, %.1f)",
                         target_type,
                         entity["position"]["x"], entity["position"]["y"], entity["position"]["z"])
            return _build_move_to_entity(entity)

    return action


def _find_nearest_entity(
    runtime_obs: dict[str, Any], target_type: str
) -> dict[str, Any] | None:
    entities = runtime_obs.get("nearby_entities", [])
    info = runtime_obs.get("info", {})

    bot_pos = None
    pos = info.get("position")
    if pos:
        bot_pos = (pos.get("x", 0), pos.get("y", 0), pos.get("z", 0))

    accepted = {target_type, target_type.lower(), target_type.capitalize()}
    if target_type == "player":
        accepted.update(info.get("player_list", []))

    matches = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        if e.get("type", "") in accepted and e.get("position"):
            matches.append(e)

    if not matches and target_type == "player":
        bot_name = (runtime_obs.get("bot") or {}).get("username", "")
        for p in runtime_obs.get("players", []):
            if not isinstance(p, dict):
                continue
            if p.get("username", "") == bot_name:
                continue
            if p.get("position"):
                matches.append({
                    "type": p.get("username", "player"),
                    "position": p["position"],
                })

    if not matches:
        return None
    if bot_pos:
        def _dist(m):
            pp = m["position"]
            return ((pp["x"] - bot_pos[0]) ** 2 +
                    (pp["y"] - bot_pos[1]) ** 2 +
                    (pp["z"] - bot_pos[2]) ** 2)
        matches.sort(key=_dist)
    return matches[0]


def _build_move_to_entity(entity: dict[str, Any]) -> dict[str, Any]:
    pos = entity["position"]
    return {
        "type": "move",
        "params": {
            "dx": float(pos.get("x", 0)) + 1.0,
            "dy": float(pos.get("y", 0)),
            "dz": float(pos.get("z", 0)),
            "absolute": True,
        },
    }


def _wait_for_arrival(
    target,
    raw_obs: dict[str, Any],
    target_xyz: tuple[float, float, float],
    timeout_s: float = 30.0,
    step_delay: float = 0.5,
    arrival_radius: float = 2.0,
) -> dict[str, Any]:
    """Poll observe() until the bot reaches target_xyz or timeout."""
    import math
    deadline = time.monotonic() + max(0.0, timeout_s)
    tx, ty, tz = target_xyz
    while time.monotonic() < deadline:
        pos = raw_obs.get("info", {}).get("position", {})
        bx = float(pos.get("x", 0))
        by = float(pos.get("y", 0))
        bz = float(pos.get("z", 0))
        dist = math.sqrt((bx - tx) ** 2 + (by - ty) ** 2 + (bz - tz) ** 2)
        if dist <= arrival_radius:
            logger.info("arrived at target (dist=%.1f)", dist)
            return raw_obs
        time.sleep(step_delay)
        raw_obs = target.observe()
    logger.warning("move timed out after %.1fs", timeout_s)
    return raw_obs
