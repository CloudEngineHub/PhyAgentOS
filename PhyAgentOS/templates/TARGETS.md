# Runtime Targets

```yaml
version: runtime_target_registry_v1
targets:
  - id: libero_real_remote
    target_class: remote
    target_kind: simulation
    enabled: true
    workspace: workspaces/libero_real
    supported_skills:
      - pi05_libero_remote
    runtime:
      target_runtime: LiberoRemoteTargetProxy
      target_endpoint: targetws://libero-host:9002
      target_adapter: target_adapter://libero_adapter
      runtime_contract_ref: configs/runtime/contracts/libero_real.runtime.yaml
    observation:
      observation_type: multimodal
      empty_observation_allowed: false
    perception:
      enabled: false
      strict_preflight: true
      sensor_config_ref: null
      perception_config_ref: null
      artifact_dir: null
    config:
      benchmark_name: libero_spatial
      task_id: 0
      init_state_id: 0
      camera_height: 256
      camera_width: 256
      action_dim: 7
      max_chunk_size: 50
      max_steps: 280
      num_steps_wait: 10
```
