"""Runtime session result schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from PhyAgentOS.runtime.schemas.verification import ExecutionRecord, VerificationState


class SessionResult(BaseModel):
    """Result payload written back after a runtime session finishes."""

    status: str | None = None
    success: bool | None = None
    num_steps: int | None = None
    return_value: float | None = None
    mean_policy_latency_ms: float | None = None
    artifact_dir: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    trace_path: str | None = None
    execution: ExecutionRecord | None = None
    verification: VerificationState = Field(default_factory=VerificationState)
    metadata: dict[str, Any] = Field(default_factory=dict)
