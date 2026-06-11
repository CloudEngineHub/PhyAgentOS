# Runtime Targets

```yaml
version: runtime_target_registry_v1
targets:
  - id: dummy_sim
    target_class: local
    target_kind: simulation
    enabled: true
    workspace: workspaces/dummy_sim
    supported_skillruntimes:
      - openpi_sim_vla
    runtime:
      target_runtime: DummySimTargetRuntime
      target_endpoint: null
      target_adapter: target_adapter://dummy_sim_adapter
      runtime_contract_ref: configs/runtime/contracts/dummy_sim.runtime.yaml
    observation:
      observation_type: multimodal
      empty_observation_allowed: false
    perception:
      enabled: false
      strict_preflight: true
      sensor_config_ref: configs/runtime/sensors/dummy_sim.sensors.yaml
      perception_config_ref: null
      artifact_dir: null
    config:
      action_dim: 7
      success_after_steps: 5
      image_size: 16
      state_dim: 8
      action:
        action_dim: 7
        chunk_size: 4
  - id: libero_real_remote
    target_class: remote
    target_kind: simulation
    enabled: true
    workspace: workspaces/libero_real
    supported_skillruntimes:
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
