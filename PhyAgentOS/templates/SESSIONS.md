# Runtime Sessions

```yaml
version: runtime_sessions_v1
sessions:
  - session_id: sess_dummy_smoke
    goal_id: goal_dummy_smoke
    target_ref: target://dummy_sim
    skillruntime_ref: skillruntime://openpi_sim_vla
    task_description: runtime smoke test
    status: pending
    priority: normal
    timeouts:
      queue_timeout_s: 30
      preflight_timeout_s: 20
      execute_timeout_s: 300
      policy_timeout_s: 10
    retry:
      max_retries: 0
      attempted: 0
    routing:
      target_endpoint: null
      policy_endpoint: dummy://local
      adapter_resolution: strict_auto
      adapter_overrides: null
    execution:
      max_steps: 10
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
  - session_id: sess_pi05_libero_remote_example
    goal_id: goal_pi05_libero_example
    target_ref: target://libero_real_remote
    skillruntime_ref: skillruntime://pi05_libero_remote
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
  - session_id: sess_gateway_grasp_apple_example
    goal_id: goal_gateway_sam3_example
    target_ref: target://forge_gateway
    skillruntime_ref: skillruntime://forge_gateway_sam3
    task_description: grasp apple through Forge Gateway
    status: pending
    priority: low
    timeouts:
      queue_timeout_s: 30
      preflight_timeout_s: 20
      execute_timeout_s: 120
      policy_timeout_s: 10
    retry:
      max_retries: 0
      attempted: 0
    routing:
      target_endpoint: http://127.0.0.1:9001
      policy_endpoint: null
      adapter_resolution: strict_auto
      adapter_overrides: null
    execution:
      max_steps: 1
      replan_every_steps: 1
      action_chunk_mode: single_step
      chunk_switch_mode: hard_switch
    runtime_hints:
      perception_queries: []
      force_environment_refresh: false
      preferred_replan_every_steps: 1
      gateway_action:
        action_type: grasp
        target_name: apple
        source: paos-agent
        inputs:
          auto_home: false
    safety_profile:
      profile: default_simulation
      workspace_bounds: default
      stop_on_policy_timeout: true
    result: {}
```
