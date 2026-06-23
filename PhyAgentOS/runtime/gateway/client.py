"""HTTP client for Forge Gateway Agent-facing MVP+ APIs."""

from __future__ import annotations

from typing import Any

import httpx


class ForgeGatewayError(RuntimeError):
    """Raised when the Forge Gateway API rejects or fails a request."""


class ForgeGatewayClient:
    def __init__(self, base_url: str, *, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = max(0.1, float(timeout_s))

    def capabilities(self) -> dict[str, Any]:
        return self._get("/agent/runtime/capabilities")

    def runtime_status(self) -> dict[str, Any]:
        return self._get("/agent/runtime/status")

    def runtime_context(self) -> dict[str, Any]:
        return self._get("/agent/runtime/context")

    def reset_runtime(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._post("/agent/runtime/reset", {"inputs": inputs or {}})

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/agent/sessions", payload)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._get(f"/agent/sessions/{session_id}")

    def cancel_session(self, session_id: str, reason: str = "paos_requested") -> dict[str, Any]:
        return self._post(f"/agent/sessions/{session_id}/cancel", {"reason": reason})

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self.base_url}{path}", timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise ForgeGatewayError(f"Forge Gateway GET {path} failed: {exc}") from exc
        return self._decode(response, path)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(f"{self.base_url}{path}", json=payload, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise ForgeGatewayError(f"Forge Gateway POST {path} failed: {exc}") from exc
        return self._decode(response, path)

    def _decode(self, response: httpx.Response, path: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ForgeGatewayError(
                f"Forge Gateway {path} returned non-JSON response: HTTP {response.status_code}"
            ) from exc
        if response.status_code >= 400 or data.get("ok") is False:
            message = data.get("msg") or data.get("message") or response.text
            raise ForgeGatewayError(f"Forge Gateway {path} rejected request: {message}")
        if not isinstance(data, dict):
            raise ForgeGatewayError(f"Forge Gateway {path} returned invalid payload")
        return data
