"""System-level task verification contracts.

The contracts in this module deliberately describe goals, execution facts, and
evidence without naming robot behaviours.  Runtime-specific adapters normalize
their data into these models before the verifier is invoked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VerificationMode = Literal["off", "audit", "enforce", "recovery"]
VerificationVerdictName = Literal[
    "success",
    "failure",
    "replan_required",
    "inconclusive",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VerificationEvidencePolicy(BaseModel):
    """Evidence requirements attached to a task rather than an action type."""

    model_config = ConfigDict(extra="forbid")

    profile: str = "semantic_default"
    required_kinds: list[str] = Field(default_factory=lambda: ["rgb_image"])
    required_sources: list[str] = Field(default_factory=list)
    minimum_association: Literal["best_effort", "authoritative"] = "best_effort"


class TaskVerificationContract(BaseModel):
    """Task-level success contract produced by the Agent/Planner."""

    model_config = ConfigDict(extra="forbid")

    mode: VerificationMode = "off"
    goal: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evidence_policy: VerificationEvidencePolicy = Field(
        default_factory=VerificationEvidencePolicy
    )
    contract_origin: Literal["explicit", "legacy"] = "explicit"

    @field_validator("goal")
    @classmethod
    def strip_goal(cls, value: str) -> str:
        return value.strip()

    @field_validator("success_criteria", "constraints")
    @classmethod
    def normalize_text_items(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("verification text items must be non-empty")
        return normalized

    @model_validator(mode="after")
    def require_semantic_contract(self) -> "TaskVerificationContract":
        if self.mode != "off":
            if not self.goal:
                raise ValueError("verification goal is required when mode is not off")
            if not self.success_criteria:
                raise ValueError(
                    "at least one success criterion is required when verification mode is not off"
                )
        return self


class ExecutionTimeline(BaseModel):
    """Source and PAOS-observed times for one runtime execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    created_at: float | None = None
    updated_at: float | None = None
    sent_at: float | None = None
    terminal_observed_at: datetime | None = None


class ExecutionError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str | None = None
    message: str = ""


class ExecutionRecord(BaseModel):
    """Immutable execution facts normalized from a runtime adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["runtime_execution_record_v1"] = "runtime_execution_record_v1"
    runtime: str
    session_id: str
    command_id: str
    gateway_api_version: str | None = None
    gateway_instance_id: str | None = None
    action_type: str | None = None
    policy_id: str | None = None
    status: Literal[
        "queued",
        "sent",
        "running",
        "succeeded",
        "failed",
        "timed_out",
        "cancelled",
        "unknown",
    ] = "unknown"
    result_semantics: str = "command_completed"
    completion: dict[str, Any] = Field(default_factory=dict)
    timeline: ExecutionTimeline = Field(default_factory=ExecutionTimeline)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: ExecutionError | None = None


class EvidenceCaptureWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before_command_at: datetime | None = None
    command_terminal_at: datetime | None = None
    after_command_at: datetime | None = None


class EvidenceArtifact(BaseModel):
    """One immutable evidence object stored below the runtime workspace."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    phase: Literal["before", "during", "after"]
    kind: str
    source_id: str
    captured_at: float | None = None
    received_at: datetime
    sequence: int | None = Field(default=None, ge=0)
    media_type: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    uri: str

    @field_validator("uri")
    @classmethod
    def require_workspace_relative_uri(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if not normalized or normalized.startswith("/") or ".." in parts:
            raise ValueError("evidence uri must be a safe workspace-relative path")
        return normalized


class EvidenceQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complete: bool
    association_quality: Literal["best_effort", "authoritative"] = "best_effort"
    capture_authority: str = "paos"
    missing_requirements: list[str] = Field(default_factory=list)
    stale_artifacts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    """Versioned, action-agnostic evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["forge_evidence_bundle_v1"] = "forge_evidence_bundle_v1"
    bundle_id: str
    session_id: str
    command_id: str
    gateway_instance_id: str | None = None
    capture_window: EvidenceCaptureWindow = Field(default_factory=EvidenceCaptureWindow)
    artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    quality: EvidenceQuality
    created_at: datetime = Field(default_factory=_utc_now)


class CriterionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(min_length=1)
    status: Literal["satisfied", "unsatisfied", "unknown"]
    evidence_refs: list[str] = Field(default_factory=list)


class RecoveryContext(BaseModel):
    """Task-level recovery guidance; never an executable runtime action."""

    model_config = ConfigDict(extra="forbid")

    unmet_criteria: list[str] = Field(default_factory=list)
    preserved_constraints: list[str] = Field(default_factory=list)
    guidance: str = ""


class VerificationVerdict(BaseModel):
    """Structured semantic verdict shared by every runtime."""

    model_config = ConfigDict(extra="forbid")

    verdict: VerificationVerdictName
    criteria: list[CriterionVerdict] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    lesson: str = Field(min_length=1)
    recovery_context: RecoveryContext | None = None
    verifier_status: Literal["completed", "invalid_response"] = "completed"

    @model_validator(mode="before")
    @classmethod
    def accept_preview_verdict_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("verdict") == "replan":
            payload["verdict"] = "replan_required"
        if "evidence_refs" not in payload and isinstance(payload.get("evidence"), list):
            payload["evidence_refs"] = [str(item) for item in payload.pop("evidence")]
        if "reason" not in payload:
            payload["reason"] = str(
                payload.pop("failure_reason", None)
                or payload.pop("replan_task_description", None)
                or "Verifier completed without an explicit reason."
            )
        if payload.get("verdict") == "replan_required" and "recovery_context" not in payload:
            payload["recovery_context"] = {
                "guidance": payload.get("reason", ""),
                "unmet_criteria": [],
                "preserved_constraints": [],
            }
        return payload

    @model_validator(mode="after")
    def validate_recovery_context(self) -> "VerificationVerdict":
        if self.verdict == "replan_required" and self.recovery_context is None:
            raise ValueError("replan_required verdict requires recovery_context")
        return self


class VerificationAttempt(BaseModel):
    model_config = ConfigDict(extra="allow")

    attempt_id: str
    created_at: datetime = Field(default_factory=_utc_now)
    source: Literal["auto", "tool"] = "auto"
    mode: Literal["apply", "review"] = "apply"
    verdict: VerificationVerdictName | None = None
    error: str | None = None


class VerificationState(BaseModel):
    """Mutable verification state kept separate from execution facts."""

    model_config = ConfigDict(extra="allow")

    status: Literal[
        "not_requested",
        "pending",
        "running",
        "completed",
        "error",
    ] = "not_requested"
    verdict: VerificationVerdict | None = None
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    bundle_ref: str | None = None
    error: str | None = None


class RecoveryRequest(BaseModel):
    """Persisted request consumed by the Agent recovery coordinator."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    parent_session_id: str
    unmet_criteria: list[str] = Field(default_factory=list)
    preserved_constraints: list[str] = Field(default_factory=list)
    guidance: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    deadline: datetime
    dispatched_at: datetime | None = None
