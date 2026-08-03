# Forge-only execution integration

PhyAgentOS supports one robot execution endpoint: Forge Gateway 1.0.0 with API version `paos-forge-gateway-mvp-plus.v1`. Gateway, Forge Runtime, and Dora dataflows are external and are not modified by PAOS.

## Startup contract

`ForgeSessionOrchestrator.start()` requests `/agent/runtime/capabilities` and rejects startup unless:

- the API version is exactly supported;
- sessions, command IDs, and runtime context are advertised;
- Gateway declares serial execution;
- requested actions are present in the capability map.

Action capability metadata is copied into `ExecutionRecord.result_semantics`. It never selects a special verifier branch.

## Execution lifecycle

```text
accepted → capturing_before → dispatching → running → finalizing
         → awaiting_verification → verifying
         → succeeded | failed | awaiting_replan
awaiting_replan → replanned | failed
```

`timed_out` and `cancelled` are terminal states. The root lineage owns the one Gateway execution slot until verification or recovery is terminal.

For a fresh action the adapter:

1. Connects to `/ws/images` and `/ws/state` and waits for configured sources.
2. Persists a before snapshot.
3. Persists a dispatch-attempt event before POSTing `/agent/sessions`.
4. Polls `/agent/sessions/{session_id}` and validates session ID, command ID, request ID, and action identity.
5. Accepts only Gateway `succeeded`, `failed`, or `cancelled` as an execution terminal.
6. Captures after frames with sequence numbers greater than the before frames.
7. Writes immutable `paos_execution_record_v1` and `forge_evidence_bundle_v1` artifacts.

Image association is explicitly `best_effort`. A task requesting authoritative association fails before execution.

## Verification semantics

- `off`: terminal status follows Gateway execution.
- `audit`: verdict/errors are recorded; execution-derived terminal status is preserved and recovery is forbidden.
- `enforce`: verdict controls success; missing evidence, verifier errors, malformed output, and inconclusive verdicts fail closed.
- `recovery`: same fail-closed behavior, while `replan_required` asks the normal Planner to create a new child.

The verifier receives only the task goal, criteria, constraints, immutable execution record, evidence bundle, lineage history, and lessons. Recovery produces a non-executable `RecoveryRequest`; only the Planner may choose a new action.

## Crash recovery

- Work not yet dispatched can continue.
- Once a dispatch attempt is recorded, restart performs GET only and never repeats POST.
- A matching Gateway session resumes capture/finalization.
- Gateway 404 after dispatch becomes `FORGE_EXECUTION_STATE_LOST`.
- Interrupted verification records an abandoned attempt and is retried.
- Replan child creation and parent transition to `replanned` share one SQLite transaction.

## Configuration

See the root README for a complete JSON example. `forge.evidence.requiredImageSources` is target-level configuration; it is not action metadata. The only accepted association quality is `best_effort`.

## Artifacts

```text
<workspace>/.paos/forge/orchestrator.sqlite3
<workspace>/artifacts/forge/<session_id>/
  execution_record.json
  evidence_bundle.json
  before/
  after/
```

Evidence retention may be `all`, `failed`, or `none`. Deleted entities leave source, timing, digest, and deletion audit data in the bundle.
