# Runtime Skills

```yaml
version: runtime_skill_registry_v1
skillruntimes:
  - id: openpi_sim_vla
    runtime: OpenPISkillRuntime
    runtime_kind: policy
    loop_mode: policy_closed_loop
    agent_exposure: none
    supported_target_kinds:
      - simulation
    policy:
      policy_client: dummy
      policy_adapter: policy_adapter://dummy_openpi_adapter
      supports_chunk: true
    observation_contract:
      observation_type: multimodal
      empty_observation_allowed: false
    supports_chunk: true
    default_replan_every: 5
    requires:
      sensors: []
      environment_outputs: []
      strict_environment_contract: true
    output_contract:
      action:
        action_space_id: dummy_policy_delta_eef_gripper_v1
        shape:
          - T
          - 7
        dtype: float32
        normalized: false
        representation: delta_eef_pose_gripper
        frame: base
        chunk:
          variable_T: true
          default_T: 4
          policy_hz: 20
    adapter_requirements:
      allowed_bridges:
        - bridge://safety_clamp
      forbidden: []
  - id: pi05_libero_remote
    runtime: OpenPISkillRuntime
    runtime_kind: policy
    loop_mode: policy_closed_loop
    agent_exposure: none
    supported_target_kinds:
      - simulation
      - real_robot
    policy:
      policy_client: openpi
      policy_adapter: policy_adapter://openpi_pi05_adapter
      supports_chunk: true
    observation_contract:
      observation_type: multimodal
      empty_observation_allowed: false
    supports_chunk: true
    default_replan_every: 5
    requires:
      sensors: []
      environment_outputs: []
      strict_environment_contract: true
    input_contract:
      images:
        - observation/image
        - observation/wrist_image
      state: observation/state
      prompt: prompt
    output_contract:
      action:
        action_space_id: libero_pi05_delta_eef_gripper_v1
        tensor_key: actions
        shape:
          - T
          - 7
        dtype: float32
        normalized: false
        representation: delta_eef_pose_gripper
        frame: base
        chunk:
          variable_T: true
          default_T: 50
          policy_hz: 20
    adapter_requirements:
      allowed_bridges:
        - bridge://safety_clamp
      forbidden:
        - implicit_shape_truncation
        - implicit_representation_cast
  - id: forge_gateway_sam3
    runtime: ForgeGatewaySkillRuntime
    runtime_kind: builtin
    loop_mode: gateway_single_action
    agent_exposure: none
    supported_target_kinds:
      - simulation
      - real_robot
    observation_contract:
      observation_type: multimodal
      empty_observation_allowed: false
    supports_chunk: false
    default_replan_every: 1
    requires:
      sensors: []
      environment_outputs: []
      strict_environment_contract: false
    input_contract:
      gateway_action:
        required: true
        fields:
          - action_type
          - inputs
    output_contract:
      gateway_result:
        status_source: /agent/sessions/{session_id}
        command_identity: policy_command_status.request_id == command_id
        execution_record: runtime_execution_record_v1
        evidence_bundle: forge_evidence_bundle_v1
        evidence_association: best_effort
```
