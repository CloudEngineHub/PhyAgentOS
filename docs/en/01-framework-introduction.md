# Framework introduction

PhyAgentOS separates conversational planning from robot execution. The Agent and its skills provide reasoning and user interaction; `ForgeSessionOrchestrator` is the only robot execution coordinator; Forge Gateway 1.0.0 owns physical/simulated action execution; `ForgeTaskVerifier` evaluates task-level criteria from persisted evidence.

The public boundary consists of `ForgeTaskRequest`, `ForgeSessionRecord`, `TaskVerificationContract`, `ExecutionRecord`, `EvidenceBundle`, `VerificationVerdict`, and `RecoveryRequest`. These models are action-independent.

Three facts are deliberately separate:

1. The Gateway reports whether an action command finished.
2. The evidence bundle records what PAOS observed around that command.
3. The verifier decides whether the task criteria were met.

PAOS keeps Embodiment, `EMBODIED.md`, `ENVIRONMENT.md`, and SceneGraph as knowledge surfaces. None of them dispatches actions.

Continue with the [user manual](02-user-manual.md), [developer manual](03-developer-manual.md), or [Forge contract](../forge/README.md).
