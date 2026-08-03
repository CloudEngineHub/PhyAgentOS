"""Runtime v2 watchdog supervisor."""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from PhyAgentOS.runtime.gateway import GatewaySessionRunner
from PhyAgentOS.runtime.perception import PerceptionRuntime
from PhyAgentOS.runtime.policy.factory import build_policy_client
from PhyAgentOS.runtime.preflight import RuntimeCompatibilityPreflight
from PhyAgentOS.runtime.schemas import (
    ExecutionError,
    ExecutionRecord,
    ExecutionTimeline,
    RecoveryRequest,
    SessionsDocument,
    SessionStatus,
    SkillRuntimeDocument,
    TargetsDocument,
)
from PhyAgentOS.runtime.schemas.common import utc_now
from PhyAgentOS.runtime.schemas.result import SessionResult
from PhyAgentOS.runtime.sessions.session_runner import SessionRunner
from PhyAgentOS.runtime.state_io.markdown_yaml import read_yaml_block
from PhyAgentOS.runtime.state_io.workspace_paths import RuntimeWorkspacePaths
from PhyAgentOS.runtime.watchdog.errors import SchemaValidationError
from PhyAgentOS.runtime.watchdog.failure import FailureEscalator
from PhyAgentOS.runtime.watchdog.health import HealthMonitor
from PhyAgentOS.runtime.watchdog.registry import SessionRegistry
from PhyAgentOS.runtime.watchdog.result_writer import ResultWriter
from PhyAgentOS.runtime.watchdog.runner_thread import RunnerThreadHandle
from PhyAgentOS.runtime.watchdog.runtime_registry import SkillRuntimeRegistry, TargetRuntimeRegistry
from PhyAgentOS.runtime.watchdog.scheduler import SessionScheduleError, SessionScheduler
from PhyAgentOS.runtime.watchdog.watcher import WorkspaceWatcher


class WatchdogSupervisor:
    """Claim and execute runtime sessions from a workspace."""

    def __init__(
        self,
        workspace: str | Path,
        worker_id: str | None = None,
        environment_workspace: str | Path | None = None,
        verification_service_enabled: bool = False,
        verification_timeout_s: float = 210.0,
    ):
        self.paths = RuntimeWorkspacePaths.from_path(workspace)
        self.workspace = self.paths.workspace
        self.environment_workspace = (
            Path(environment_workspace).expanduser() if environment_workspace is not None else self.workspace
        )
        self.worker_id = worker_id or f"runtime-watchdog@{socket.gethostname()}"
        self.verification_service_enabled = bool(verification_service_enabled)
        self.verification_timeout_s = max(1.0, float(verification_timeout_s))
        self.registry = SessionRegistry(self.paths.sessions)
        self.result_writer = ResultWriter(self.workspace)
        self.watcher = WorkspaceWatcher(self.paths)
        self.scheduler = SessionScheduler()
        self.target_registry = TargetRuntimeRegistry()
        self.skill_registry = SkillRuntimeRegistry()
        self.perception_runtime = PerceptionRuntime(self.workspace, self.environment_workspace)
        self.health_monitor = HealthMonitor()
        self.failure_escalator = FailureEscalator()
        self.preflight = RuntimeCompatibilityPreflight(self.workspace, self.skill_registry)

    def run_once(self) -> bool:
        sessions_doc, targets_doc, skillruntimes_doc = self._load_runtime_documents()
        if self._expire_stale_workflow(sessions_doc):
            return True
        try:
            scheduled = self.scheduler.select_next(sessions_doc, targets_doc, skillruntimes_doc)
        except SessionScheduleError as exc:
            self.failure_escalator.handle(exc.session_id, exc, self.registry)
            return True
        if scheduled is None:
            return False
        session_id = scheduled.session.session_id
        if not self.registry.try_claim(session_id, self.worker_id):
            return False

        try:
            session = self.registry.get_session(session_id)
            _, targets_doc, skillruntimes_doc = self._load_runtime_documents()
            scheduled = self.scheduler.resolve_session(session, targets_doc, skillruntimes_doc)
            self.registry.mark_preflight_checking(session_id)
            session = self.registry.get_session(session_id)
            scheduled = self.scheduler.resolve_session(session, targets_doc, skillruntimes_doc)
            if self._is_gateway_session(scheduled):
                if not scheduled.target_spec.enabled:
                    raise SchemaValidationError(f"target {scheduled.target_id} is disabled")
                self._require_verifier_if_requested(session)
                self.registry.mark_running(session_id)
                session = self.registry.get_session(session_id)
                scheduled = self.scheduler.resolve_session(session, targets_doc, skillruntimes_doc)
                result = GatewaySessionRunner(
                    workspace=self.workspace,
                    session=session,
                    target_spec=scheduled.target_spec,
                    skillruntime_spec=scheduled.skillruntime_spec,
                ).run()
                self._finalize_execution(
                    session,
                    scheduled.target_spec,
                    scheduled.skillruntime_id,
                    result,
                )
                return True
            health_report = self.health_monitor.preflight(scheduled)
            if not health_report.ok:
                raise SchemaValidationError(health_report.summary())

            perception_plan = self.perception_runtime.resolve_and_check(scheduled)
            preflight_result = self.preflight.check(scheduled, perception_plan)
            if preflight_result.verdict == "rejected":
                result = SessionResult(
                    status="rejected",
                    success=False,
                    error_code="RUNTIME_PREFLIGHT_FAILED",
                    error_message=self._preflight_error_message(preflight_result),
                    metadata={"preflight": preflight_result.model_dump(mode="json", exclude_none=True)},
                )
                self.result_writer.write_lesson(
                    session,
                    scheduled.target_spec.id,
                    scheduled.skillruntime_id,
                    "preflight_checking",
                    result.error_code,
                    result.error_message or "runtime compatibility preflight failed",
                    preflight_result.model_dump(mode="json", exclude_none=True),
                )
                self.registry.mark_rejected(session_id, result)
                return True

            self._write_preflight_metadata(session_id, preflight_result)
            self._require_verifier_if_requested(session)

            self.registry.mark_running(session_id)
            session = self.registry.get_session(session_id)
            scheduled = self.scheduler.resolve_session(session, targets_doc, skillruntimes_doc)
            target_endpoint = session.routing.target_endpoint or scheduled.target_spec.runtime.target_endpoint
            target = self.target_registry.build(scheduled.target_spec, target_endpoint=target_endpoint)
            policy_client = None
            runner = None
            cleanup_in_background = False
            try:
                if scheduled.skillruntime_spec.runtime_kind == "policy":
                    policy_client = self._build_policy_client(session, scheduled.target_spec)
                runtime = self.skill_registry.build(scheduled.skillruntime_spec.runtime)
                runner = SessionRunner(
                    session=session,
                    target_spec=scheduled.target_spec,
                    skillruntime_spec=scheduled.skillruntime_spec,
                    adapter_plan=preflight_result.adapter_plan,
                    target=target,
                    skill_runtime=runtime,
                    policy_client=policy_client,
                    perception_runtime=self.perception_runtime,
                    perception_plan=perception_plan,
                    target_tool_manifest=preflight_result.target_tool_manifest,
                )
                thread_handle = RunnerThreadHandle(runner)
                thread_handle.start()
                while not thread_handle.done:
                    thread_handle.snapshot()
                    if thread_handle.elapsed_s() >= float(session.timeouts.execute_timeout_s):
                        result = SessionResult(
                            status="timed_out",
                            success=False,
                            error_code="EXECUTION_TIMEOUT",
                            error_message=(
                                "session exceeded execute_timeout_s="
                                f"{session.timeouts.execute_timeout_s}"
                            ),
                            metadata={
                                "timeout_s": session.timeouts.execute_timeout_s,
                                "runner_snapshot": thread_handle.snapshot(),
                                "cleanup": "best_effort_threaded",
                            },
                        )
                        thread_handle.request_cancel_and_close("execution timeout")
                        cleanup_in_background = True
                        self._close_policy_client(policy_client)
                        self._finalize_execution(
                            session,
                            scheduled.target_spec,
                            scheduled.skillruntime_id,
                            result,
                            initial_observation=(runner.initial_observation if runner is not None else None),
                            final_observation=(runner.final_observation if runner is not None else None),
                            initial_observed_at=(runner.initial_observed_at if runner is not None else None),
                            final_observed_at=(runner.final_observed_at if runner is not None else None),
                        )
                        return True
                    self._sleep_runner_poll_interval(session)
                if thread_handle.exception is not None:
                    raise thread_handle.exception
                result = thread_handle.result
                if result is None:
                    raise RuntimeError("runner thread finished without a result")
            finally:
                self._close_policy_client(policy_client)
                if cleanup_in_background:
                    pass
                elif runner is not None:
                    runner.close()
                else:
                    target.close()

            self._finalize_execution(
                session,
                scheduled.target_spec,
                scheduled.skillruntime_id,
                result,
                initial_observation=(runner.initial_observation if runner is not None else None),
                final_observation=(runner.final_observation if runner is not None else None),
                initial_observed_at=(runner.initial_observed_at if runner is not None else None),
                final_observed_at=(runner.final_observed_at if runner is not None else None),
            )
            return True
        except Exception as exc:
            self.failure_escalator.handle(session_id, exc, self.registry)
            return True

    def _load_runtime_documents(self) -> tuple[SessionsDocument, TargetsDocument, SkillRuntimeDocument]:
        try:
            sessions_doc = SessionsDocument.model_validate(read_yaml_block(self.paths.sessions))
            targets_doc = TargetsDocument.model_validate(read_yaml_block(self.paths.targets))
            skillruntimes_doc = SkillRuntimeDocument.model_validate(read_yaml_block(self.paths.skillruntimes))
            return sessions_doc, targets_doc, skillruntimes_doc
        except ValidationError as exc:
            raise SchemaValidationError(str(exc)) from exc

    def _load_registries(self) -> tuple[TargetsDocument, SkillRuntimeDocument]:
        try:
            targets_doc = TargetsDocument.model_validate(read_yaml_block(self.paths.targets))
            skillruntimes_doc = SkillRuntimeDocument.model_validate(read_yaml_block(self.paths.skillruntimes))
            return targets_doc, skillruntimes_doc
        except ValidationError as exc:
            raise SchemaValidationError(str(exc)) from exc

    def _build_policy_client(self, session, target_spec):
        action_cfg = target_spec.config.get("action", {})
        action_dim = target_spec.config.get("action_dim", action_cfg.get("action_dim", 7))
        chunk_size = target_spec.config.get("chunk_size", action_cfg.get("chunk_size", 4))
        return build_policy_client(
            session.routing.policy_endpoint or "dummy://local",
            timeout_s=session.timeouts.policy_timeout_s,
            action_dim=int(action_dim),
            chunk_size=int(chunk_size),
        )

    def _is_gateway_session(self, scheduled) -> bool:
        return (
            scheduled.skillruntime_spec.runtime == "ForgeGatewaySkillRuntime"
            or scheduled.target_spec.runtime.target_runtime == "ForgeGatewayRuntime"
        )

    def _close_policy_client(self, policy_client) -> None:
        if policy_client is None:
            return
        try:
            policy_client.close()
        except Exception:
            pass

    def _sleep_runner_poll_interval(self, session) -> None:
        import time

        timeout_s = float(session.timeouts.execute_timeout_s)
        time.sleep(max(0.01, min(0.05, timeout_s / 10.0)))

    def _preflight_error_message(self, preflight_result) -> str:
        if not preflight_result.missing_items:
            return "runtime compatibility preflight failed"
        return "; ".join(
            f"{item.code}: {item.field} expected {item.expected}"
            + (f", found {item.found}" if item.found is not None else "")
            for item in preflight_result.missing_items
        )

    def _write_preflight_metadata(self, session_id: str, preflight_result) -> None:
        document = self.registry.load()
        for session in document.sessions:
            if session.session_id != session_id:
                continue
            metadata = dict(session.result.metadata)
            metadata["preflight"] = preflight_result.model_dump(mode="json", exclude_none=True)
            session.result.metadata = metadata
            self.registry.save(document)
            return

    def _require_verifier_if_requested(self, session) -> None:
        if (
            session.verification.mode in {"enforce", "recovery"}
            and not self.verification_service_enabled
        ):
            raise SchemaValidationError(
                "VERIFICATION_SERVICE_DISABLED: non-off session requires the Agent verifier service"
            )

    def _finalize_execution(
        self,
        session,
        target_spec,
        skillruntime_id: str,
        result: SessionResult,
        *,
        initial_observation=None,
        final_observation=None,
        initial_observed_at=None,
        final_observed_at=None,
    ) -> None:
        """Persist execution facts before semantic verification can mutate task state."""
        if result.execution is None:
            result.execution = self._generic_execution_record(
                session,
                skillruntime_id,
                result,
            )
        self.registry.mark_finalizing(session.session_id)
        result = self.result_writer.write_episode(
            session,
            target_spec,
            skillruntime_id,
            result,
        )
        self.result_writer.write_session_history(session, target_spec, result)
        if session.verification.mode == "off":
            self.registry.mark_finished(session.session_id, result)
            return
        self.result_writer.write_verification_bundle(
            session,
            target_spec,
            skillruntime_id,
            result,
            environment_workspace=self.environment_workspace,
            initial_observation=initial_observation,
            final_observation=final_observation,
            initial_observed_at=initial_observed_at,
            final_observed_at=final_observed_at,
        )
        if session.verification.mode == "audit" and not self.verification_service_enabled:
            message = "semantic verifier service is disabled; audit verdict was not produced"
            result.verification.status = "error"
            result.verification.error = message
            final_status = self._execution_terminal_status(result)
            result.status = final_status.value
            result.success = final_status == SessionStatus.SUCCEEDED
            self.registry.mark_finished(session.session_id, result)
            finished = self.registry.get_session(session.session_id)
            self.result_writer.write_verification_result(finished, finished.result)
            self.result_writer.write_lesson(
                finished,
                finished.target_ref.removeprefix("target://"),
                finished.skillruntime_ref.removeprefix("skillruntime://"),
                "agent_verification",
                "VERIFICATION_SERVICE_DISABLED",
                message,
                {"verification_mode": "audit"},
            )
            return
        self.registry.mark_awaiting_verification(session.session_id, result)

    @staticmethod
    def _generic_execution_record(session, skillruntime_id: str, result: SessionResult) -> ExecutionRecord:
        raw_status = str(result.status or ("succeeded" if result.success else "failed"))
        status = raw_status if raw_status in {
            "queued", "sent", "running", "succeeded", "failed", "timed_out", "cancelled"
        } else "unknown"
        error = None
        if result.error_code or result.error_message:
            error = ExecutionError(code=result.error_code, message=result.error_message or "")
        return ExecutionRecord(
            runtime=skillruntime_id,
            session_id=session.session_id,
            command_id=f"paos_{session.session_id}",
            status=status,
            result_semantics="runtime_completed",
            timeline=ExecutionTimeline(terminal_observed_at=datetime.now(timezone.utc)),
            outputs={
                key: value
                for key, value in {
                    "num_steps": result.num_steps,
                    "return_value": result.return_value,
                    "mean_policy_latency_ms": result.mean_policy_latency_ms,
                    "trace_path": result.trace_path,
                }.items()
                if value is not None
            },
            error=error,
        )

    def _expire_stale_workflow(self, sessions_doc: SessionsDocument) -> bool:
        """Fail closed when the Agent-owned verifier or Planner stops progressing."""
        now = utc_now()
        verifier_active = any(
            session.status == SessionStatus.VERIFYING
            for session in sessions_doc.sessions
        )
        for session in sessions_doc.sessions:
            if session.status in {
                SessionStatus.AWAITING_VERIFICATION,
                SessionStatus.VERIFYING,
            }:
                updated_at = session.updated_at
                if session.status == SessionStatus.AWAITING_VERIFICATION and verifier_active:
                    continue
                if updated_at is None or (now - updated_at).total_seconds() < self.verification_timeout_s:
                    continue
                if session.status == SessionStatus.AWAITING_VERIFICATION and not self.registry.try_claim_verification(
                    session.session_id,
                    self.worker_id,
                ):
                    continue
                current = self.registry.get_session(session.session_id)
                result = current.result.model_copy(deep=True)
                message = (
                    "semantic verification did not complete within "
                    f"{self.verification_timeout_s:g}s"
                )
                result.verification.status = "error"
                result.verification.error = message
                if current.verification.mode == "audit":
                    final_status = self._execution_terminal_status(result)
                else:
                    final_status = SessionStatus.FAILED
                    result.error_code = "VERIFICATION_ORCHESTRATION_TIMEOUT"
                    result.error_message = message
                self.registry.mark_verification_finished(
                    current.session_id,
                    result,
                    final_status,
                )
                self.result_writer.write_lesson(
                    current,
                    current.target_ref.removeprefix("target://"),
                    current.skillruntime_ref.removeprefix("skillruntime://"),
                    "agent_verification",
                    "VERIFICATION_ORCHESTRATION_TIMEOUT",
                    message,
                    {"verification_mode": current.verification.mode},
                )
                finished = self.registry.get_session(current.session_id)
                self.result_writer.write_verification_result(finished, finished.result)
                return True
            if session.status == SessionStatus.AWAITING_REPLAN:
                raw = session.result.metadata.get("recovery_request")
                if not isinstance(raw, dict) or not raw.get("deadline"):
                    continue
                request = RecoveryRequest.model_validate(raw)
                if now < request.deadline:
                    continue
                message = "Agent Planner did not create a recovery child before the deadline."
                if self.registry.mark_replan_failed(
                    session.session_id,
                    error_code="VERIFICATION_REPLAN_TIMEOUT",
                    error_message=message,
                ):
                    self.result_writer.write_lesson(
                        session,
                        session.target_ref.removeprefix("target://"),
                        session.skillruntime_ref.removeprefix("skillruntime://"),
                        "agent_recovery",
                        "VERIFICATION_REPLAN_TIMEOUT",
                        message,
                        request.model_dump(mode="json"),
                    )
                    finished = self.registry.get_session(session.session_id)
                    self.result_writer.write_verification_result(finished, finished.result)
                return True
        return False

    @staticmethod
    def _execution_terminal_status(result: SessionResult) -> SessionStatus:
        raw = result.execution.status if result.execution is not None else result.status
        return {
            "succeeded": SessionStatus.SUCCEEDED,
            "failed": SessionStatus.FAILED,
            "timed_out": SessionStatus.TIMED_OUT,
            "cancelled": SessionStatus.CANCELLED,
        }.get(str(raw), SessionStatus.FAILED)
