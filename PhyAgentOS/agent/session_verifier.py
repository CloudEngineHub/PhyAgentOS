"""Agent-owned semantic verification for completed runtime sessions."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from PhyAgentOS.providers.base import LLMProvider
from PhyAgentOS.runtime.schemas import (
    RecoveryRequest,
    SessionResult,
    SessionSpec,
    SessionStatus,
    VerificationVerdict,
)
from PhyAgentOS.runtime.schemas.common import utc_now
from PhyAgentOS.runtime.verification import (
    VerificationEvidenceError,
    VerificationRequest,
    VerificationRequestBuilder,
)
from PhyAgentOS.runtime.watchdog.registry import SessionRegistry
from PhyAgentOS.runtime.watchdog.result_writer import ResultWriter
from PhyAgentOS.verification.engine import VerificationEngine
from PhyAgentOS.verification.service import VerificationServiceProcess

logger = logging.getLogger(__name__)

_REVIEWABLE_STATUSES = {
    SessionStatus.SUCCEEDED,
    SessionStatus.FAILED,
    SessionStatus.REPLANNED,
    SessionStatus.TIMED_OUT,
    SessionStatus.CANCELLED,
}


class VerificationVerdictError(ValueError):
    """Verifier output violated the public verdict contract."""


class SessionVerifier:
    """Poll pending sessions and apply task-level semantic verdicts."""

    def __init__(
        self,
        *,
        workspace: str | Path,
        provider: LLMProvider,
        model: str,
        max_replans: int,
        evidence_retention: Literal["all", "failed", "none"] = "none",
        poll_interval_s: float = 1.0,
        worker_id: str | None = None,
        timeout_s: float = 180.0,
        service_host: str = "127.0.0.1",
        service_port: int = 8100,
        session_secret: str | None = None,
        service_provider_spec: dict[str, Any] | None = None,
        replan_timeout_s: float = 120.0,
        max_calls: int = 50,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.engine = VerificationEngine(provider=provider, model=model, timeout_s=timeout_s)
        self.max_replans = max(0, int(max_replans))
        self.evidence_retention = evidence_retention
        self.poll_interval_s = max(0.05, float(poll_interval_s))
        self.worker_id = worker_id or f"agent-verifier@{socket.gethostname()}"
        self.registry = SessionRegistry(self.workspace / "SESSIONS.md")
        self.result_writer = ResultWriter(self.workspace)
        self.request_builder = VerificationRequestBuilder(self.workspace)
        self.replan_timeout_s = max(1.0, float(replan_timeout_s))
        self.max_calls = max(0, int(max_calls))
        self.calls = 0
        self._stopped = False
        self.service = VerificationServiceProcess(
            engine=self.engine,
            host=service_host,
            port=service_port,
            session_secret=session_secret or uuid4().hex,
            provider_spec=service_provider_spec,
        )

    async def start(self) -> None:
        if not self._stopped:
            await self._run_blocking(self.service.start)

    async def run(self) -> None:
        try:
            await self.start()
        except Exception:
            logger.exception("Agent Verification Service failed readiness; sessions will fail closed")
        while not self._stopped:
            ran = await self.run_once()
            if not ran:
                await asyncio.sleep(self.poll_interval_s)

    def stop(self) -> None:
        self._stopped = True
        self.service.stop()

    async def run_once(self) -> bool:
        session = self.registry.first_awaiting_verification()
        if session is None:
            return False
        if self.max_calls and self.calls >= self.max_calls:
            self._finish_with_error(
                session,
                "VERIFICATION_CALL_BUDGET_EXHAUSTED",
                f"verifier call budget exhausted ({self.max_calls})",
                source="auto",
            )
            return True
        outcome = await self.verify_session(session.session_id, source="auto")
        return outcome.get("code") != "already_verifying"

    async def verify_session(
        self,
        session_id: str,
        *,
        source: Literal["auto", "tool"] = "tool",
    ) -> dict[str, Any]:
        try:
            session = self.registry.get_session(session_id)
        except KeyError:
            return self._outcome(False, "not_found", session_id, message="session does not exist")

        if session.status == SessionStatus.AWAITING_VERIFICATION:
            if not self.registry.try_claim_verification(session_id, self.worker_id):
                return self._outcome(False, "already_verifying", session_id)
            return await self._run_apply(self.registry.get_session(session_id), source)
        if session.status == SessionStatus.VERIFYING:
            return self._outcome(False, "already_verifying", session_id)
        if session.status in _REVIEWABLE_STATUSES:
            return await self._run_review(session, source)
        return self._outcome(
            False,
            "not_ready",
            session_id,
            message=f"session status is {session.status.value}",
        )

    async def _run_apply(
        self,
        session: SessionSpec,
        source: Literal["auto", "tool"],
    ) -> dict[str, Any]:
        request: VerificationRequest | None = None
        try:
            request = self.request_builder.build(session)
            verdict = await self._verify(request)
            self._validate_verdict(session, request, verdict)
        except asyncio.CancelledError:
            self.registry.release_verification(session.session_id, self.worker_id)
            raise
        except VerificationEvidenceError as exc:
            return self._handle_apply_error(
                session,
                source,
                "VERIFICATION_EVIDENCE_UNAVAILABLE",
                str(exc),
            )
        except VerificationVerdictError as exc:
            return self._handle_apply_error(
                session,
                source,
                "VERIFICATION_INVALID_VERDICT",
                str(exc),
            )
        except Exception as exc:
            logger.exception("session verification failed for %s", session.session_id)
            return self._handle_apply_error(
                session,
                source,
                "VERIFICATION_SERVICE_UNAVAILABLE",
                str(exc) or type(exc).__name__,
            )

        result = session.result.model_copy(deep=True)
        self._record_attempt(result, verdict, source=source, mode="apply")
        result.verification.verdict = verdict
        final_status: SessionStatus | None = None
        if session.verification.mode == "audit":
            final_status = self._execution_terminal_status(result)
            self.registry.mark_verification_finished(
                session.session_id,
                result,
                final_status,
            )
        elif verdict.verdict == "success":
            final_status = SessionStatus.SUCCEEDED
            self.registry.mark_verification_finished(
                session.session_id,
                result,
                final_status,
            )
        elif verdict.verdict == "replan_required" and session.verification.mode == "recovery":
            if session.replan_attempt >= self.max_replans:
                result.error_code = "VERIFICATION_REPLAN_LIMIT_REACHED"
                result.error_message = (
                    f"replan limit reached ({self.max_replans}): {verdict.reason}"
                )
                final_status = SessionStatus.FAILED
                self.registry.mark_verification_finished(
                    session.session_id,
                    result,
                    final_status,
                )
            else:
                context = verdict.recovery_context
                unmet = [
                    item.criterion
                    for item in verdict.criteria
                    if item.status != "satisfied"
                ]
                if context is not None:
                    unmet.extend(context.unmet_criteria)
                preserved_constraints = list(session.verification.constraints)
                if context is not None:
                    preserved_constraints.extend(context.preserved_constraints)
                evidence_refs = list(verdict.evidence_refs)
                for criterion in verdict.criteria:
                    evidence_refs.extend(criterion.evidence_refs)
                request_record = RecoveryRequest(
                    request_id=f"recovery_{uuid4().hex[:16]}",
                    parent_session_id=session.session_id,
                    unmet_criteria=list(dict.fromkeys(unmet)),
                    preserved_constraints=list(dict.fromkeys(preserved_constraints)),
                    guidance=context.guidance if context else verdict.reason,
                    evidence_refs=list(dict.fromkeys(evidence_refs)),
                    deadline=utc_now() + timedelta(seconds=self.replan_timeout_s),
                )
                self.registry.mark_awaiting_replan(
                    session.session_id,
                    result,
                    request_record,
                )
        else:
            result.error_code = (
                "VERIFICATION_REPLAN_REQUIRED"
                if verdict.verdict == "replan_required"
                else "VERIFICATION_INCONCLUSIVE"
                if verdict.verdict == "inconclusive"
                else "VERIFICATION_FAILED"
            )
            result.error_message = verdict.reason
            final_status = SessionStatus.FAILED
            self.registry.mark_verification_finished(
                session.session_id,
                result,
                final_status,
            )

        self._write_lesson(session, verdict, result.error_code)
        retention = self._apply_retention(
            request,
            final_status or SessionStatus.REPLANNED,
        )
        self._record_retention(session.session_id, retention)
        current = self.registry.get_session(session.session_id)
        self.result_writer.write_verification_result(current, current.result)
        return self._outcome(
            True,
            "verified",
            session.session_id,
            status=current.status.value,
            verdict=verdict,
        )

    async def _run_review(
        self,
        session: SessionSpec,
        source: Literal["auto", "tool"],
    ) -> dict[str, Any]:
        try:
            request = self.request_builder.build(session)
            verdict = await self._verify(request)
            self._validate_verdict(session, request, verdict)
        except Exception as exc:
            return self._outcome(
                False,
                "review_error",
                session.session_id,
                message=str(exc),
            )
        result = session.result.model_copy(deep=True)
        self._record_attempt(result, verdict, source=source, mode="review")
        self.registry.update_result(session.session_id, result)
        self.result_writer.write_verification_result(session, result)
        self._write_lesson(session, verdict, None, phase="agent_reverification")
        return self._outcome(
            True,
            "reviewed",
            session.session_id,
            status=session.status.value,
            verdict=verdict,
        )

    async def _verify(self, request: VerificationRequest) -> VerificationVerdict:
        self.calls += 1
        data = await self._run_blocking(self._start_and_verify, request.content)
        try:
            return VerificationVerdict.model_validate(data)
        except Exception as exc:
            raise VerificationVerdictError(str(exc)) from exc

    def _start_and_verify(self, content: list[dict[str, Any]]) -> dict[str, Any]:
        # One executor hop avoids a readiness/HTTP gap and keeps both blocking
        # child-service operations off the Agent event loop.
        self.service.start()
        return self.service.verify_session(content)

    @staticmethod
    async def _run_blocking(function, *args):
        """Run one blocking service call without retaining a process-wide executor."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def set_result(value) -> None:
            if not future.done():
                future.set_result(value)

        def set_exception(error: BaseException) -> None:
            if not future.done():
                future.set_exception(error)

        def invoke() -> None:
            try:
                result = function(*args)
            except BaseException as exc:
                try:
                    loop.call_soon_threadsafe(set_exception, exc)
                except RuntimeError:
                    return
            else:
                try:
                    loop.call_soon_threadsafe(set_result, result)
                except RuntimeError:
                    return

        threading.Thread(
            target=invoke,
            name="paos-verification-call",
            daemon=True,
        ).start()
        return await future

    @staticmethod
    def _validate_verdict(
        session: SessionSpec,
        request: VerificationRequest,
        verdict: VerificationVerdict,
    ) -> None:
        expected = session.verification.success_criteria
        actual = [item.criterion for item in verdict.criteria]
        if len(actual) != len(expected) or set(actual) != set(expected):
            raise VerificationVerdictError(
                "verifier must return exactly one criterion verdict for every success criterion"
            )
        refs = set(verdict.evidence_refs)
        for criterion in verdict.criteria:
            refs.update(criterion.evidence_refs)
        unknown = refs - set(request.valid_evidence_refs)
        if unknown:
            raise VerificationVerdictError(
                "verifier referenced unknown evidence: " + ", ".join(sorted(unknown))
            )

    def _handle_apply_error(
        self,
        session: SessionSpec,
        source: Literal["auto", "tool"],
        code: str,
        message: str,
    ) -> dict[str, Any]:
        result = session.result.model_copy(deep=True)
        self._record_attempt(result, None, source=source, mode="apply", error=message)
        result.verification.error = message
        if session.verification.mode == "audit":
            final_status = self._execution_terminal_status(result)
        else:
            final_status = SessionStatus.FAILED
            result.error_code = code
            result.error_message = message
        self.registry.mark_verification_finished(
            session.session_id,
            result,
            final_status,
        )
        self.result_writer.write_lesson(
            session,
            session.target_ref.removeprefix("target://"),
            session.skillruntime_ref.removeprefix("skillruntime://"),
            "agent_verification",
            code,
            message,
            {"verification_mode": session.verification.mode},
        )
        current = self.registry.get_session(session.session_id)
        self.result_writer.write_verification_result(current, current.result)
        return self._outcome(
            session.verification.mode == "audit",
            "audit_error" if session.verification.mode == "audit" else "verification_error",
            session.session_id,
            status=final_status.value,
            message=message,
        )

    def _finish_with_error(
        self,
        session: SessionSpec,
        code: str,
        message: str,
        *,
        source: Literal["auto", "tool"],
    ) -> None:
        if not self.registry.try_claim_verification(session.session_id, self.worker_id):
            return
        claimed = self.registry.get_session(session.session_id)
        self._handle_apply_error(claimed, source, code, message)

    def _record_attempt(
        self,
        result: SessionResult,
        verdict: VerificationVerdict | None,
        *,
        source: Literal["auto", "tool"],
        mode: Literal["apply", "review"],
        error: str | None = None,
    ) -> None:
        attempt = {
            "attempt_id": f"verification_{uuid4().hex[:12]}",
            "created_at": utc_now().isoformat(),
            "source": source,
            "mode": mode,
            "verdict": verdict.verdict if verdict is not None else None,
            "details": verdict.model_dump(mode="json") if verdict is not None else None,
            "error": error,
        }
        result.verification.attempts.append(attempt)
        compatibility = result.metadata.setdefault("verification", {"attempts": []})
        compatibility.setdefault("attempts", []).append(attempt)

    @staticmethod
    def _execution_terminal_status(result: SessionResult) -> SessionStatus:
        raw = result.execution.status if result.execution is not None else result.status
        mapping = {
            "succeeded": SessionStatus.SUCCEEDED,
            "failed": SessionStatus.FAILED,
            "timed_out": SessionStatus.TIMED_OUT,
            "cancelled": SessionStatus.CANCELLED,
        }
        return mapping.get(str(raw), SessionStatus.FAILED)

    def _apply_retention(
        self,
        request: VerificationRequest,
        final_status: SessionStatus,
    ) -> dict[str, Any]:
        should_delete = self.evidence_retention == "none" or (
            self.evidence_retention == "failed"
            and final_status == SessionStatus.SUCCEEDED
        )
        deleted: list[str] = []
        errors: list[dict[str, str]] = []
        if should_delete:
            for path in request.artifact_paths:
                if path.name in {"evidence_bundle.json", "verification_bundle.json"}:
                    continue
                try:
                    relative = str(path.relative_to(self.workspace.resolve()))
                    path.unlink(missing_ok=True)
                    deleted.append(relative)
                except Exception as exc:
                    errors.append({"path": str(path), "error": str(exc)})
        return {
            "policy": self.evidence_retention,
            "status": "partial" if errors else "deleted" if should_delete else "retained",
            "updated_at": utc_now().isoformat(),
            "deleted_paths": deleted,
            "errors": errors,
        }

    def _record_retention(self, session_id: str, retention: dict[str, Any]) -> None:
        session = self.registry.get_session(session_id)
        result = session.result.model_copy(deep=True)
        result.metadata["verification_retention"] = retention
        self.registry.update_result(session_id, result)

    def _write_lesson(
        self,
        session: SessionSpec,
        verdict: VerificationVerdict,
        error_code: str | None,
        *,
        phase: str = "agent_verification",
    ) -> None:
        self.result_writer.write_lesson(
            session,
            session.target_ref.removeprefix("target://"),
            session.skillruntime_ref.removeprefix("skillruntime://"),
            phase,
            error_code,
            verdict.lesson,
            verdict.model_dump(mode="json"),
        )

    @staticmethod
    def _outcome(
        ok: bool,
        code: str,
        session_id: str,
        *,
        status: str | None = None,
        verdict: VerificationVerdict | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "ok": ok,
                "code": code,
                "session_id": session_id,
                "status": status,
                "verdict": verdict.verdict if verdict is not None else None,
                "reason": verdict.reason if verdict is not None else None,
                "message": message,
            }.items()
            if value is not None
        }
