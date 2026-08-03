"""Run one PAOS runtime session through the PhyAgentOS ForgeAdapter."""

from __future__ import annotations

from pathlib import Path

from PhyAgentOS.runtime.gateway.adapter import ForgeAdapter, ForgeAdapterOutcome
from PhyAgentOS.runtime.gateway.client import ForgeGatewayClient
from PhyAgentOS.runtime.schemas import SessionResult, SessionSpec, SkillRuntimeSpec, TargetSpec


class GatewaySessionRunner:
    """Compatibility runner delegating all Forge details to ``ForgeAdapter``."""

    def __init__(
        self,
        *,
        workspace: str | Path,
        session: SessionSpec,
        target_spec: TargetSpec,
        skillruntime_spec: SkillRuntimeSpec,
        client: ForgeGatewayClient | None = None,
        adapter: ForgeAdapter | None = None,
    ) -> None:
        self.adapter = adapter or ForgeAdapter(
            workspace=workspace,
            session=session,
            target_spec=target_spec,
            skillruntime_spec=skillruntime_spec,
            client=client,
        )
        self.outcome: ForgeAdapterOutcome | None = None

    def run(self) -> SessionResult:
        self.outcome = self.adapter.run()
        return self.outcome.result
