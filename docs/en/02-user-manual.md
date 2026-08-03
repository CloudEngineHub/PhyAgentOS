# User manual

## Configure and start

Run `paos onboard`, configure a model provider, and enable the `forge` object shown in the root README. The configured endpoint must expose Forge Gateway 1.0.0 and API `paos-forge-gateway-mvp-plus.v1`.

Use `paos agent` for interactive work, `paos agent -m "..."` for one-shot work, or `paos gateway` for configured messaging channels. When a one-shot request submits a Forge task, PAOS remains alive until the root lineage finishes.

## Describe a task

Ask for one high-level Gateway action and provide enough detail for the Agent to construct:

- `task_description`, `action_type`, and action `inputs`;
- verification `mode`;
- task `goal`, success criteria, and constraints for every non-`off` mode.

The submit tool returns immediately. The Agent receives system events for completion or recovery. Query `forge_get_session` when you need the latest persisted state.

## Choose a verification mode

- Use `off` only when Gateway command completion is sufficient.
- Use `audit` to observe verifier quality without changing execution outcomes.
- Use `enforce` when unverified or inconclusive task completion must fail.
- Use `recovery` when the Planner may try a newly planned action after `replan_required`.

## Operations

- Inspect live Gateway state with `forge_get_context`.
- Cancel by PAOS session ID with `forge_cancel_session`.
- Reset only while no lineage is active with `forge_reset`.
- Review a terminal session with `verify_forge_session`; review does not change its status.

## Troubleshooting

- API/support validation failure: confirm the configured endpoint is Gateway 1.0.0.
- `FORGE_EXECUTION_STATE_LOST`: PAOS recorded dispatch, but Gateway no longer knows the matching session. The action is not resent; inspect Gateway logs and reset explicitly if safe.
- Missing after evidence: check `/ws/images`, configured source IDs, capture timeouts, and frame sequences.
- Verification unavailable: non-`off` submissions are rejected or fail closed. Configure a valid verification provider/service.
- Busy error: another root lineage still owns the serial Gateway slot; inspect or cancel it.

Existing user workspaces are not modified automatically. Obsolete execution-protocol files from older installations may be removed manually after backing up anything important; current PAOS neither reads nor generates them.
