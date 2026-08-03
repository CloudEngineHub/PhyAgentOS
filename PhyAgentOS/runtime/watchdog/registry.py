"""Session registry backed by workspace/SESSIONS.md."""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from pydantic import ValidationError

from PhyAgentOS.runtime.schemas import (
    RecoveryRequest,
    SessionResult,
    SessionRuntimeHints,
    SessionsDocument,
    SessionSpec,
    SessionStatus,
)
from PhyAgentOS.runtime.schemas.common import utc_now
from PhyAgentOS.runtime.schemas.session import validate_status_transition
from PhyAgentOS.runtime.state_io.markdown_yaml import read_yaml_block, write_yaml_block
from PhyAgentOS.runtime.watchdog.errors import error_code_for, terminal_status_for


class SessionRegistry:
    """Manage runtime session state transitions in a Markdown YAML document."""

    def __init__(self, sessions_path: Path):
        self.sessions_path = sessions_path
        self.lock_path = sessions_path.with_suffix(sessions_path.suffix + ".lock")
        self.last_claim_token: str | None = None

    def load(self) -> SessionsDocument:
        return self._load_unlocked()

    def _load_unlocked(self) -> SessionsDocument:
        try:
            return SessionsDocument.model_validate(read_yaml_block(self.sessions_path))
        except ValidationError as exc:
            raise ValueError(f"invalid sessions document {self.sessions_path}: {exc}") from exc

    def save(self, document: SessionsDocument) -> None:
        with self._exclusive_lock():
            self._save_unlocked(document)

    def _save_unlocked(self, document: SessionsDocument) -> None:
        write_yaml_block(
            self.sessions_path,
            "Runtime Sessions",
            document.model_dump(mode="json", exclude_none=True),
        )

    def first_pending(self, document: SessionsDocument | None = None) -> SessionSpec | None:
        document = document or self.load()
        for session in document.sessions:
            if session.status == SessionStatus.PENDING:
                return session
        return None

    def first_awaiting_verification(
        self, document: SessionsDocument | None = None
    ) -> SessionSpec | None:
        document = document or self.load()
        return next(
            (
                session
                for session in document.sessions
                if session.status == SessionStatus.AWAITING_VERIFICATION
            ),
            None,
        )

    def first_awaiting_replan(
        self, document: SessionsDocument | None = None
    ) -> SessionSpec | None:
        document = document or self.load()
        return next(
            (
                session
                for session in document.sessions
                if session.status == SessionStatus.AWAITING_REPLAN
            ),
            None,
        )

    def get_session(self, session_id: str) -> SessionSpec:
        for session in self.load().sessions:
            if session.session_id == session_id:
                return session
        raise KeyError(f"session not found: {session_id}")

    def try_claim(self, session_id: str, worker_id: str) -> bool:
        """Claim a pending session and verify ownership after the write."""
        with self._exclusive_lock():
            document = self._load_unlocked()
            claim_token = uuid4().hex
            changed = False
            for session in document.sessions:
                if session.session_id != session_id:
                    continue
                if session.status != SessionStatus.PENDING:
                    return False
                validate_status_transition(session.status, SessionStatus.CLAIMED)
                session.status = SessionStatus.CLAIMED
                session.claimed_by = worker_id
                session.claim_token = claim_token
                session.updated_at = utc_now()
                changed = True
                break
            if not changed:
                return False

            self._save_unlocked(document)
            owned = self._get_session_from_document(document, session_id)
            verified = (
                owned.status == SessionStatus.CLAIMED
                and owned.claimed_by == worker_id
                and owned.claim_token == claim_token
            )
            self.last_claim_token = claim_token if verified else None
            return verified

    def mark_running(self, session_id: str) -> None:
        self._update_session_status(session_id, SessionStatus.RUNNING)

    def mark_finalizing(self, session_id: str) -> None:
        self._update_session_status(session_id, SessionStatus.FINALIZING)

    def mark_awaiting_verification(self, session_id: str, result: SessionResult) -> None:
        result.verification.status = "pending"
        self._update_session_status(
            session_id,
            SessionStatus.AWAITING_VERIFICATION,
            result=result,
        )

    def try_claim_verification(self, session_id: str, worker_id: str) -> bool:
        """Atomically claim one semantic verification attempt."""
        with self._exclusive_lock():
            document = self._load_unlocked()
            session = self._get_session_from_document(document, session_id)
            if session.status != SessionStatus.AWAITING_VERIFICATION:
                return False
            validate_status_transition(session.status, SessionStatus.VERIFYING)
            session.status = SessionStatus.VERIFYING
            session.claimed_by = worker_id
            session.claim_token = uuid4().hex
            session.updated_at = utc_now()
            session.result.verification.status = "running"
            self._save_unlocked(document)
            return True

    def release_verification(self, session_id: str, worker_id: str) -> None:
        with self._exclusive_lock():
            document = self._load_unlocked()
            session = self._get_session_from_document(document, session_id)
            if session.status != SessionStatus.VERIFYING or session.claimed_by != worker_id:
                return
            validate_status_transition(session.status, SessionStatus.AWAITING_VERIFICATION)
            session.status = SessionStatus.AWAITING_VERIFICATION
            session.claimed_by = None
            session.claim_token = None
            session.updated_at = utc_now()
            session.result.verification.status = "pending"
            self._save_unlocked(document)

    def mark_preflight_checking(self, session_id: str) -> None:
        self._update_session_status(session_id, SessionStatus.PREFLIGHT_CHECKING)

    def mark_rejected(self, session_id: str, result: SessionResult) -> None:
        result.status = SessionStatus.REJECTED.value
        result.success = False
        self._update_session_status(session_id, SessionStatus.REJECTED, result=result)

    def mark_succeeded(self, session_id: str, result: SessionResult) -> None:
        result.status = SessionStatus.SUCCEEDED.value
        result.success = True if result.success is None else result.success
        self._update_session_status(session_id, SessionStatus.SUCCEEDED, result=result)

    def mark_failed(self, session_id: str, error: Exception) -> None:
        status = SessionStatus(terminal_status_for(error))
        result = SessionResult(
            status=status.value,
            success=False,
            error_code=error_code_for(error),
            error_message=str(error),
        )
        self._update_session_status(session_id, status, result=result)

    def mark_timed_out(self, session_id: str, result: SessionResult) -> None:
        result.status = SessionStatus.TIMED_OUT.value
        result.success = False
        self._update_session_status(session_id, SessionStatus.TIMED_OUT, result=result)

    def mark_execution_failed(self, session_id: str, error: Exception) -> None:
        result = SessionResult(
            status=SessionStatus.FAILED.value,
            success=False,
            error_code=error_code_for(error),
            error_message=str(error),
        )
        self._update_session_status(session_id, SessionStatus.FAILED, result=result)

    def mark_finished(self, session_id: str, result: SessionResult) -> None:
        status = SessionStatus(result.status or (SessionStatus.SUCCEEDED.value if result.success else SessionStatus.FAILED.value))
        self._update_session_status(session_id, status, result=result)

    def mark_verification_finished(
        self,
        session_id: str,
        result: SessionResult,
        final_status: SessionStatus,
    ) -> None:
        if final_status not in {
            SessionStatus.SUCCEEDED,
            SessionStatus.FAILED,
            SessionStatus.TIMED_OUT,
            SessionStatus.CANCELLED,
        }:
            raise ValueError(f"invalid post-verification terminal status: {final_status}")
        result.status = final_status.value
        result.success = final_status == SessionStatus.SUCCEEDED
        result.verification.status = (
            "error" if result.verification.error else "completed"
        )
        self._update_session_status(session_id, final_status, result=result)

    def mark_awaiting_replan(
        self,
        session_id: str,
        result: SessionResult,
        request: RecoveryRequest,
    ) -> None:
        result.status = SessionStatus.AWAITING_REPLAN.value
        result.success = False
        result.verification.status = "completed"
        result.metadata["recovery_request"] = request.model_dump(mode="json")
        self._update_session_status(
            session_id,
            SessionStatus.AWAITING_REPLAN,
            result=result,
        )

    def mark_recovery_dispatched(self, session_id: str) -> RecoveryRequest:
        with self._exclusive_lock():
            document = self._load_unlocked()
            session = self._get_session_from_document(document, session_id)
            if session.status != SessionStatus.AWAITING_REPLAN:
                raise ValueError("session is not awaiting replan")
            raw = session.result.metadata.get("recovery_request")
            request = RecoveryRequest.model_validate(raw)
            if request.dispatched_at is None:
                request.dispatched_at = utc_now()
                session.result.metadata["recovery_request"] = request.model_dump(mode="json")
                session.updated_at = utc_now()
                self._save_unlocked(document)
            return request

    def create_replanned_session(
        self,
        parent_session_id: str,
        *,
        task_description: str,
        runtime_hints: dict[str, Any],
    ) -> SessionSpec:
        """Atomically append a freshly planned child and finish its parent attempt."""
        description = task_description.strip()
        if not description:
            raise ValueError("replanned task_description must be non-empty")
        required_hint_fields = {
            "perception_queries",
            "force_environment_refresh",
            "preferred_replan_every_steps",
            "gateway_action",
        }
        missing_hint_fields = required_hint_fields - set(runtime_hints)
        if missing_hint_fields:
            raise ValueError(
                "replanned runtime_hints must be complete; missing: "
                + ", ".join(sorted(missing_hint_fields))
            )
        hints = SessionRuntimeHints.model_validate(runtime_hints)
        gateway_action = dict(hints.gateway_action)
        gateway_action.pop("command_id", None)
        hints.gateway_action = gateway_action

        with self._exclusive_lock():
            document = self._load_unlocked()
            parent = self._get_session_from_document(document, parent_session_id)
            if parent.status != SessionStatus.AWAITING_REPLAN:
                raise ValueError("parent session is not awaiting replan")
            recovery = RecoveryRequest.model_validate(
                parent.result.metadata.get("recovery_request")
            )
            if utc_now() >= recovery.deadline:
                raise ValueError("recovery request deadline has expired")
            attempt = parent.replan_attempt + 1
            child_id = f"{parent.session_id}_replan_{attempt}_{uuid4().hex[:6]}"
            child = SessionSpec(
                session_id=child_id,
                parent_session_id=parent.session_id,
                replan_attempt=attempt,
                goal_id=parent.goal_id,
                parent_goal_id=parent.parent_goal_id,
                horizon=parent.horizon,
                target_ref=parent.target_ref,
                skillruntime_ref=parent.skillruntime_ref,
                task_description=description,
                verification=parent.verification.model_copy(deep=True),
                status=SessionStatus.PENDING,
                priority=parent.priority,
                created_at=utc_now(),
                updated_at=utc_now(),
                timeouts=parent.timeouts.model_copy(deep=True),
                retry=parent.retry.model_copy(update={"attempted": 0}, deep=True),
                depends_on=[],
                routing=parent.routing.model_copy(deep=True),
                execution=parent.execution.model_copy(deep=True),
                runtime_hints=hints,
                safety_profile=parent.safety_profile.model_copy(deep=True),
                result=SessionResult(),
            )
            if any(item.session_id == child.session_id for item in document.sessions):
                raise ValueError(f"duplicate replanned session id: {child.session_id}")
            validate_status_transition(parent.status, SessionStatus.REPLANNED)
            parent.status = SessionStatus.REPLANNED
            parent.updated_at = utc_now()
            parent.result.status = SessionStatus.REPLANNED.value
            parent.result.success = False
            parent.result.metadata["replanned_session_id"] = child.session_id
            document.sessions.append(child)
            self._save_unlocked(document)
            return child

    def mark_replan_failed(
        self,
        session_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> bool:
        with self._exclusive_lock():
            document = self._load_unlocked()
            session = self._get_session_from_document(document, session_id)
            if session.status != SessionStatus.AWAITING_REPLAN:
                return False
            validate_status_transition(session.status, SessionStatus.FAILED)
            result = session.result.model_copy(deep=True)
            result.status = SessionStatus.FAILED.value
            result.success = False
            result.error_code = error_code
            result.error_message = error_message
            session.status = SessionStatus.FAILED
            session.claimed_by = None
            session.claim_token = None
            session.updated_at = utc_now()
            session.result = result
            self._save_unlocked(document)
            return True

    def update_result(self, session_id: str, result: SessionResult) -> None:
        with self._exclusive_lock():
            document = self._load_unlocked()
            session = self._get_session_from_document(document, session_id)
            session.result = result
            session.updated_at = utc_now()
            self._save_unlocked(document)

    def mark_retry_pending(self, session_id: str, error: Exception) -> None:
        """Return a claimed/running session to pending for a configured retry."""
        with self._exclusive_lock():
            document = self._load_unlocked()
            for session in document.sessions:
                if session.session_id != session_id:
                    continue
                session.status = SessionStatus.PENDING
                session.claimed_by = None
                session.claim_token = None
                session.retry.attempted += 1
                session.updated_at = utc_now()
                session.result = SessionResult(
                    status=SessionStatus.PENDING.value,
                    success=False,
                    error_code=error_code_for(error),
                    error_message=str(error),
                )
                self._save_unlocked(document)
                return
        raise KeyError(f"session not found: {session_id}")

    def _update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        result: SessionResult | None = None,
    ) -> None:
        with self._exclusive_lock():
            document = self._load_unlocked()
            for session in document.sessions:
                if session.session_id != session_id:
                    continue
                validate_status_transition(session.status, status)
                session.status = status
                if status not in {
                    SessionStatus.CLAIMED,
                    SessionStatus.VERIFYING,
                }:
                    session.claimed_by = None
                    session.claim_token = None
                session.updated_at = utc_now()
                if result is not None:
                    session.result = result
                self._save_unlocked(document)
                return
        raise KeyError(f"session not found: {session_id}")

    def _get_session_from_document(self, document: SessionsDocument, session_id: str) -> SessionSpec:
        for session in document.sessions:
            if session.session_id == session_id:
                return session
        raise KeyError(f"session not found: {session_id}")

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
