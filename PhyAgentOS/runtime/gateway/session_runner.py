"""Run one PAOS runtime session through Forge Gateway MVP+ APIs."""

from __future__ import annotations

import time
from typing import Any

from PhyAgentOS.runtime.gateway.client import ForgeGatewayClient, ForgeGatewayError
from PhyAgentOS.runtime.schemas import SessionResult, SessionSpec, SkillRuntimeSpec, TargetSpec

_TERMINAL_GATEWAY_STATUSES = {"succeeded", "failed", "cancelled"}


class GatewaySessionRunner:
    """Bridge a PAOS SessionSpec to a single Forge Gateway action session.

    This is the Phase-3 compatibility path for the existing watchdog +
    SESSIONS.md queue. A future Agent command adapter should live beside this
    module and call ForgeGatewayClient directly for capabilities, action
    sessions, reset, cancel, and context without carrying PAOS target/runtime
    execution fields through the bridge.
    """

    def __init__(
        self,
        *,
        session: SessionSpec,
        target_spec: TargetSpec,
        skillruntime_spec: SkillRuntimeSpec,
        client: ForgeGatewayClient | None = None,
    ):
        self.session = session
        self.target_spec = target_spec
        self.skillruntime_spec = skillruntime_spec
        self.client = client or ForgeGatewayClient(
            self._gateway_endpoint(),
            timeout_s=max(1.0, float(session.timeouts.policy_timeout_s)),
        )

    def run(self) -> SessionResult:
        payload = self._build_payload()
        created = self.client.create_session(payload)
        deadline = time.monotonic() + float(self.session.timeouts.execute_timeout_s)
        poll_interval_s = self._poll_interval_s()
        last_response = created

        while True:
            status = self._session_status(last_response)
            if status in _TERMINAL_GATEWAY_STATUSES:
                context = self._safe_runtime_context()
                return self._to_result(status, last_response, context)
            if time.monotonic() >= deadline:
                cancel_response = self._safe_cancel("execution timeout")
                return SessionResult(
                    status="timed_out",
                    success=False,
                    error_code="GATEWAY_EXECUTION_TIMEOUT",
                    error_message=(
                        "Forge Gateway session exceeded execute_timeout_s="
                        f"{self.session.timeouts.execute_timeout_s}"
                    ),
                    metadata={
                        "gateway": {
                            "create_response": created,
                            "last_response": last_response,
                            "cancel_response": cancel_response,
                        },
                        "task_status": "unknown",
                    },
                )
            time.sleep(poll_interval_s)
            last_response = self.client.get_session(payload["session_id"])

    def _gateway_endpoint(self) -> str:
        endpoint = self.session.routing.target_endpoint or self.target_spec.runtime.target_endpoint
        if not endpoint:
            raise ForgeGatewayError(
                "Forge Gateway session requires routing.target_endpoint or target.runtime.target_endpoint"
            )
        if not endpoint.startswith(("http://", "https://")):
            raise ForgeGatewayError(f"Forge Gateway endpoint must be HTTP(S): {endpoint}")
        return endpoint

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
            if key in {"action_type", "action", "type", "command_id", "instruction", "source", "inputs"}:
                continue
            payload[key] = value
        return payload

    def _poll_interval_s(self) -> float:
        raw = self.session.runtime_hints.gateway_action.get("poll_interval_s", 0.5)
        try:
            return max(0.1, min(5.0, float(raw)))
        except (TypeError, ValueError):
            return 0.5

    def _session_status(self, response: dict[str, Any]) -> str:
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        session = data.get("session") if isinstance(data.get("session"), dict) else {}
        status = session.get("status") or data.get("status")
        return str(status or "unknown")

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

    def _to_result(
        self,
        gateway_status: str,
        response: dict[str, Any],
        context: dict[str, Any] | None,
    ) -> SessionResult:
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        commands = data.get("commands") if isinstance(data.get("commands"), list) else []
        command = commands[0] if commands and isinstance(commands[0], dict) else {}
        outputs = command.get("outputs") if isinstance(command.get("outputs"), dict) else {}
        message = command.get("message") or data.get("msg") or ""
        success = gateway_status == "succeeded"
        return SessionResult(
            status=gateway_status,
            success=success,
            error_code=None if success else "GATEWAY_SESSION_FAILED",
            error_message=None if success else str(message or f"Gateway session {gateway_status}"),
            metadata={
                "gateway": {
                    "status": gateway_status,
                    "response": response,
                    "context": context,
                    "outputs": outputs,
                },
                "task_status": "not_verified" if success else "unknown",
            },
        )
