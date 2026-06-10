"""Minecraft skill runtime: drives an episode on a MinecraftTarget."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PhyAgentOS.runtime.schemas import AdapterPlan, SessionResult, SessionSpec
from PhyAgentOS.runtime.sessions.models import SkillContext, SkillRuntimeResult
from PhyAgentOS.runtime.skills.builtin import BuiltinSkillRuntime
from PhyAgentOS.runtime.watchdog.errors import SessionTimeoutError

logger = logging.getLogger(__name__)


class MinecraftSkillRuntime(BuiltinSkillRuntime):
    """Execute a Minecraft episode: observe → pick_action → action_chunk → repeat."""

    def start(self, skill_ctx: SkillContext) -> None:
        pass

    def cancel(self, skill_ctx: SkillContext, reason: str) -> None:
        pass

    def snapshot(self, skill_ctx: SkillContext) -> dict:
        return {"status": "idle"}

    def run_builtin_loop(
        self,
        skill_ctx: SkillContext,
        target_handle,
        adapter_plan: AdapterPlan,
    ) -> SkillRuntimeResult:
        session = skill_ctx.session
        action_plan: list[dict[str, Any]] = _extract_action_plan(session)
        step_results: list[dict[str, Any]] = []
        total_reward = 0.0
        start_time = time.monotonic()
        timeout_s = session.timeouts.execute_timeout_s

        for step_idx in range(session.execution.max_steps):
            if time.monotonic() - start_time > timeout_s:
                raise SessionTimeoutError(
                    f"session {session.session_id} exceeded {timeout_s}s"
                )

            if step_idx >= len(action_plan):
                final_status = {
                    "num_steps": len(step_results),
                    "reward": total_reward,
                    "executed_steps": len(step_results),
                }
                return SkillRuntimeResult(
                    status="succeeded",
                    success=True,
                    final_status=final_status,
                    metadata={
                        "step_results": step_results,
                        "task": session.task_description,
                    },
                )

            action = _pick_action(action_plan, step_idx, target_handle)

            status = target_handle.action_chunk({"actions": [action]})
            obs = target_handle.observe()
            obs_data = obs.data

            action_ok = bool(status.get("ok", True))
            action_result = str(status.get("result", ""))
            step_results.append({
                "step": step_idx,
                "type": action.get("type"),
                "params": action.get("params", {}),
                "ok": action_ok,
                "result": action_result,
            })
            if not action_ok:
                logger.warning(
                    "step %d: %s failed — %s",
                    step_idx, action.get("type"), action_result,
                )
                return SkillRuntimeResult(
                    status="failed",
                    success=False,
                    final_status={"num_steps": len(step_results)},
                    error_code="ACTION_FAILED",
                    error_message=f"step {step_idx}: {action.get('type')} failed: {action_result}",
                    metadata={
                        "failed_action": action.get("type"),
                        "failed_action_params": action.get("params", {}),
                        "bridge_result": action_result,
                    },
                )
            logger.info(
                "step %d: %s ok — %s",
                step_idx, action.get("type"), action_result,
            )

            if action.get("type") == "move" and action.get("params", {}).get("absolute"):
                obs_data = _wait_for_arrival(
                    target_handle, obs_data,
                    target_xyz=(
                        float(action["params"]["dx"]),
                        float(action["params"]["dy"]),
                        float(action["params"]["dz"]),
                    ),
                    timeout_s=min(30.0, timeout_s - (time.monotonic() - start_time)),
                    step_delay=0.5,
                )

        return SkillRuntimeResult(
            status="failed",
            success=False,
            final_status={"num_steps": len(step_results)},
            error_code="MAX_STEPS_EXCEEDED",
            error_message="session reached max_steps without success",
        )


_LESSON_HEADING = "## Session Record"


def record_lesson_to_workspace(
    workspace: str | Path,
    session: SessionSpec,
    result: SessionResult,
) -> None:
    """Write a successful session record to LESSONS.md."""
    ws = Path(workspace)
    lesson_file = ws / "LESSONS.md"
    step_results = result.metadata.get("step_results", [])
    task = result.metadata.get("task", session.task_description)

    lines: list[str] = []
    lines.append(_LESSON_HEADING)
    lines.append(f"- **Task**: {task}")
    lines.append(f"- **Session**: {session.session_id}")
    lines.append(f"- **Target**: {session.target_ref}")
    lines.append(f"- **Timestamp**: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- **Steps**: {result.num_steps or len(step_results)}")
    lines.append(f"- **Status**: {'success' if result.success else 'failed'}")
    if result.error_code:
        lines.append(f"- **Error**: {result.error_code} — {result.error_message or ''}")
    for sr in step_results:
        ok_mark = "\u2713" if sr.get("ok") else "\u2717"
        lines.append(f"  {sr['step']+1}. {sr['type']} {ok_mark}")
        params = sr.get("params", {})
        if params:
            lines.append(f"     params: {params}")
        res = sr.get("result", "")
        if res:
            lines.append(f"     result: {res}")
    lines.append("")

    lesson_entry = "\n".join(lines) + "\n"
    ws.mkdir(parents=True, exist_ok=True)
    if lesson_file.exists():
        with open(lesson_file, "a", encoding="utf-8") as fh:
            fh.write(lesson_entry)
    else:
        lesson_file.write_text("# Lessons Learned\n\n" + lesson_entry, encoding="utf-8")
    logger.info("recorded lesson to %s: %s", lesson_file, task)


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
    target_handle,
) -> dict[str, Any]:
    """Pick the next action, resolving dynamic targets at runtime."""
    action = action_plan[step_idx].copy()

    if action.get("type") == "move":
        target_type = action.get("params", {}).get("target")
        if target_type:
            obs = target_handle.observe()
            entity = _find_nearest_entity(obs.data, target_type)
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
    target_handle,
    obs_data: dict[str, Any],
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
        pos = obs_data.get("info", {}).get("position", {})
        bx = float(pos.get("x", 0))
        by = float(pos.get("y", 0))
        bz = float(pos.get("z", 0))
        dist = math.sqrt((bx - tx) ** 2 + (by - ty) ** 2 + (bz - tz) ** 2)
        if dist <= arrival_radius:
            logger.info("arrived at target (dist=%.1f)", dist)
            return obs_data
        time.sleep(step_delay)
        obs = target_handle.observe()
        obs_data = obs.data
    logger.warning("move timed out after %.1fs", timeout_s)
    return obs_data
