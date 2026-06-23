# Forge Gateway MVP+ 详细设计

### 2.1 MVP+ 定义

MVP+ 指：

- Gateway 使用内存作为运行态 source of truth。
- Gateway 写 JSONL 事件日志作为审计和弱恢复。
- Gateway 写 `runtime_context.json` snapshot 作为 Agent 可读上下文镜像。
- 不引入数据库。
- 不做强一致恢复。

推荐存储层级：

```text
Source of truth:
  Gateway 内存状态

Durable audit:
  runtime_state/events.jsonl

Agent-visible snapshot:
  runtime_state/runtime_context.json
  可选 FORGE_RUNTIME.md / ENVIRONMENT.md
```

### 2.2 Gateway 内部模块

```text
Forge Gateway
├── Agent API Server
├── Session Store
├── Command Mapper
├── Action Manifest Loader
├── Dora IO Adapter
├── Runtime State Aggregator
├── Runtime Context Builder
├── Event Log Writer
└── Snapshot Writer
```

#### Agent API Server

提供：

- `POST /agent/sessions`
- `GET /agent/sessions/{session_id}`
- `POST /agent/sessions/{session_id}/cancel`
- `GET /agent/runtime/status`
- `GET /agent/runtime/context`
- `GET /agent/runtime/capabilities`

#### Session Store

维护：

```text
sessions: dict[str, SessionState]
commands: dict[str, CommandState]
nodes: dict[str, NodeStatus]
active_session_id: str | None
last_result: dict | None
```

#### Command Mapper

负责：

- 基于 action manifest 校验 Agent action。
- 将 `action_type` 映射到 `policy_id + PolicyCommand.command`。
- 将 Agent parameters 映射到 `PolicyCommand.inputs`。
- 注入 `session_id`、`command_id`、`instruction`、`source`。
- 将 `command_id` 映射为 `PolicyCommand.request_id`。

#### Action Manifest Loader

负责：

- 读取 `agent.action_manifests`。
- 解析 `./actions/{robot_id}/{policy_id}.md` 的 YAML frontmatter。
- 汇总 `robot_id`、`policy_id`、`actions`、`required_parameters`、`input_mapping`、`resources`、`timeout_s`、`completion`。
- 生成 `/agent/runtime/capabilities` 的 `policies` 和 `actions` 视图。
- MVP+ 阶段强制串行执行 action，不提供配置化并行。

#### Dora IO Adapter

负责：

- 将 Gateway command queue 转为 `PolicyCommand` 输出。
- 接收 `policy_command_status`、`runtime_status`、`proprio_state`、`action`、`record_status`、`playback_status`、`image/*` 等输入。
- 将输入事件交给 Runtime State Aggregator。

#### Runtime State Aggregator

负责：

- 根据事件更新 SessionState / CommandState / NodeStatus。
- 处理 timeout。
- 处理 result。
- 维护 runtime readiness。

#### Runtime Context Builder

负责生成：

- Agent 可读 runtime status。
- capabilities。
- active session。
- current session summary。
- last result。
- failure reason。
- environment summary。

### 2.3 状态模型

#### SessionState

```json
{
  "session_id": "sess_...",
  "status": "running",
  "created_at": 1710000000.0,
  "updated_at": 1710000001.0,
  "action_type": "grasp",
  "instruction": "抓取桌面上的红苹果",
  "source": "paos-agent",
  "target": "red_apple",
  "command_ids": ["cmd_..."],
  "message": ""
}
```

状态：

```text
queued
running
succeeded
failed
cancelled
```

MVP+ 不实现复杂排队策略，也不允许通过配置开启并行。同一 robot 强制只允许一个 `queued/running` session。

#### CommandState

```json
{
  "command_id": "cmd_...",
  "session_id": "sess_...",
  "policy_id": "sam3",
  "command": "grasp_simple",
  "action_type": "grasp",
  "inputs": {
    "target_name": "red_apple",
    "session_id": "sess_...",
    "command_id": "cmd_...",
    "policy_id": "sam3"
  },
  "status": "running",
  "request_id": "cmd_...",
  "created_at": 1710000000.0,
  "updated_at": 1710000001.0,
  "sent_at": 1710000000.2,
  "message": "",
  "outputs": {}
}
```

状态：

```text
queued
sent
running
succeeded
failed
cancelled
```

#### NodeStatus

```json
{
  "node_id": "sam3_policy",
  "node_type": "policy",
  "status": "running",
  "phase": "planning",
  "updated_at": 1710000002.0,
  "active_command_id": "cmd_...",
  "last_error": null
}
```

### 2.4 状态转换

```text
POST /agent/sessions
  -> session created
  -> command created
  -> queued

Gateway emits PolicyCommand
  -> sent

policy_command_status accepted/running
  -> running

policy_command_status done
  -> succeeded

policy_command_status rejected/error
  -> failed

cancel requested
  -> cancelled
  -> Gateway sends stop PolicyCommand to original policy
```

### 2.5 `execution_status` 与 `task_status`

MVP+ 必须区分：

```text
execution_status:
  policy command 是否完成

task_status:
  任务语义是否真正成功
```

原因：当前很多 policy 只能知道动作序列是否完成，无法判断真实任务是否成功。

示例：

```json
{
  "execution_status": "succeeded",
  "task_status": "unknown",
  "success": null,
  "message": "policy sequence finished; task success is not verified"
}
```

后续可通过 verifier / evaluator node 补齐 `task_status`。

### 2.6 SAM3 Policy 改造要求

`sam3_policy` 已按 MVP+ 协议做最小改造：

1. 订阅 `policy_command`。
2. 解析 `forge_msgs.PolicyCommand`。
3. 将 `PolicyCommand.command` 映射到原业务动作 mode。
4. 从 `PolicyCommand.inputs` 读取：
   - `session_id`
   - `command_id`
   - `target`
   - `target_name`
   - `instruction`
5. 保持原 `action` 输出。
6. 输出 `policy_command_status`。

`sam3_policy` 内部需要维护 policy-local state：

```text
current_session_id
current_command_id
current_mode
current_phase
last_command
active_step
step_queue
started_at
last_progress_at
last_error
```

但不应维护全局 runtime state。

### 2.7 Dora Topics

#### Gateway 输出

```text
policy_command
```

#### Gateway 输入

```text
policy_command_status
runtime_status
proprio_state
action
record_status
playback_status
image/*
```

#### `policy_command_status`

使用 `forge_msgs.PolicyCommandStatus`。

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

Gateway 优先用 `request_id` 关联 `CommandState`；`request_id` 为空时可尝试使用 `outputs.command_id`。

### 2.8 Runtime Context

Gateway 生成 `runtime_context.json`：

```json
{
  "updated_at": 1710000000.0,
  "capabilities": {
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
        "robot_id": "piper",
        "actions": {
          "grasp": {
            "command": "grasp_simple",
            "required_parameters": ["target_name"]
          }
        }
      }
    }
  },
  "readiness": {
    "ready": true,
    "missing": []
  },
  "active_session_id": "sess_...",
  "sessions": {},
  "commands": {},
  "nodes": {},
  "last_result": {},
  "last_error": null,
  "runtime": {
    "current_frame_count": 100,
    "sim_status": {},
    "record_status": {},
    "playback_status": {}
  }
}
```

MVP+ 中，PAOS Agent 通过 API 读取该 context；Markdown mirror 只是兼容和审计。

### 2.9 Event Log

Gateway 写 JSONL：

```json
{"ts":1710000000.0,"type":"session_created","data":{"session":{"session_id":"sess_..."},"command":{"command_id":"cmd_..."}}}
{"ts":1710000000.2,"type":"command_sent","data":{"command_id":"cmd_..."}}
{"ts":1710000012.4,"type":"policy_command_status","data":{"request_id":"cmd_...","status":"done"}}
{"ts":1710000013.0,"type":"session_cancelled","data":{"session_id":"sess_..."}}
```

MVP+ 重启恢复策略：

- Gateway 重启后加载 snapshot。
- 不恢复未完成的低层 action；未完成 session 需要由上层重新查询或重新发起。
- 不尝试恢复正在执行的低层 action。

### 2.10 Watchdog MVP+ 范围

MVP+ 做：

- readiness
- status aggregation
- `policy_command_status` 状态回流
- cancel/stop 上层控制
- VLA/长动作的简单停止语义：Gateway 将 session 标记为 `cancelled`，并向原 policy 下发 `stop`

MVP+ 不做：

- 实时安全裁剪
- 硬件 E-stop
- LLM 介入实时控制
- 自动 recovery
- 可配置并行动作
- VLA 任务完成自动判定

后续中长期再做：

- node heartbeat protocol
- cancel acknowledgement
- reset acknowledgement
- estop dataflow
- verifier/evaluator
- Agent 任务级 retry/replan
