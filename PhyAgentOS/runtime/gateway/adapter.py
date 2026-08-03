"""PhyAgentOS-owned adapter for Forge Gateway 1.0 Agent sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PhyAgentOS.runtime.gateway.client import ForgeGatewayClient, ForgeGatewayError
from PhyAgentOS.runtime.gateway.evidence import ForgeEvidenceWriter
from PhyAgentOS.runtime.gateway.observation import (
    ForgeObservationCollector,
    ForgeObservationError,
    ObservationSnapshot,
)
from PhyAgentOS.runtime.schemas import (
    EvidenceBundle,
    ExecutionError,
    ExecutionRecord,
    ExecutionTimeline,
    SessionResult,
    SessionSpec,
    SkillRuntimeSpec,
    TargetSpec,
    VerificationState,
)

FORGE_GATEWAY_API_VERSION = "paos-forge-gateway-mvp-plus.v1"
_TERMINAL_GATEWAY_STATUSES = {"succeeded", "failed", "cancelled"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ForgeAdapterOutcome:
    result: SessionResult
    evidence_bundle: EvidenceBundle | None = None
    evidence_bundle_ref: str | None = None


class ForgeAdapter:
    """Normalize Gateway execution and WebSocket observations into PAOS contracts."""

    def __init__(
        self,
        *,
        workspace: str | Path,
        session: SessionSpec,
        target_spec: TargetSpec,
        skillruntime_spec: SkillRuntimeSpec,
        client: ForgeGatewayClient | None = None,
        collector_factory=None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.session = session
        self.target_spec = target_spec
        self.skillruntime_spec = skillruntime_spec
        self.endpoint = self._gateway_endpoint()
        self.client = client or ForgeGatewayClient(
            self.endpoint,
            timeout_s=max(1.0, float(session.timeouts.policy_timeout_s)),
        )
        self.collector_factory = collector_factory or ForgeObservationCollector

    def run(self) -> ForgeAdapterOutcome:
        payload = self._build_payload()
        capabilities = self._capabilities(payload["action_type"])
        action_capability = capabilities["actions"][payload["action_type"]]
        verification_enabled = self.session.verification.mode != "off"
        capture_errors: list[str] = []
        collector: ForgeObservationCollector | None = None
        before: ObservationSnapshot | None = None
        after: ObservationSnapshot | None = None
        terminal_observed_at: datetime | None = None
        required_sources: list[str] = []
        required_kinds = list(self.session.verification.evidence_policy.required_kinds)

        if verification_enabled:
            policy = self.session.verification.evidence_policy
            if policy.minimum_association == "authoritative":
                raise ForgeGatewayError(
                    "FORGE_EVIDENCE_ASSOCIATION_UNSUPPORTED: Gateway 1.0 has no authoritative evidence API"
                )
            required_sources = self._required_image_sources(required_kinds)
            cfg = self._evidence_config()
            association_policy = cfg.get(
                "association_quality",
                cfg.get("association_policy", "best_effort"),
            )
            if association_policy != "best_effort":
                raise ForgeGatewayError(
                    "FORGE_EVIDENCE_ASSOCIATION_UNSUPPORTED: Gateway 1.0 evidence is best_effort"
                )
            collector = self.collector_factory(
                self.endpoint,
                required_image_sources=required_sources,
                max_artifact_bytes=int(cfg.get("max_artifact_bytes", 8 * 1024 * 1024)),
                require_state="robot_state" in required_kinds,
                connection_timeout_s=float(cfg.get("connection_timeout_s", 2.0)),
            )
            collector.start()
            try:
                before = collector.wait_for_before(float(cfg.get("capture_timeout_s", 5.0)))
            except ForgeObservationError as exc:
                if self.session.verification.mode != "audit":
                    collector.close()
                    raise ForgeGatewayError(str(exc)) from exc
                capture_errors.append(str(exc))

        created: dict[str, Any] | None = None
        last_response: dict[str, Any] | None = None
        cancel_response: dict[str, Any] | None = None
        gateway_status = "unknown"
        timeout_error: ExecutionError | None = None
        try:
            created = self.client.create_session(payload)
            last_response = created
            _, created_command = self._validated_session_command(
                created, payload["session_id"], payload["command_id"]
            )
            self._validate_action_identity(created_command, payload, action_capability)
            deadline = time.monotonic() + float(self.session.timeouts.execute_timeout_s)
            while True:
                session_data, command_data = self._validated_session_command(
                    last_response,
                    payload["session_id"],
                    payload["command_id"],
                )
                self._validate_action_identity(command_data, payload, action_capability)
                gateway_status = str(session_data.get("status") or "unknown")
                command_status = str(command_data.get("status") or "unknown")
                if gateway_status in _TERMINAL_GATEWAY_STATUSES:
                    if command_status not in _TERMINAL_GATEWAY_STATUSES:
                        raise ForgeGatewayError(
                            "Gateway returned terminal session with non-terminal command"
                        )
                    if command_status != gateway_status:
                        raise ForgeGatewayError(
                            f"Gateway session/command terminal mismatch: {gateway_status}/{command_status}"
                        )
                    terminal_observed_at = _utc_now()
                    break
                if time.monotonic() >= deadline:
                    terminal_observed_at = _utc_now()
                    gateway_status = "timed_out"
                    timeout_error = ExecutionError(
                        code="GATEWAY_EXECUTION_TIMEOUT",
                        message=(
                            "Forge Gateway session exceeded execute_timeout_s="
                            f"{self.session.timeouts.execute_timeout_s}"
                        ),
                    )
                    cancel_response = self._safe_cancel("execution timeout")
                    break
                time.sleep(self._poll_interval_s())
                last_response = self.client.get_session(payload["session_id"])

            if collector is not None and before is not None and terminal_observed_at is not None:
                try:
                    after = collector.wait_for_after(
                        before,
                        terminal_observed_at=terminal_observed_at,
                        timeout_s=float(
                            self._evidence_config().get("post_capture_timeout_s", 5.0)
                        ),
                    )
                except ForgeObservationError as exc:
                    capture_errors.append(str(exc))
        finally:
            if collector is not None:
                capture_errors.extend(collector.errors)
                collector.close()

        context = self._safe_runtime_context()
        session_data, command_data = self._last_known_session_command(
            last_response or {}, payload["session_id"], payload["command_id"]
        )
        execution = self._execution_record(
            payload=payload,
            capabilities=capabilities,
            action_capability=action_capability,
            gateway_status=gateway_status,
            session_data=session_data,
            command_data=command_data,
            terminal_observed_at=terminal_observed_at,
            error=timeout_error,
        )
        result = self._session_result(
            execution=execution,
            created=created,
            last_response=last_response,
            cancel_response=cancel_response,
            context=context,
        )

        bundle: EvidenceBundle | None = None
        bundle_ref: str | None = None
        if verification_enabled:
            bundle, bundle_ref = ForgeEvidenceWriter(
                self.workspace,
                payload["session_id"],
                payload["command_id"],
            ).write(
                before=before,
                after=after,
                terminal_observed_at=terminal_observed_at,
                required_sources=required_sources,
                required_kinds=required_kinds,
                errors=capture_errors,
            )
            result.verification = VerificationState(status="pending", bundle_ref=bundle_ref)
            result.metadata["evidence"] = {
                "bundle_ref": bundle_ref,
                "complete": bundle.quality.complete,
                "association_quality": bundle.quality.association_quality,
            }
        return ForgeAdapterOutcome(result, bundle, bundle_ref)

    def _gateway_endpoint(self) -> str:
        endpoint = self.session.routing.target_endpoint or self.target_spec.runtime.target_endpoint
        if not endpoint:
            raise ForgeGatewayError(
                "Forge Gateway session requires routing.target_endpoint or target.runtime.target_endpoint"
            )
        if not endpoint.startswith(("http://", "https://")):
            raise ForgeGatewayError(f"Forge Gateway endpoint must be HTTP(S): {endpoint}")
        return endpoint.rstrip("/")

    def _build_payload(self) -> dict[str, Any]:
        action = dict(self.session.runtime_hints.gateway_action or {})
        action_type = action.get("action_type") or action.get("action") or action.get("type")
        if not isinstance(action_type, str) or not action_type:
            raise ForgeGatewayError("runtime_hints.gateway_action.action_type is required")
        inputs = action.get("inputs") or {}
        if not isinstance(inputs, dict):
            raise ForgeGatewayError("runtime_hints.gateway_action.inputs must be an object")
        payload: dict[str, Any] = {
            "session_id": self.session.session_id,
            "command_id": str(action.get("command_id") or f"cmd_{self.session.session_id}"),
            "action_type": action_type,
            "instruction": str(action.get("instruction") or self.session.task_description),
            "source": str(action.get("source") or "paos-agent"),
            "inputs": dict(inputs),
        }
        for key, value in action.items():
            if key in {
                "action_type",
                "action",
                "type",
                "command_id",
                "instruction",
                "source",
                "inputs",
                "poll_interval_s",
            }:
                continue
            payload[key] = value
        return payload

    def _capabilities(self, action_type: str) -> dict[str, Any]:
        response = self.client.capabilities()
        data = self._data(response)
        version = data.get("api_version")
        if version != FORGE_GATEWAY_API_VERSION:
            raise ForgeGatewayError(
                f"FORGE_GATEWAY_API_UNSUPPORTED: expected {FORGE_GATEWAY_API_VERSION}, got {version!r}"
            )
        supports = data.get("supports")
        required = ("sessions", "command_id", "runtime_context", "serial_actions_only")
        if not isinstance(supports, dict) or any(supports.get(key) is not True for key in required):
            raise ForgeGatewayError(
                "FORGE_GATEWAY_CAPABILITY_MISSING: sessions, command_id, runtime_context, "
                "and serial_actions_only are required"
            )
        actions = data.get("actions")
        if not isinstance(actions, dict) or not isinstance(actions.get(action_type), dict):
            raise ForgeGatewayError(f"FORGE_ACTION_UNSUPPORTED: {action_type}")
        return data

    def _required_image_sources(self, required_kinds: list[str]) -> list[str]:
        if "rgb_image" not in required_kinds:
            return []
        policy_sources = self.session.verification.evidence_policy.required_sources
        if policy_sources:
            return list(dict.fromkeys(policy_sources))
        config = self._evidence_config()
        configured = config.get("required_image_sources", config.get("evidence_sources", []))
        if isinstance(configured, list) and all(isinstance(value, str) for value in configured):
            sources = [value for value in configured if value]
            if sources:
                return list(dict.fromkeys(sources))
        context = self._data(self.client.runtime_context())
        readiness = context.get("readiness") if isinstance(context.get("readiness"), dict) else {}
        images = readiness.get("images") if isinstance(readiness.get("images"), dict) else {}
        sources = [str(source) for source in images]
        if not sources:
            raise ForgeGatewayError(
                "FORGE_EVIDENCE_CONFIGURATION_REQUIRED: configure target.config.verification.required_image_sources"
            )
        return sources

    def _evidence_config(self) -> dict[str, Any]:
        value = self.target_spec.config.get("verification", {})
        return dict(value) if isinstance(value, dict) else {}

    def _validated_session_command(
        self,
        response: dict[str, Any],
        session_id: str,
        command_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        session, command = self._last_known_session_command(response, session_id, command_id)
        if session.get("session_id") != session_id:
            raise ForgeGatewayError("Gateway response session_id does not match request")
        if command.get("command_id") != command_id:
            raise ForgeGatewayError("Gateway response command_id does not match request")
        if command.get("session_id") != session_id:
            raise ForgeGatewayError("Gateway command belongs to another session")
        if command.get("request_id") != command_id:
            raise ForgeGatewayError("Gateway command request_id does not match command_id")
        return session, command

    def _last_known_session_command(
        self,
        response: dict[str, Any],
        session_id: str,
        command_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        data = self._data(response)
        session = data.get("session") if isinstance(data.get("session"), dict) else {}
        candidates: list[dict[str, Any]] = []
        if isinstance(data.get("command"), dict):
            candidates.append(data["command"])
        if isinstance(data.get("commands"), list):
            candidates.extend(item for item in data["commands"] if isinstance(item, dict))
        command = next(
            (item for item in candidates if item.get("command_id") == command_id),
            candidates[0] if len(candidates) == 1 else {},
        )
        return dict(session), dict(command)

    @staticmethod
    def _validate_action_identity(
        command: dict[str, Any],
        payload: dict[str, Any],
        capability: dict[str, Any],
    ) -> None:
        expected = {
            "action_type": payload["action_type"],
            "policy_id": capability.get("policy_id"),
            "command": capability.get("command"),
        }
        for field, value in expected.items():
            if value is not None and command.get(field) != value:
                raise ForgeGatewayError(
                    f"Gateway command {field} does not match advertised action capability"
                )

    def _execution_record(
        self,
        *,
        payload: dict[str, Any],
        capabilities: dict[str, Any],
        action_capability: dict[str, Any],
        gateway_status: str,
        session_data: dict[str, Any],
        command_data: dict[str, Any],
        terminal_observed_at: datetime | None,
        error: ExecutionError | None,
    ) -> ExecutionRecord:
        status = gateway_status if gateway_status in {
            "queued", "sent", "running", "succeeded", "failed", "timed_out", "cancelled"
        } else "unknown"
        outputs = command_data.get("outputs") if isinstance(command_data.get("outputs"), dict) else {}
        if error is None and status == "failed":
            error = ExecutionError(
                code="GATEWAY_SESSION_FAILED",
                message=str(command_data.get("message") or session_data.get("message") or ""),
            )
        return ExecutionRecord(
            runtime="forge_gateway",
            session_id=payload["session_id"],
            command_id=payload["command_id"],
            gateway_api_version=str(capabilities.get("api_version")),
            action_type=payload["action_type"],
            policy_id=str(action_capability.get("policy_id") or "") or None,
            status=status,
            result_semantics=str(action_capability.get("result_semantics") or "command_completed"),
            completion=(
                dict(action_capability.get("completion"))
                if isinstance(action_capability.get("completion"), dict)
                else {}
            ),
            timeline=ExecutionTimeline(
                created_at=self._float_or_none(session_data.get("created_at")),
                updated_at=self._float_or_none(session_data.get("updated_at")),
                sent_at=self._float_or_none(command_data.get("sent_at")),
                terminal_observed_at=terminal_observed_at,
            ),
            outputs=dict(outputs),
            error=error,
        )

    def _session_result(
        self,
        *,
        execution: ExecutionRecord,
        created: dict[str, Any] | None,
        last_response: dict[str, Any] | None,
        cancel_response: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> SessionResult:
        success = execution.status == "succeeded"
        return SessionResult(
            status=execution.status,
            success=success,
            error_code=execution.error.code if execution.error is not None else None,
            error_message=execution.error.message if execution.error is not None else None,
            execution=execution,
            metadata={
                "gateway": {
                    "status": execution.status,
                    "create_response": created,
                    "last_response": last_response,
                    "cancel_response": cancel_response,
                    "context": context,
                    "outputs": execution.outputs,
                },
                "task_status": "not_verified" if success else "unknown",
            },
        )

    def _safe_runtime_context(self) -> dict[str, Any] | None:
        try:
            return self.client.runtime_context()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _safe_cancel(self, reason: str) -> dict[str, Any] | None:
        try:
            return self.client.cancel_session(self.session.session_id, reason=reason)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _poll_interval_s(self) -> float:
        raw = self.session.runtime_hints.gateway_action.get("poll_interval_s", 0.5)
        try:
            return max(0.1, min(5.0, float(raw)))
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def _data(response: dict[str, Any]) -> dict[str, Any]:
        data = response.get("data")
        return dict(data) if isinstance(data, dict) else dict(response)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
