# Developer manual

## Modules

- `PhyAgentOS/forge/client.py`: asynchronous Gateway HTTP API.
- `PhyAgentOS/forge/observation.py`: bounded asynchronous image/state collection.
- `PhyAgentOS/forge/evidence.py`: validated artifact and public-bundle writer.
- `PhyAgentOS/forge/adapter.py`: one Gateway action lifecycle; no task-success logic.
- `PhyAgentOS/forge/store.py`: transactional SQLite state and event history.
- `PhyAgentOS/forge/orchestrator.py`: execution, verification, recovery, restart, and notifications.
- `PhyAgentOS/verification/contracts.py`: versioned action-independent contracts.
- `PhyAgentOS/agent/session_verifier.py`: Forge verifier client/process and retention.
- `PhyAgentOS/agent/tools/forge.py`: Agent-facing Forge tools.

## Invariants

- PAOS generates session and command IDs; callers cannot set them.
- One non-terminal root lineage exists per process/store.
- Dispatch intent is durable before POST and is never automatically repeated.
- Terminal identity requires matching session, command, request, and action.
- `ExecutionRecord` is immutable after adapter finalization; reviews append verification attempts only.
- Verifier prompts and recovery requests are independent of action type.
- Parent `replanned` and child creation are atomic.

## Adding Gateway actions

Add or change the action in Forge Gateway. PAOS discovers it through capabilities and passes generic inputs. Do not add action-specific verifier switches. Express success through task criteria and evidence policy.

## Tests

The Forge tests cover contracts/config, store transitions and concurrency, Gateway identity, observation boundaries, orchestration modes, recovery, and restart rules. Default tests use fake clients/adapters; optional black-box tests may use `FORGE_GATEWAY_URL` without modifying Gateway files.

```bash
pytest
ruff check PhyAgentOS tests
python -m compileall -q PhyAgentOS tests
```

The repository guard excludes historical reports under `plan/` and rejects active imports or protocol-template reintroduction from the removed execution system.
