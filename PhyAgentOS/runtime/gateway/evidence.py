"""Persist ForgeAdapter observations as public Evidence Bundle artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from PhyAgentOS.runtime.gateway.observation import ObservationSnapshot
from PhyAgentOS.runtime.schemas import (
    EvidenceArtifact,
    EvidenceBundle,
    EvidenceCaptureWindow,
    EvidenceQuality,
)
from PhyAgentOS.runtime.state_io.atomic_file import atomic_write_bytes, atomic_write_text


class ForgeEvidenceWriter:
    def __init__(self, workspace: Path, session_id: str, command_id: str) -> None:
        self.workspace = workspace.resolve()
        self.session_id = session_id
        self.command_id = command_id
        self.artifact_dir = self.workspace / "artifacts" / "runtime" / session_id
        resolved = self.artifact_dir.resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ValueError("Forge evidence artifact directory escapes runtime workspace")
        self.evidence_dir = self.artifact_dir / "evidence"

    def write(
        self,
        *,
        before: ObservationSnapshot | None,
        after: ObservationSnapshot | None,
        terminal_observed_at,
        required_sources: list[str],
        required_kinds: list[str],
        errors: list[str],
    ) -> tuple[EvidenceBundle, str]:
        artifacts: list[EvidenceArtifact] = []
        missing: list[str] = []
        for phase, snapshot in (("before", before), ("after", after)):
            if snapshot is None:
                missing.append(f"{phase}:snapshot")
                continue
            for source in required_sources:
                image = snapshot.images.get(source)
                if image is None:
                    missing.append(f"{phase}:rgb_image:{source}")
                    continue
                suffix = self._suffix_for(image.media_type)
                name = f"{phase}_{self._safe_name(source)}_{image.sequence}.{suffix}"
                path = self.evidence_dir / name
                atomic_write_bytes(path, image.data)
                artifacts.append(
                    self._artifact(
                        path=path,
                        phase=phase,
                        kind="rgb_image",
                        source_id=source,
                        captured_at=image.captured_at,
                        received_at=image.received_at,
                        sequence=image.sequence,
                        media_type=image.media_type,
                        data=image.data,
                    )
                )
            if snapshot.state is not None:
                data = json.dumps(
                    snapshot.state.payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                path = self.evidence_dir / f"{phase}_robot_state.json"
                atomic_write_bytes(path, data)
                artifacts.append(
                    self._artifact(
                        path=path,
                        phase=phase,
                        kind="robot_state",
                        source_id="ws/state",
                        captured_at=None,
                        received_at=snapshot.state.received_at,
                        sequence=None,
                        media_type="application/json",
                        data=data,
                    )
                )
            elif "robot_state" in required_kinds:
                missing.append(f"{phase}:robot_state:ws/state")

        # Transient transport/validation errors remain auditable, but a bundle is
        # complete when every required artifact was ultimately captured.
        complete = not missing
        bundle = EvidenceBundle(
            bundle_id=f"forge_evidence_{uuid4().hex[:16]}",
            session_id=self.session_id,
            command_id=self.command_id,
            capture_window=EvidenceCaptureWindow(
                before_command_at=before.captured_at if before is not None else None,
                command_terminal_at=terminal_observed_at,
                after_command_at=after.captured_at if after is not None else None,
            ),
            artifacts=artifacts,
            quality=EvidenceQuality(
                complete=complete,
                association_quality="best_effort",
                capture_authority="paos_forge_adapter",
                missing_requirements=missing,
                errors=list(errors),
            ),
        )
        path = self.artifact_dir / "evidence_bundle.json"
        atomic_write_text(
            path,
            json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
        )
        return bundle, str(path.relative_to(self.workspace))

    def _artifact(
        self,
        *,
        path: Path,
        phase: str,
        kind: str,
        source_id: str,
        captured_at,
        received_at,
        sequence,
        media_type: str,
        data: bytes,
    ) -> EvidenceArtifact:
        relative = str(path.relative_to(self.workspace))
        digest = hashlib.sha256(data).hexdigest()
        identity = hashlib.sha256(
            f"{phase}:{kind}:{source_id}:{sequence}:{digest}".encode("utf-8")
        ).hexdigest()
        return EvidenceArtifact(
            artifact_id=f"artifact_{identity[:20]}",
            phase=phase,
            kind=kind,
            source_id=source_id,
            captured_at=captured_at,
            received_at=received_at,
            sequence=sequence,
            media_type=media_type,
            sha256=digest,
            byte_size=len(data),
            uri=relative,
        )

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._")
        return cleaned[:80] or "source"

    @staticmethod
    def _suffix_for(media_type: str) -> str:
        return {
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }.get(media_type.lower(), "img")
