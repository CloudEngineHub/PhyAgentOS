"""Best-effort Forge Gateway observation collection over WebSocket."""

from __future__ import annotations

import base64
import binascii
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse


class ForgeObservationError(RuntimeError):
    """Raised when Gateway evidence cannot be collected safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CapturedImage:
    source_id: str
    sequence: int
    captured_at: float | None
    received_at: datetime
    media_type: str
    data: bytes


@dataclass(frozen=True)
class CapturedState:
    received_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class ObservationSnapshot:
    captured_at: datetime
    images: dict[str, CapturedImage] = field(default_factory=dict)
    state: CapturedState | None = None


ConnectionFactory = Callable[[str, float], Any]


def _default_connection_factory(url: str, timeout_s: float) -> Any:
    try:
        import websocket
    except ImportError as exc:  # pragma: no cover - packaging/environment guard
        raise ForgeObservationError(
            "websocket-client is required for Forge verification evidence collection"
        ) from exc
    return websocket.create_connection(
        url,
        timeout=timeout_s,
        http_proxy_host=None,
        http_proxy_port=None,
    )


class ForgeObservationCollector:
    """Maintain the latest validated state and frame for each required source."""

    def __init__(
        self,
        base_url: str,
        *,
        required_image_sources: list[str],
        max_artifact_bytes: int,
        require_state: bool = False,
        connection_timeout_s: float = 2.0,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.required_image_sources = tuple(dict.fromkeys(required_image_sources))
        self.max_artifact_bytes = max(1, int(max_artifact_bytes))
        self.require_state = bool(require_state)
        self.connection_timeout_s = max(0.1, float(connection_timeout_s))
        self.connection_factory = connection_factory or _default_connection_factory
        self._condition = threading.Condition()
        self._latest_images: dict[str, CapturedImage] = {}
        self._latest_state: CapturedState | None = None
        self._errors: list[str] = []
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._connections: list[Any] = []

    @property
    def errors(self) -> list[str]:
        with self._condition:
            return list(self._errors)

    def start(self) -> None:
        if self._threads:
            return
        for name, path, handler in (
            ("images", "/ws/images", self._handle_image_message),
            ("state", "/ws/state", self._handle_state_message),
        ):
            thread = threading.Thread(
                target=self._receive_loop,
                args=(path, handler),
                name=f"paos-forge-{name}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            connections = list(self._connections)
            self._condition.notify_all()
        for connection in connections:
            try:
                connection.close()
            except Exception:
                pass
        for thread in self._threads:
            thread.join(timeout=2.0)

    def wait_for_before(self, timeout_s: float) -> ObservationSnapshot:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._condition:
            while not self._stop.is_set():
                if (
                    all(source in self._latest_images for source in self.required_image_sources)
                    and (not self.require_state or self._latest_state is not None)
                ):
                    return self._snapshot_locked()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(remaining, 0.2))
            missing = [
                source for source in self.required_image_sources if source not in self._latest_images
            ]
            requirements = [f"image:{source}" for source in missing]
            if self.require_state and self._latest_state is None:
                requirements.append("state:ws/state")
            raise ForgeObservationError(
                "FORGE_EVIDENCE_UNAVAILABLE: missing before sources: "
                + ", ".join(requirements or ["unknown"])
            )

    def wait_for_after(
        self,
        before: ObservationSnapshot,
        *,
        terminal_observed_at: datetime,
        timeout_s: float,
    ) -> ObservationSnapshot:
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._condition:
            while not self._stop.is_set():
                ready = True
                for source in self.required_image_sources:
                    current = self._latest_images.get(source)
                    previous = before.images.get(source)
                    if (
                        current is None
                        or previous is None
                        or current.sequence <= previous.sequence
                        or current.received_at < terminal_observed_at
                    ):
                        ready = False
                        break
                state_ready = not self.require_state or (
                    self._latest_state is not None
                    and self._latest_state.received_at >= terminal_observed_at
                )
                if ready and state_ready:
                    snapshot = self._snapshot_locked()
                    if (
                        snapshot.state is not None
                        and snapshot.state.received_at < terminal_observed_at
                    ):
                        snapshot = ObservationSnapshot(
                            captured_at=snapshot.captured_at,
                            images=snapshot.images,
                            state=None,
                        )
                    return snapshot
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(remaining, 0.2))
            missing: list[str] = []
            for source in self.required_image_sources:
                current = self._latest_images.get(source)
                previous = before.images.get(source)
                if current is None or previous is None or current.sequence <= previous.sequence:
                    missing.append(source)
            requirements = [f"image:{source}" for source in missing]
            if self.require_state and (
                self._latest_state is None
                or self._latest_state.received_at < terminal_observed_at
            ):
                requirements.append("state:ws/state")
            raise ForgeObservationError(
                "FORGE_EVIDENCE_UNAVAILABLE: missing fresh after sources: "
                + ", ".join(requirements or ["unknown"])
            )

    def latest_snapshot(self) -> ObservationSnapshot:
        with self._condition:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            captured_at=utc_now(),
            images=dict(self._latest_images),
            state=self._latest_state,
        )

    def _receive_loop(self, path: str, handler: Callable[[Any], None]) -> None:
        url = self._ws_url(path)
        while not self._stop.is_set():
            connection = None
            try:
                connection = self.connection_factory(url, self.connection_timeout_s)
                with self._condition:
                    self._connections.append(connection)
                while not self._stop.is_set():
                    raw = connection.recv()
                    if raw is None:
                        raise ForgeObservationError(f"Gateway WebSocket {path} closed")
                    handler(raw)
            except Exception as exc:
                if not self._stop.is_set():
                    self._record_error(f"{path}: {exc}")
                    self._stop.wait(0.1)
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                    with self._condition:
                        if connection in self._connections:
                            self._connections.remove(connection)

    def _handle_image_message(self, raw: Any) -> None:
        payload = self._parse_json(raw, "image")
        if payload.get("type") != "image":
            return
        source = payload.get("id")
        if not isinstance(source, str) or not source:
            self._record_error("image message has no source id")
            return
        if self.required_image_sources and source not in self.required_image_sources:
            return
        try:
            sequence = int(payload["seq"])
            if sequence < 0:
                raise ValueError("negative sequence")
            timestamp_raw = payload.get("timestamp")
            captured_at = float(timestamp_raw) if timestamp_raw is not None else None
            if captured_at is not None and not math.isfinite(captured_at):
                raise ValueError("non-finite timestamp")
            media_type = str(payload.get("content_type") or "")
            if not media_type.startswith("image/"):
                raise ValueError(f"unsupported media type: {media_type!r}")
            encoded = payload.get("data")
            if not isinstance(encoded, str):
                raise ValueError("image data must be base64 string")
            max_encoded = ((self.max_artifact_bytes + 2) // 3) * 4 + 4
            if len(encoded) > max_encoded:
                raise ValueError("encoded image exceeds configured artifact limit")
            data = base64.b64decode(encoded, validate=True)
            if not data or len(data) > self.max_artifact_bytes:
                raise ValueError("decoded image exceeds configured artifact limit")
            if not self._matches_media_type(data, media_type):
                raise ValueError("image bytes do not match declared media type")
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            self._record_error(f"invalid image message for {source}: {exc}")
            return

        image = CapturedImage(
            source_id=source,
            sequence=sequence,
            captured_at=captured_at,
            received_at=utc_now(),
            media_type=media_type,
            data=data,
        )
        with self._condition:
            previous = self._latest_images.get(source)
            if previous is not None and image.sequence <= previous.sequence:
                return
            self._latest_images[source] = image
            self._condition.notify_all()

    def _handle_state_message(self, raw: Any) -> None:
        payload = self._parse_json(raw, "state")
        state = CapturedState(received_at=utc_now(), payload=payload)
        with self._condition:
            self._latest_state = state
            self._condition.notify_all()

    def _parse_json(self, raw: Any, kind: str) -> dict[str, Any]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ForgeObservationError(f"{kind} WebSocket message must be text JSON")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ForgeObservationError(f"{kind} WebSocket message must be an object")
        return value

    def _record_error(self, message: str) -> None:
        with self._condition:
            self._errors.append(message)
            if len(self._errors) > 50:
                self._errors = self._errors[-50:]
            self._condition.notify_all()

    def _ws_url(self, path: str) -> str:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ForgeObservationError(f"unsupported Gateway URL: {self.base_url}")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        base_path = parsed.path.rstrip("/")
        return urlunparse((scheme, parsed.netloc, base_path + path, "", "", ""))

    @staticmethod
    def _matches_media_type(data: bytes, media_type: str) -> bool:
        normalized = media_type.lower().split(";", 1)[0].strip()
        if normalized in {"image/jpeg", "image/jpg"}:
            return data.startswith(b"\xff\xd8\xff")
        if normalized == "image/png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        if normalized == "image/webp":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        return False
