# Environment State

Auto-updated by PhyAgentOS runtime workspace manager.

```json
{
  "schema_version": "PhyAgentOS.environment.v2",
  "updated_at": "2026-06-10T05:16:25.205797+00:00",
  "targets": {
    "libero_real_remote": {
      "target_id": "libero_real_remote",
      "enabled": true,
      "target_class": "remote",
      "target_kind": "simulation",
      "workspace": "workspaces/libero_real",
      "supported_skills": [
        "pi05_libero_remote"
      ],
      "connection_state": {
        "status": "configured",
        "endpoint": "targetws://libero-host:9002",
        "checked_at": "2026-06-10T05:16:25.205797+00:00",
        "source": "TARGETS.md"
      },
      "runtime": {
        "target_runtime": "LiberoRemoteTargetProxy",
        "target_adapter": "target_adapter://libero_adapter",
        "runtime_contract_ref": "configs/runtime/contracts/libero_real.runtime.yaml"
      },
      "benchmark": {
        "benchmark_name": "libero_spatial",
        "task_id": 0,
        "init_state_id": 0
      }
    },
    "minecraft_java_env": {
      "target_id": "minecraft_java_env",
      "enabled": true,
      "target_class": "local",
      "target_kind": "game",
      "workspace": "workspaces/minecraft",
      "supported_skills": [
        "minecraft_navigate",
        "minecraft_mine",
        "minecraft_build"
      ],
      "connection_state": {
        "status": "configured",
        "endpoint": null,
        "checked_at": "2026-06-10T05:16:25.205797+00:00",
        "source": "TARGETS.md"
      },
      "runtime": {
        "target_runtime": "MinecraftTargetRuntime",
        "target_adapter": "target_adapter://minecraft_adapter",
        "runtime_contract_ref": "configs/runtime/contracts/minecraft.runtime.yaml"
      },
      "benchmark": {}
    }
  }
}
```
