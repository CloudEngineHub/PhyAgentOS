"""Write runtime results to artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PhyAgentOS.runtime.artifacts.episode_writer import EpisodeWriter
from PhyAgentOS.runtime.schemas import (
    EvidenceArtifact,
    EvidenceBundle,
    EvidenceCaptureWindow,
    EvidenceQuality,
    SessionResult,
    SessionSpec,
    TargetSpec,
)
from PhyAgentOS.runtime.schemas.common import utc_now
from PhyAgentOS.runtime.state_io.atomic_file import atomic_write_text
from PhyAgentOS.runtime.state_io.markdown_yaml import read_yaml_block, write_yaml_block


class ResultWriter:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.episode_writer = EpisodeWriter(workspace / "artifacts" / "runtime")

    def write_episode(
        self,
        session: SessionSpec,
        target: TargetSpec,
        skillruntime_id: str,
        result: SessionResult,
    ) -> SessionResult:
        artifact_dir = self.episode_writer.write_episode(session, target, skillruntime_id, result)
        result.artifact_dir = str(artifact_dir.relative_to(self.workspace))
        return result

    def write_session_history(
        self,
        session: SessionSpec,
        target: TargetSpec,
        result: SessionResult,
    ) -> None:
        """Write transient runtime session history outside ENVIRONMENT.md."""
        path = self.workspace / "LOG.md"
        history = self._load_session_history(path)
        sessions = history.get("sessions")
        if not isinstance(sessions, dict):
            sessions = {}

        summary = {
            "session_id": session.session_id,
            "target_id": target.id,
            "status": result.status,
            "success": bool(result.success),
            "artifact_dir": result.artifact_dir or "",
            "num_steps": result.num_steps,
            "return_value": result.return_value,
            "mean_policy_latency_ms": result.mean_policy_latency_ms,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "trace_path": result.trace_path,
            "updated_at": utc_now().isoformat(),
        }
        sessions[session.session_id] = {key: value for key, value in summary.items() if value is not None}
        history.update(
            {
                "version": "runtime_session_history_v1",
                "updated_at": utc_now().isoformat(),
                "last_session_id": session.session_id,
                "last_target_id": target.id,
                "last_status": result.status,
                "last_success": bool(result.success),
                "last_artifact_dir": result.artifact_dir or "",
                "sessions": sessions,
            }
        )
        write_yaml_block(path, "Runtime Session History", history)

    def write_verification_bundle(
        self,
        session: SessionSpec,
        target: TargetSpec,
        skillruntime_id: str,
        result: SessionResult,
        *,
        environment_workspace: Path,
        initial_observation: dict[str, Any] | None = None,
        final_observation: dict[str, Any] | None = None,
        initial_observed_at: datetime | None = None,
        final_observed_at: datetime | None = None,
    ) -> Path:
        """Write the v3 task/execution/evidence wrapper consumed by the verifier."""
        if not result.artifact_dir:
            raise ValueError("verification bundle requires an episode artifact directory")
        artifact_dir = self._workspace_path(result.artifact_dir)
        initial_paths: list[Path] = []
        final_paths: list[Path] = []
        evidence_bundle_ref = result.verification.bundle_ref
        if evidence_bundle_ref is None:
            initial_paths = self.episode_writer.write_rgb_frames(
                artifact_dir,
                initial_observation,
                phase="before",
            )
            final_paths = self.episode_writer.write_rgb_frames(
                artifact_dir,
                final_observation,
                phase="after",
            )
            evidence_bundle_ref = self._write_runner_evidence_bundle(
                session,
                result,
                artifact_dir,
                initial_paths=initial_paths,
                final_paths=final_paths,
                initial_observation=initial_observation,
                final_observation=final_observation,
                initial_observed_at=initial_observed_at,
                final_observed_at=final_observed_at,
            )
            result.verification.bundle_ref = evidence_bundle_ref

        payload = {
            "version": "agent_session_verification_v3",
            "task_verification_contract": session.verification.model_dump(
                mode="json", exclude_none=True
            ),
            "session": session.model_dump(mode="json", exclude_none=True),
            "target_id": target.id,
            "skillruntime_id": skillruntime_id,
            "execution_record": (
                result.execution.model_dump(mode="json", exclude_none=True)
                if result.execution is not None
                else None
            ),
            "runtime_result": result.model_dump(mode="json", exclude_none=True),
            "evidence_bundle_ref": evidence_bundle_ref,
            "initial_rgb_paths": [
                str(path.relative_to(self.workspace)) for path in initial_paths
            ],
            "final_rgb_paths": [
                str(path.relative_to(self.workspace)) for path in final_paths
            ],
            "environment_md": self._read_optional(
                environment_workspace / "ENVIRONMENT.md"
            ),
            "history_md": self._read_optional(self.workspace / "LOG.md"),
            "lessons_md": self._read_optional(self.workspace / "LESSONS.md"),
            "created_at": utc_now().isoformat(),
        }
        path = artifact_dir / "verification_bundle.json"
        atomic_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        result.metadata["verification_bundle_ref"] = str(path.relative_to(self.workspace))
        return path

    def _write_runner_evidence_bundle(
        self,
        session: SessionSpec,
        result: SessionResult,
        artifact_dir: Path,
        *,
        initial_paths: list[Path],
        final_paths: list[Path],
        initial_observation: dict[str, Any] | None,
        final_observation: dict[str, Any] | None,
        initial_observed_at: datetime | None,
        final_observed_at: datetime | None,
    ) -> str:
        artifacts: list[EvidenceArtifact] = []
        for phase, paths, observed_at in (
            ("before", initial_paths, initial_observed_at),
            ("after", final_paths, final_observed_at),
        ):
            for path in paths:
                source = path.stem.split("_", 2)[-1]
                artifacts.append(
                    self._evidence_artifact(
                        path,
                        phase=phase,
                        kind="rgb_image",
                        source_id=source,
                        observed_at=observed_at,
                        media_type="image/png",
                    )
                )

        if "robot_state" in session.verification.evidence_policy.required_kinds:
            for phase, observation, observed_at in (
                ("before", initial_observation, initial_observed_at),
                ("after", final_observation, final_observed_at),
            ):
                path = self.episode_writer.write_json_observation(
                    artifact_dir,
                    observation,
                    phase=phase,
                )
                if path is not None:
                    artifacts.append(
                        self._evidence_artifact(
                            path,
                            phase=phase,
                            kind="robot_state",
                            source_id="paos_session_runner",
                            observed_at=observed_at,
                            media_type="application/json",
                        )
                    )

        terminal_at = (
            result.execution.timeline.terminal_observed_at
            if result.execution is not None
            else None
        )
        after_frozen_at = utc_now()
        missing: list[str] = []
        for kind in session.verification.evidence_policy.required_kinds:
            for phase in ("before", "after"):
                candidates = [
                    artifact
                    for artifact in artifacts
                    if artifact.kind == kind and artifact.phase == phase
                ]
                if not candidates:
                    missing.append(f"{phase}:{kind}")
                if "image" in kind:
                    for source in session.verification.evidence_policy.required_sources:
                        if not any(artifact.source_id == source for artifact in candidates):
                            missing.append(f"{phase}:{kind}:{source}")
        if initial_observed_at is None:
            missing.append("capture_window:before")
        if terminal_at is None:
            missing.append("capture_window:terminal")
        bundle = EvidenceBundle(
            bundle_id=f"runner_evidence_{session.session_id}",
            session_id=session.session_id,
            command_id=(
                result.execution.command_id
                if result.execution is not None
                else f"paos_{session.session_id}"
            ),
            capture_window=EvidenceCaptureWindow(
                before_command_at=initial_observed_at,
                command_terminal_at=terminal_at,
                after_command_at=after_frozen_at,
            ),
            artifacts=artifacts,
            quality=EvidenceQuality(
                complete=not missing,
                association_quality="best_effort",
                capture_authority="paos_session_runner",
                missing_requirements=missing,
            ),
        )
        path = artifact_dir / "evidence_bundle.json"
        atomic_write_text(
            path,
            json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
        )
        return str(path.relative_to(self.workspace))

    def _evidence_artifact(
        self,
        path: Path,
        *,
        phase: str,
        kind: str,
        source_id: str,
        observed_at: datetime | None,
        media_type: str,
    ) -> EvidenceArtifact:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        identity = hashlib.sha256(
            f"{phase}:{kind}:{source_id}:{digest}".encode("utf-8")
        ).hexdigest()
        return EvidenceArtifact(
            artifact_id=f"artifact_{identity[:20]}",
            phase=phase,
            kind=kind,
            source_id=source_id,
            captured_at=observed_at.timestamp() if observed_at is not None else None,
            received_at=utc_now(),
            media_type=media_type,
            sha256=digest,
            byte_size=len(data),
            uri=str(path.relative_to(self.workspace)),
        )

    def _load_session_history(self, path: Path) -> dict:
        if not path.exists():
            return {"version": "runtime_session_history_v1", "sessions": {}}
        try:
            payload = read_yaml_block(path)
        except Exception:
            return {"version": "runtime_session_history_v1", "sessions": {}}
        if payload.get("version") != "runtime_session_history_v1":
            return {"version": "runtime_session_history_v1", "sessions": {}}
        return payload

    def write_verification_result(
        self,
        session: SessionSpec,
        result: SessionResult,
    ) -> Path | None:
        """Persist verifier state without rewriting the immutable execution record."""
        if not result.artifact_dir:
            return None
        artifact_dir = self._workspace_path(result.artifact_dir)
        path = artifact_dir / "verification_result.json"
        payload = {
            "version": "agent_session_verification_result_v1",
            "session_id": session.session_id,
            "status": result.status,
            "success": result.success,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "execution_identity": (
                {
                    "session_id": result.execution.session_id,
                    "command_id": result.execution.command_id,
                    "status": result.execution.status,
                }
                if result.execution is not None
                else None
            ),
            "verification": result.verification.model_dump(mode="json"),
            "retention": result.metadata.get("verification_retention"),
            "updated_at": utc_now().isoformat(),
        }
        atomic_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        episode_path = artifact_dir / "episode.json"
        if episode_path.is_file():
            try:
                episode = json.loads(episode_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                episode = None
            if isinstance(episode, dict):
                # Deliberately leave episode["execution"] untouched.
                episode.update(
                    {
                        "status": result.status,
                        "success": result.success,
                        "error_code": result.error_code,
                        "error_message": result.error_message,
                        "verification": result.verification.model_dump(mode="json"),
                    }
                )
                atomic_write_text(
                    episode_path,
                    json.dumps(episode, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                )
        return path

    def write_lesson(
        self,
        session: SessionSpec,
        target_id: str,
        skillruntime_id: str,
        phase: str,
        error_code: str | None,
        summary: str,
        metadata: dict,
    ) -> None:
        path = self.workspace / "LESSONS.md"
        payload = self._load_lessons(path)
        lessons = payload.get("lessons")
        if not isinstance(lessons, list):
            lessons = []
        lessons.append(
            {
                "id": f"lesson_{session.session_id}_{len(lessons) + 1}",
                "timestamp": utc_now().isoformat(),
                "session_id": session.session_id,
                "phase": phase,
                "error_code": error_code,
                "target_id": target_id,
                "skillruntime_id": skillruntime_id,
                "summary": summary,
                "metadata": metadata,
            }
        )
        write_yaml_block(
            path,
            "Runtime Lessons",
            {"version": "runtime_lessons_v1", "updated_at": utc_now().isoformat(), "lessons": lessons},
        )

    def _load_lessons(self, path: Path) -> dict:
        if not path.exists():
            return {"version": "runtime_lessons_v1", "lessons": []}
        try:
            payload = read_yaml_block(path)
        except Exception:
            return {"version": "runtime_lessons_v1", "lessons": []}
        if not isinstance(payload.get("lessons"), list):
            payload["lessons"] = []
        return payload

    def _workspace_path(self, relative_path: str) -> Path:
        root = self.workspace.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"artifact path escapes runtime workspace: {relative_path}")
        return path

    @staticmethod
    def _read_optional(path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""
