# PAOS Forge Gateway MVP+

本文档面向当前 MVP+ 验证：PAOS 保留 Agent 语义层，Forge Gateway / Dora dataflow 承担底层动作执行。当前目标是跑通 Phase 3 闭环，不替换全部 PAOS Runtime v2 代码。

## Quick Start

### 1. 启动 Forge Gateway Dataflow

以 `sam3_grasp_runner` 仿真为例：

```bash
cd /path/to/sam3_grasp_runner
bash scripts/run_sim_rgbd.sh
```

确认 Gateway 可访问：

```bash
curl -sS http://127.0.0.1:9001/agent/runtime/capabilities | jq
```

预期能看到：

- `supports.sessions: true`
- `supports.serial_actions_only: true`
- `actions.grasp`
- `actions.place`
- `actions.check_target`
- `actions.go_home`

### 2. 初始化 PAOS Runtime Workspace

```bash
cd /path/to/PhyAgentOS
python scripts/init_runtime_workspace.py --workspace ~/.PhyAgentOS/workspace
```

该命令会创建：

- `TARGETS.md`
- `SKILLRUNTIME.md`
- `SESSIONS.md`
- `RUNTIME.md`
- `ENVIRONMENT.md`
- `configs/runtime/*`

如果文件已存在，默认不会覆盖；只有需要重置模板时才使用 `--force`。

### 3. 启用 Forge Gateway Target

在 `~/.PhyAgentOS/workspace/TARGETS.md` 中启用 `forge_gateway`：

```yaml
- id: forge_gateway
  target_class: remote
  target_kind: simulation
  enabled: true
  workspace: workspaces/forge_gateway
  supported_skillruntimes:
    - forge_gateway_sam3
  runtime:
    target_runtime: ForgeGatewayRuntime
    target_endpoint: http://127.0.0.1:9001
    target_adapter: target_adapter://forge_gateway_passthrough
    runtime_contract_ref: configs/runtime/contracts/forge_gateway.runtime.yaml
```

`target_endpoint` 指向 Forge Gateway HTTP 地址。旧 workspace 可能仍使用 `forge_gateway_piper_sim`，建议迁移到 `forge_gateway`。

### 4. 启动 PAOS Agent

开发分支验证时推荐使用源码入口，避免加载环境中旧版 `paos`：

```bash
cd /path/to/PhyAgentOS
python -m PhyAgentOS agent --workspace ~/.PhyAgentOS/workspace --logs
```

如果希望 `paos` 命令也指向当前源码：

```bash
cd /path/to/PhyAgentOS
python -m pip install -e .
```

## 命令示例

### 自然语言动作

PAOS Agent 会读取 runtime workspace 中的 `RUNTIME.md`、`TARGETS.md`、`SKILLRUNTIME.md` 和 `SESSIONS.md`。动作类请求会被翻译成 `SESSIONS.md` 中的 `runtime_hints.gateway_action`。

示例：

```text
帮我通过 Forge Gateway 抓取苹果
检查一下桌面上是否有 apple
让机械臂回到初始位
```

常用映射：


| 用户意图       | `gateway_action.action_type` | 关键参数                 |
| ---------- | ---------------------------- | -------------------- |
| 抓取/拿起/夹取苹果 | `grasp`                      | `target_name: apple` |
| 放下/放置物体    | `place`                      | `target_name` 或放置描述  |
| 检查是否有苹果    | `check_target`               | `target_name: apple` |
| 回到初始位/回家   | `go_home`                    | 无必需目标                |


### 手动追加 Action Session

如果不通过自然语言，也可以手动向 `SESSIONS.md` 追加 pending session：

```yaml
- session_id: sess_gateway_grasp_apple
  goal_id: goal_gateway_sam3
  target_ref: target://forge_gateway
  skillruntime_ref: skillruntime://forge_gateway_sam3
  task_description: grasp apple through Forge Gateway
  status: pending
  priority: normal
  routing:
    target_endpoint: http://127.0.0.1:9001
    policy_endpoint: null
  runtime_hints:
    gateway_action:
      action_type: grasp
      target_name: apple
      source: paos-agent
      inputs:
        auto_home: false
  result: {}
```

然后手动执行一次 watchdog：

```bash
cd /path/to/PhyAgentOS
python scripts/run_runtime_watchdog.py --workspace ~/.PhyAgentOS/workspace --once
```

### 场景复位

场景复位不是普通 action session。不要向 `SESSIONS.md` 追加 `action_type: reset`，应直接调用 Agent command adapter：

```bash
cd /path/to/PhyAgentOS
python -m PhyAgentOS.runtime.gateway.command_adapter --workspace ~/.PhyAgentOS/workspace reset
```

该命令会读取 `TARGETS.md` 中的 Gateway endpoint，并调用：

```http
POST /agent/runtime/reset
```

Gateway 内部复用 `reset_scene` runtime 命令，由 dataflow 完成仿真环境复位。

### 验证状态

查看 Gateway runtime context：

```bash
curl -sS http://127.0.0.1:9001/agent/runtime/context | jq
```

查看 PAOS session 状态：

```bash
rg "sess_gateway|status:|result:" ~/.PhyAgentOS/workspace/SESSIONS.md
```

查看 PAOS runtime log：

```bash
sed -n '1,200p' ~/.PhyAgentOS/workspace/LOG.md
```

## 当前调用链路

当前实现同时存在两条链路。

### Action Session 链路

动作类任务走现有 PAOS Runtime v2 bridge：

```text
用户自然语言
  -> PAOS Agent
  -> 写入 SESSIONS.md
  -> WatchdogSupervisor
  -> GatewaySessionRunner
  -> POST /agent/sessions
  -> Forge Gateway
  -> Dora PolicyCommand
  -> policy_command_status
  -> PAOS SessionResult / LOG.md
```

触发条件是 session 绑定到 Forge Gateway target 或 skillruntime：

```yaml
target_ref: target://forge_gateway
skillruntime_ref: skillruntime://forge_gateway_sam3
runtime_hints:
  gateway_action:
    action_type: grasp
```

代码入口：

- `PhyAgentOS/runtime/gateway/session_runner.py`
- `PhyAgentOS/runtime/watchdog/supervisor.py`
- `PhyAgentOS/runtime/gateway/client.py`

这条链路适合需要 session 状态和结果写回的动作，例如 `grasp`、`place`、`check_target`、`go_home`。

### Runtime Command 链路

非 action session 的运行时控制命令走 command adapter：

```text
PAOS Agent / manual command
  -> ForgeGatewayCommandAdapter
  -> ForgeGatewayClient
  -> POST /agent/runtime/reset
  -> Forge Gateway
  -> reset_scene
  -> Dora dataflow
```

代码入口：

- `PhyAgentOS/runtime/gateway/command_adapter.py`
- `PhyAgentOS/runtime/gateway/client.py`

当前已支持：

```bash
python -m PhyAgentOS.runtime.gateway.command_adapter --workspace ~/.PhyAgentOS/workspace reset
```

## 后续规划

当前 `SESSIONS.md + WatchdogSupervisor + GatewaySessionRunner` 是 Phase 3 兼容路径，用于最小代价接入 PAOS Runtime v2 的会话队列。

后续建议逐步收敛为统一的 Agent command adapter：

```text
用户自然语言
  -> PAOS Agent planner
  -> ForgeGatewayCommandAdapter
  -> Forge Gateway /agent/*
  -> Forge dataflow
  -> runtime context / result
  -> PAOS Agent
```

目标 adapter 形态：

```python
adapter.get_capabilities()
adapter.create_action_session(action_type="grasp", inputs={"target_name": "apple"})
adapter.get_session(session_id)
adapter.cancel_session(session_id)
adapter.reset_runtime()
adapter.get_context()
```

长期目标是让 PAOS Agent 只理解 Gateway capabilities、action manifest、runtime context 和 result，不再依赖 PAOS Runtime v2 的 target / skillruntime 执行模型。