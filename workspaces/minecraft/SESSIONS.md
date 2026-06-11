# Runtime Sessions

```yaml
version: runtime_sessions_v1
sessions:
- session_id: nav_to_wissingcc
  target_ref: target://minecraft_java_env
  skill_ref: skill://minecraft_navigate
  task_description: 导航到玩家 wissingcc 身边
  status: succeeded
  priority: normal
  updated_at: '2026-06-10T05:10:54.843042Z'
  claimed_by: runtime-watchdog@liuy
  claim_token: b82f0e6efa064bcbbe85f87ce05a8da9
  timeouts:
    queue_timeout_s: 30.0
    preflight_timeout_s: 20.0
    execute_timeout_s: 300.0
    policy_timeout_s: 10.0
  retry:
    max_retries: 0
    attempted: 0
  depends_on: []
  routing:
    adapter_resolution: strict_auto
  execution:
    max_steps: 200
    replan_every: 8
    replan_every_steps: 5
    action_chunk_mode: chunk_buffer
    chunk_switch_mode: hard_switch
  runtime_hints:
    perception_queries:
    - type: move
      params:
        target: wissingcc
        absolute: true
    force_environment_refresh: false
    preferred_replan_every_steps: 5
  safety_profile:
    profile: default_simulation
    workspace_bounds: default
    stop_on_policy_timeout: true
  result:
    status: succeeded
    success: true
    num_steps: 1
    return_value: 0.0
    artifact_dir: artifacts/runtime/nav_to_wissingcc
    metadata:
      step_results:
      - step: 0
        type: chat
        params:
          message: I can't see any wissingcc nearby.
        ok: true
        result: 'sent: I can''t see any wissingcc nearby.'
      task: 导航到玩家 wissingcc 身边
      final_status:
        num_steps: 1
        reward: 0.0
        executed_steps: 1
      artifacts: {}
- session_id: nav_to_wissingcc_v2
  target_ref: target://minecraft_java_env
  skill_ref: skill://minecraft_navigate
  task_description: 导航到玩家 wissingcc 身边 (20.5, 64, -227.5)
  status: succeeded
  priority: normal
  updated_at: '2026-06-10T05:55:47.562521Z'
  claimed_by: runtime-watchdog@liuy
  claim_token: 455ec638d5aa4fcf8311a61cd7c97b6d
  timeouts:
    queue_timeout_s: 30.0
    preflight_timeout_s: 20.0
    execute_timeout_s: 300.0
    policy_timeout_s: 10.0
  retry:
    max_retries: 0
    attempted: 0
  depends_on: []
  routing:
    adapter_resolution: strict_auto
  execution:
    max_steps: 200
    replan_every: 8
    replan_every_steps: 5
    action_chunk_mode: chunk_buffer
    chunk_switch_mode: hard_switch
  runtime_hints:
    perception_queries:
    - type: move
      params:
        dx: 20.5
        dy: 64
        dz: -227.5
        absolute: true
    force_environment_refresh: false
    preferred_replan_every_steps: 5
  safety_profile:
    profile: default_simulation
    workspace_bounds: default
    stop_on_policy_timeout: true
  result:
    status: succeeded
    success: true
    num_steps: 1
    return_value: 0.0
    artifact_dir: artifacts/runtime/nav_to_wissingcc_v2
    metadata:
      step_results:
      - step: 0
        type: move
        params:
          dx: 20.5
          dy: 64
          dz: -227.5
          absolute: true
        ok: true
        result: moving to (20.5, 64.0, -227.5)
      task: 导航到玩家 wissingcc 身边 (20.5, 64, -227.5)
      final_status:
        num_steps: 1
        reward: 0.0
        executed_steps: 1
      artifacts: {}
```
