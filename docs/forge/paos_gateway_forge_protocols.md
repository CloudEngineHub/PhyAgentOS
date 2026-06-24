# PAOS / Gateway / Forge 三方接口协议附录

### 3.1 协议分组

三方并行开发依赖三组协议：

1. **PAOS -> Gateway：Agent Command Protocol**
2. **Gateway -> Forge：Runtime Command Protocol**
3. **Forge -> Gateway：Runtime Feedback Protocol**

### 3.2 PAOS -> Gateway：Agent Command Protocol

#### 创建 Session

```http
POST /agent/sessions
Content-Type: application/json
```

请求：

```json
{
  "session_id": "optional-session-id",
  "command_id": "optional-command-id",
  "action_type": "grasp",
  "target_name": "red_apple",
  "instruction": "抓取桌面上的红苹果",
  "source": "paos-agent",
  "inputs": {
    "auto_home": false
  }
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "session": {
      "session_id": "sess_...",
      "status": "queued",
      "action_type": "grasp",
      "command_ids": ["cmd_..."]
    },
    "command": {
      "command_id": "cmd_...",
      "policy_id": "sam3",
      "command": "grasp_simple",
      "request_id": "cmd_...",
      "status": "queued"
    },
    "status": "queued"
  }
}
```

错误响应：

```json
{
  "ok": false,
  "msg": "missing required inputs: target_name"
}
```

#### 查询 Session

```http
GET /agent/sessions/{session_id}
```

响应：

```json
{
  "ok": true,
  "data": {
    "session": {
      "session_id": "sess_...",
      "status": "running",
      "action_type": "grasp",
      "command_ids": ["cmd_..."]
    },
    "commands": [
      {
        "command_id": "cmd_...",
        "policy_id": "sam3",
        "command": "grasp_simple",
        "status": "running",
        "outputs": {}
      }
    ]
  }
}
```

#### 取消 Session

```http
POST /agent/sessions/{session_id}/cancel
```

请求：

```json
{
  "reason": "agent_requested"
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "session_id": "sess_...",
    "status": "cancelled"
  }
}
```

MVP+ 已实现最小 cancel 语义：Gateway 将 session/command 标记为 `cancelled`，并向原 `policy_id` 下发 `PolicyCommand(command="stop")`。该能力用于 VLA 或长动作的上层简单停止控制，不表示底层已经完成复杂恢复。

#### Runtime Status

```http
GET /agent/runtime/status
```

响应：

```json
{
  "ok": true,
  "data": {
    "readiness": {
      "ready": true,
      "missing": []
    },
    "active_session_id": null,
    "sessions": {},
    "commands": {},
    "nodes": {},
    "last_result": {},
    "last_error": null
  }
}
```

#### Runtime Context

```http
GET /agent/runtime/context
```

响应：

```json
{
  "ok": true,
  "data": {
    "updated_at": 1710000000.0,
    "capabilities": {},
    "readiness": {},
    "active_session_id": null,
    "sessions": {},
    "commands": {},
    "nodes": {},
    "last_result": {},
    "last_error": null,
    "runtime": {}
  }
}
```

#### Runtime Capabilities

```http
GET /agent/runtime/capabilities
```

响应：

```json
{
  "ok": true,
  "data": {
    "api_version": "paos-forge-gateway-mvp-plus.v1",
    "action_manifests": ["./actions/piper/sam3.md"],
    "supports": {
      "sessions": true,
      "command_id": true,
      "cancel": true,
      "reset": true,
      "estop": false,
      "runtime_context": true,
      "serial_actions_only": true
    },
    "policies": {
      "sam3": {
        "policy_id": "sam3",
        "robot_id": "piper",
        "manifest": "./actions/piper/sam3.md",
        "actions": {
          "grasp": {
            "command": "grasp_simple",
            "required_parameters": ["target_name"]
          }
        }
      }
    },
    "actions": {
      "grasp": {
        "policy_id": "sam3",
        "robot_id": "piper",
        "command": "grasp_simple",
        "required_parameters": ["target_name"]
      }
    }
  }
}
```

### 3.3 Gateway -> Forge：Runtime Command Protocol

Gateway 输出 `forge_msgs.PolicyCommand`。

规范：

```json
{
  "policy_id": "sam3",
  "command": "grasp_simple",
  "request_id": "cmd_...",
  "inputs_json": {
    "session_id": "sess_...",
    "command_id": "cmd_...",
    "action_type": "grasp",
    "policy_id": "sam3",
    "target": "red_apple",
    "target_name": "red_apple",
    "instruction": "抓取桌面上的红苹果",
    "source": "paos-agent"
  }
}
```

映射来自 action manifest，例如 `./actions/piper/sam3.md`：

| Agent `action_type` | `policy_id` | PolicyCommand `command` | Required inputs |
|---|---|---|---|
| `grasp` | `sam3` | `grasp_simple` | `target_name` |
| `place` | `sam3` | `explore_and_place` | `target_name` |
| `check_target` | `sam3` | `check_target` | `target_name` |
| `go_home` | `sam3` | `go_standby` | none |

取消时，Gateway 向原 policy 下发：

```json
{
  "policy_id": "sam3",
  "command": "stop",
  "request_id": "cancel_cmd_...",
  "inputs_json": {
    "session_id": "sess_...",
    "command_id": "cancel_cmd_...",
    "cancelled_command_id": "cmd_...",
    "source": "paos-agent",
    "reason": "agent_cancel"
  }
}
```

### 3.4 Forge -> Gateway：Runtime Feedback Protocol

#### `policy_command_status`

由 policy node 输出，类型为 `forge_msgs.PolicyCommandStatus`。

```json
{
  "policy_id": "sam3",
  "command": "grasp_simple",
  "request_id": "cmd_...",
  "status": "done",
  "message": "",
  "outputs_json": {
    "accepted": true,
    "command_id": "cmd_...",
    "target_name": "red_apple"
  }
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `policy_id` | policy 节点标识 |
| `command` | 被处理的 PolicyCommand command |
| `request_id` | Gateway 下发的 request id，MVP+ 等于 `command_id` |
| `status` | `accepted/running/done/rejected/error` |
| `message` | Agent 可读摘要 |
| `outputs_json` | policy 输出对象，可包含 `command_id`、`target_name`、`accepted` 等 |

Gateway 状态映射：

| PolicyCommandStatus `status` | Gateway command/session |
|---|---|
| `accepted` / `running` | `running` |
| `done` | `succeeded` |
| `rejected` / `error` | `failed` |

### 3.5 Runtime Context Protocol

`RuntimeContextV1`：

```json
{
  "updated_at": 1710000000.0,
  "capabilities": {
    "api_version": "paos-forge-gateway-mvp-plus.v1",
    "supports": {
      "sessions": true,
      "command_id": true,
      "cancel": true,
      "runtime_context": true,
      "serial_actions_only": true
    },
    "policies": {},
    "actions": {}
  },
  "readiness": {
    "ready": true,
    "missing": []
  },
  "active_session_id": null,
  "sessions": {},
  "commands": {},
  "nodes": {},
  "runtime": {
    "current_frame_count": 0,
    "sim_status": {},
    "record_status": {},
    "playback_status": {}
  },
  "last_result": null,
  "last_error": null
}
```

MVP+ 中，`capabilities` 来自 action manifest，`last_result` 来自最近一次 `PolicyCommandStatus`。Gateway 不判断复杂任务语义成功，VLA 或长动作完成判定由 PAOS Agent 或后续 verifier 处理。

### 3.6 Benchmark Protocol 预留

MVP+ 不实现具体 benchmark，只预留：

```http
POST /agent/benchmarks
GET /agent/benchmarks/{benchmark_id}
```

请求草案：

```json
{
  "suite": "libero_spatial",
  "tasks": ["pick_up_the_black_bowl"],
  "num_episodes": 50,
  "policy": {
    "policy_id": "pi0",
    "endpoint": "optional"
  }
}
```

结果草案：

```json
{
  "benchmark_id": "bench_...",
  "status": "completed",
  "metrics": {
    "success_rate": 0.82,
    "mean_steps": 73.4
  },
  "failure_summary": {
    "timeout": 5,
    "grasp_failed": 4
  }
}
```

### 3.7 错误码建议

| 错误码 | 说明 |
|---|---|
| `RUNTIME_NOT_READY` | Forge runtime readiness 不满足 |
| `UNSUPPORTED_ACTION` | Agent 请求的 action 不支持 |
| `INVALID_PARAMETERS` | 参数缺失或类型错误 |
| `RUNTIME_BUSY` | 当前只支持单 active session，runtime 忙 |
| `COMMAND_TIMEOUT` | command 超时 |
| `POLICY_FAILED` | policy node 内部失败 |
| `PERCEPTION_FAILED` | 感知阶段失败 |
| `PLANNING_FAILED` | 规划阶段失败 |
| `EXECUTION_FAILED` | 执行动作失败 |
| `TASK_NOT_VERIFIED` | 执行完成但任务成功未验证 |
