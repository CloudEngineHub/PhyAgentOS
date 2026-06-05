# Runtime Sessions

```yaml
version: runtime_sessions_v1
sessions:
  - session_id: sess_pi05_libero_remote_example
    goal_id: goal_pi05_libero_example
    target_ref: target://libero_real_remote
    skill_ref: skill://pi05_libero_remote
    task_description: pick up the black bowl between the plate and the ramekin and place it on the plate
    status: pending
    priority: low
    timeouts:
      queue_timeout_s: 30
      preflight_timeout_s: 20
      execute_timeout_s: 300
      policy_timeout_s: 10
    retry:
      max_retries: 0
      attempted: 0
    routing:
      target_endpoint: targetws://libero-host:9002
      policy_endpoint: openpi://policy-host:8000
      adapter_resolution: strict_auto
      adapter_overrides: null
    execution:
      max_steps: 200
      replan_every_steps: 5
      action_chunk_mode: chunk_buffer
      chunk_switch_mode: hard_switch
    runtime_hints:
      perception_queries: []
      force_environment_refresh: false
      preferred_replan_every_steps: 5
    safety_profile:
      profile: default_simulation
      workspace_bounds: default
      stop_on_policy_timeout: true
    result: {}
```
