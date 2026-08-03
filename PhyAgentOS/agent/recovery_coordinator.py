"""Bridge verifier recovery requests back into the normal Agent Planner loop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from PhyAgentOS.bus.events import InboundMessage
from PhyAgentOS.bus.queue import MessageBus
from PhyAgentOS.runtime.schemas import RecoveryRequest
from PhyAgentOS.runtime.schemas.common import utc_now
from PhyAgentOS.runtime.watchdog.registry import SessionRegistry
from PhyAgentOS.runtime.watchdog.result_writer import ResultWriter


class AgentRecoveryCoordinator:
    """Dispatch each recovery request once and enforce its persisted deadline."""

    def __init__(
        self,
        *,
        workspace: str | Path,
        bus: MessageBus,
        poll_interval_s: float = 1.0,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.bus = bus
        self.registry = SessionRegistry(self.workspace / "SESSIONS.md")
        self.result_writer = ResultWriter(self.workspace)
        self.poll_interval_s = max(0.05, float(poll_interval_s))
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            ran = await self.run_once()
            if not ran:
                await asyncio.sleep(self.poll_interval_s)

    def stop(self) -> None:
        self._stopped = True

    async def run_once(self) -> bool:
        sessions = [
            session
            for session in self.registry.load().sessions
            if session.status.value == "awaiting_replan"
        ]
        if not sessions:
            return False
        pending = [
            (
                session,
                RecoveryRequest.model_validate(
                    session.result.metadata.get("recovery_request")
                ),
            )
            for session in sessions
        ]
        expired = next(
            ((session, request) for session, request in pending if utc_now() >= request.deadline),
            None,
        )
        if expired is not None:
            session, request = expired
            message = "Agent Planner did not create a recovery child before the deadline."
            marked = self.registry.mark_replan_failed(
                session.session_id,
                error_code="VERIFICATION_REPLAN_TIMEOUT",
                error_message=message,
            )
            if not marked:
                return True
            self.result_writer.write_lesson(
                session,
                session.target_ref.removeprefix("target://"),
                session.skillruntime_ref.removeprefix("skillruntime://"),
                "agent_recovery",
                "VERIFICATION_REPLAN_TIMEOUT",
                message,
                request.model_dump(mode="json"),
            )
            return True
        dispatchable = next(
            (
                (session, request)
                for session, request in pending
                if request.dispatched_at is None
            ),
            None,
        )
        if dispatchable is None:
            return False
        session, request = dispatchable
        request = self.registry.mark_recovery_dispatched(session.session_id)
        await self.bus.publish_inbound(
            InboundMessage(
                channel="system",
                sender_id="session-verifier",
                chat_id=f"recovery:{session.session_id}",
                session_key_override=f"system:recovery:{session.session_id}",
                content=self._planner_message(session, request),
                metadata={"recovery_request_id": request.request_id},
            )
        )
        return True

    @staticmethod
    def _planner_message(session, request: RecoveryRequest) -> str:
        payload = {
            "parent_session_id": session.session_id,
            "goal": session.verification.goal,
            "success_criteria": session.verification.success_criteria,
            "constraints": request.preserved_constraints,
            "unmet_criteria": request.unmet_criteria,
            "reason_and_guidance": request.guidance,
            "evidence_refs": request.evidence_refs,
            "target_ref": session.target_ref,
            "skillruntime_ref": session.skillruntime_ref,
            "deadline": request.deadline.isoformat(),
        }
        return (
            "[System: task recovery requested]\n"
            "Re-plan through the normal Planner. Preserve the goal, target, safety, routing, and "
            "verification contract. Inspect current runtime context as needed, then call "
            "create_replanned_session exactly once with a new task_description and complete "
            "runtime_hints. Never reuse the old Gateway command_id and do not treat verifier "
            "guidance as an executable action.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
