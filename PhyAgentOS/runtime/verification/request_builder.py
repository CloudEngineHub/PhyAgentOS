"""Resolve versioned runtime evidence into a model verification request."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PhyAgentOS.runtime.schemas import EvidenceBundle, SessionSpec


class VerificationEvidenceError(ValueError):
    """Raised when persisted evidence cannot support semantic verification."""


@dataclass(frozen=True)
class VerificationRequest:
    content: list[dict[str, Any]]
    bundle: dict[str, Any]
    artifact_paths: tuple[Path, ...]
    valid_evidence_refs: frozenset[str]


class VerificationRequestBuilder:
    def __init__(self, workspace: str | Path, *, max_image_bytes: int = 16 * 1024 * 1024):
        self.workspace = Path(workspace).expanduser().resolve()
        self.max_image_bytes = max(1, int(max_image_bytes))

    def build(self, session: SessionSpec) -> VerificationRequest:
        wrapper = self._load_wrapper(session)
        version = wrapper.get("version")
        if version == "agent_session_verification_v3":
            return self._build_v3(session, wrapper)
        if version == "agent_session_verification_v2":
            return self._build_legacy(session, wrapper)
        raise VerificationEvidenceError(f"unsupported verification bundle version: {version!r}")

    def _build_v3(
        self,
        session: SessionSpec,
        wrapper: dict[str, Any],
    ) -> VerificationRequest:
        evidence_ref = wrapper.get("evidence_bundle_ref")
        if isinstance(evidence_ref, str) and evidence_ref:
            evidence_path = self._workspace_path(evidence_ref)
            try:
                evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence = EvidenceBundle.model_validate(evidence_payload)
            except Exception as exc:
                raise VerificationEvidenceError(
                    f"invalid public evidence bundle: {evidence_ref}"
                ) from exc
            if evidence.session_id != session.session_id:
                raise VerificationEvidenceError(
                    "evidence bundle belongs to a different session"
                )
            if session.result.execution is not None and (
                evidence.command_id != session.result.execution.command_id
            ):
                raise VerificationEvidenceError(
                    "evidence bundle command_id does not match execution record"
                )
            minimum = session.verification.evidence_policy.minimum_association
            if minimum == "authoritative" and (
                evidence.quality.association_quality != "authoritative"
            ):
                raise VerificationEvidenceError(
                    "evidence association quality is below task policy"
                )
            if not evidence.quality.complete:
                raise VerificationEvidenceError(
                    "evidence bundle is incomplete: "
                    + ", ".join(evidence.quality.missing_requirements or ["unknown"])
                )
            self._validate_required_evidence(session, evidence)
            self._validate_capture_window(evidence)
            return self._content_from_public_bundle(session, wrapper, evidence, evidence_path)
        raise VerificationEvidenceError(
            "agent_session_verification_v3 requires evidence_bundle_ref"
        )

    def _content_from_public_bundle(
        self,
        session: SessionSpec,
        wrapper: dict[str, Any],
        evidence: EvidenceBundle,
        evidence_path: Path,
    ) -> VerificationRequest:
        paths: list[Path] = [evidence_path]
        structured: dict[str, Any] = {}
        images: list[tuple[str, str, bytes]] = []
        artifact_ids = {artifact.artifact_id for artifact in evidence.artifacts}
        for artifact in evidence.artifacts:
            path = self._workspace_path(artifact.uri)
            if not path.is_file():
                raise VerificationEvidenceError(
                    f"verification artifact does not exist: {artifact.uri}"
                )
            data = path.read_bytes()
            if len(data) != artifact.byte_size:
                raise VerificationEvidenceError(
                    f"verification artifact size mismatch: {artifact.artifact_id}"
                )
            if hashlib.sha256(data).hexdigest() != artifact.sha256:
                raise VerificationEvidenceError(
                    f"verification artifact digest mismatch: {artifact.artifact_id}"
                )
            paths.append(path)
            if artifact.media_type.startswith("image/"):
                if not data or len(data) > self.max_image_bytes:
                    raise VerificationEvidenceError(
                        f"verification image exceeds size limit: {artifact.artifact_id}"
                    )
                if not self._matches_media_type(data, artifact.media_type):
                    raise VerificationEvidenceError(
                        "verification image bytes do not match media type: "
                        f"{artifact.artifact_id}"
                    )
                images.append((artifact.artifact_id, artifact.media_type, data))
            elif artifact.media_type == "application/json":
                try:
                    structured[artifact.artifact_id] = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise VerificationEvidenceError(
                        f"verification JSON artifact is invalid: {artifact.artifact_id}"
                    ) from exc

        required_refs = set()
        for kind in session.verification.evidence_policy.required_kinds:
            required_refs.update(
                artifact.artifact_id
                for artifact in evidence.artifacts
                if artifact.kind == kind
            )
        if session.verification.evidence_policy.required_kinds and not required_refs:
            raise VerificationEvidenceError("required evidence kinds are unavailable")

        context = {
            "task_verification_contract": session.verification.model_dump(mode="json"),
            "execution_record": (
                session.result.execution.model_dump(mode="json")
                if session.result.execution is not None
                else wrapper.get("execution_record")
            ),
            "evidence_bundle": evidence.model_dump(mode="json"),
            "structured_evidence": structured,
            "environment_md": wrapper.get("environment_md", ""),
            "history_md": wrapper.get("history_md", ""),
            "lessons_md": wrapper.get("lessons_md", ""),
            "valid_evidence_refs": sorted(artifact_ids),
        }
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Determine whether the task success criteria are semantically satisfied. "
                    "Use only the supplied execution facts and evidence.\n\n"
                    + json.dumps(context, ensure_ascii=False, indent=2)
                ),
            }
        ]
        for artifact_id, media_type, data in images:
            content.extend(
                [
                    {"type": "text", "text": f"EVIDENCE_ARTIFACT: {artifact_id}"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,"
                            + base64.b64encode(data).decode("ascii")
                        },
                    },
                ]
            )
        return VerificationRequest(
            content,
            wrapper,
            tuple(paths),
            frozenset(artifact_ids),
        )

    def _build_legacy(
        self,
        session: SessionSpec,
        wrapper: dict[str, Any],
    ) -> VerificationRequest:
        return self._build_legacy_paths(session, wrapper)

    def _build_legacy_paths(
        self,
        session: SessionSpec,
        wrapper: dict[str, Any],
    ) -> VerificationRequest:
        initial = wrapper.get("initial_rgb_paths")
        final = wrapper.get("final_rgb_paths")
        if not isinstance(initial, list) or not initial:
            raise VerificationEvidenceError("paired before RGB evidence is unavailable")
        if not isinstance(final, list) or not final:
            raise VerificationEvidenceError("paired after RGB evidence is unavailable")
        relative_paths = [str(value) for value in [*initial, *final]]
        paths: list[Path] = []
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "task_verification_contract": session.verification.model_dump(
                            mode="json"
                        ),
                        "execution_record": wrapper.get("execution_record"),
                        "runtime_result": wrapper.get("runtime_result"),
                        "environment_md": wrapper.get("environment_md", ""),
                        "history_md": wrapper.get("history_md", ""),
                        "lessons_md": wrapper.get("lessons_md", ""),
                        "legacy_evidence_refs": relative_paths,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        ]
        for relative in relative_paths:
            path = self._workspace_path(relative)
            if not path.is_file():
                raise VerificationEvidenceError(
                    f"verification RGB evidence does not exist: {relative}"
                )
            data = path.read_bytes()
            if not data or len(data) > self.max_image_bytes:
                raise VerificationEvidenceError(
                    f"verification RGB evidence has invalid size: {relative}"
                )
            paths.append(path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,"
                        + base64.b64encode(data).decode("ascii")
                    },
                }
            )
        return VerificationRequest(
            content,
            wrapper,
            tuple(paths),
            frozenset(relative_paths),
        )

    @staticmethod
    def _validate_required_evidence(
        session: SessionSpec,
        evidence: EvidenceBundle,
    ) -> None:
        ids = [artifact.artifact_id for artifact in evidence.artifacts]
        if len(ids) != len(set(ids)):
            raise VerificationEvidenceError("evidence artifact IDs must be unique")
        policy = session.verification.evidence_policy
        for kind in policy.required_kinds:
            for phase in ("before", "after"):
                candidates = [
                    item
                    for item in evidence.artifacts
                    if item.kind == kind and item.phase == phase
                ]
                if not candidates:
                    raise VerificationEvidenceError(
                        f"required evidence is unavailable: {phase}:{kind}"
                    )
                if "image" in kind:
                    for source in policy.required_sources:
                        if not any(item.source_id == source for item in candidates):
                            raise VerificationEvidenceError(
                                "required evidence source is unavailable: "
                                f"{phase}:{kind}:{source}"
                            )

    @staticmethod
    def _validate_capture_window(evidence: EvidenceBundle) -> None:
        window = evidence.capture_window
        if (
            window.before_command_at is None
            or window.command_terminal_at is None
            or window.after_command_at is None
        ):
            raise VerificationEvidenceError("evidence capture window is incomplete")
        if not (
            window.before_command_at <= window.command_terminal_at <= window.after_command_at
        ):
            raise VerificationEvidenceError("evidence capture window ordering is invalid")

    def _load_wrapper(self, session: SessionSpec) -> dict[str, Any]:
        if not session.result.artifact_dir:
            raise VerificationEvidenceError(
                "session has no artifact directory for verification"
            )
        path = self._workspace_path(session.result.artifact_dir) / "verification_bundle.json"
        if not path.is_file():
            raise VerificationEvidenceError(
                f"verification bundle does not exist: {path}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerificationEvidenceError(
                f"verification bundle is invalid JSON: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise VerificationEvidenceError("verification bundle must be a JSON object")
        return payload

    def _workspace_path(self, relative_path: str) -> Path:
        path = (self.workspace / relative_path).resolve()
        if not path.is_relative_to(self.workspace):
            raise VerificationEvidenceError(
                f"verification artifact escapes runtime workspace: {relative_path}"
            )
        return path

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
