# PhyAgentOS

PhyAgentOS is an agent framework with one robot execution path: Forge Gateway 1.0.0. The Agent plans a high-level action, the Forge adapter executes it, captures before/after evidence, and invokes a task-level verifier before reporting success.

[中文说明](README_zh.md) · [Forge guide](docs/forge/README.md) · [User manual](docs/en/02-user-manual.md) · [Developer manual](docs/en/03-developer-manual.md)

## Architecture

```text
User / channel
      │
      ▼
Agent Planner ── Forge tools ──► ForgeSessionOrchestrator
                                      │
                   ┌──────────────────┼──────────────────┐
                   ▼                  ▼                  ▼
             ForgeAdapter       SQLite event log   ForgeTaskVerifier
                   │                  │                  │
                   ▼                  ▼                  ▼
          Forge Gateway 1.0.0    public contracts   verdict / recovery
                   │
                   ▼
             Forge + Dora
```

Gateway `succeeded` is an execution fact. For `enforce` and `recovery` tasks, task success comes from the semantic verification verdict.

## Install

```bash
git clone https://github.com/HKUDS/PhyAgentOS.git
cd PhyAgentOS
pip install -e .
paos onboard
```

Configure the model provider and the single Forge endpoint in `~/.PhyAgentOS/config.json`:

```json
{
  "agents": {
    "verification": {
      "serviceEnabled": true,
      "evidenceRetention": "failed",
      "maxReplansPerEpisode": 2
    }
  },
  "forge": {
    "enabled": true,
    "baseUrl": "http://127.0.0.1:9001",
    "apiVersion": "paos-forge-gateway-mvp-plus.v1",
    "requestTimeoutS": 10,
    "pollIntervalS": 0.5,
    "executionTimeoutS": 300,
    "evidence": {
      "requiredImageSources": ["front"],
      "captureTimeoutS": 5,
      "postCaptureTimeoutS": 5,
      "maxArtifactBytes": 8388608,
      "associationQuality": "best_effort"
    }
  }
}
```

Start an interactive Agent or the multi-channel gateway:

```bash
paos agent
paos gateway
```

## Forge tools

- `forge_execute_task` submits one action asynchronously and generates fresh PAOS session and command IDs.
- `forge_get_session` returns persisted request, execution, evidence, verdict, and recovery state.
- `forge_cancel_session` cancels active execution or recovery.
- `forge_get_context` reads live capabilities, readiness, and context.
- `forge_reset` explicitly resets an idle Gateway.
- `verify_forge_session` performs a non-destructive review of retained evidence.
- `create_replanned_forge_session` atomically creates a new child for a parent awaiting recovery.

Verification modes are `off`, `audit`, `enforce`, and `recovery`. Every non-`off` task requires a goal and at least one success criterion.

## Persistence

The orchestrator stores state and its append-only event history in `<workspace>/.paos/forge/orchestrator.sqlite3`. Evidence and public contract artifacts are under `<workspace>/artifacts/forge/<session_id>/`. Dispatch attempts are persisted before Gateway submission so a restart never blindly repeats an action.

`EMBODIED.md`, `ENVIRONMENT.md`, and SceneGraph remain knowledge/context surfaces. They are not execution queues.

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check PhyAgentOS tests
python -m compileall -q PhyAgentOS tests
```

The supported Gateway contract is documented in [docs/forge/README.md](docs/forge/README.md). Historical design reports are kept under `plan/`.

## License

MIT. See [LICENSE](LICENSE).
