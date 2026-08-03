# PAOS Forge Gateway MVP+

本文档面向当前 MVP+ 验证：PAOS 保留 Agent 语义层，Forge Gateway / Dora dataflow 承担底层动作执行。当前目标是跑通 Phase 3 闭环，不替换全部 PAOS Runtime v2 代码。

## Quick Start

### 1. 拉取 SAM3 Forge Bundle

从 `PhyAgentOS` 仓库目录执行：

```bash
cd /path/to/PhyAgentOS
bash examples/fetch_forge_sam3_bundle.sh
```

默认会下载并解压到与 `PhyAgentOS` 同级的：

```text
../sam3_bundle
```

该 bundle 内已经包含 Forge runtime 二进制、策略二进制、dataflow、配置和启动脚本。

可选环境变量：

```bash
VERSION=latest bash examples/fetch_forge_sam3_bundle.sh
```

如对象存储路径变化，可覆盖：

```bash
SAM3_URL='https://.../sam3_bundle.zip' bash examples/fetch_forge_sam3_bundle.sh
SAM3_BASE_URL='https://.../sam3_bundle/${VERSION}' bash examples/fetch_forge_sam3_bundle.sh
```

### 2. 按 bundle 内说明准备运行文件

进入 bundle：

```bash
cd ../sam3_bundle
```

按 bundle 内 `README.md` 准备：

- `sam3.pt`
- 真机需要的 `calibration_result.npz`
- 真机相机内参：`configs/real/sam3_policy.yaml`

手眼标定流程见 bundle 内：

```text
docs/handeye-calibration.md
```

### 3. 启动 Forge Gateway Dataflow

仿真：

```bash
cd ../sam3_bundle
SAM3_SKIP_UV_SYNC=1 bash scripts/run_sim_rgbd.sh
```

真机：

```bash
cd ../sam3_bundle
SAM3_SKIP_UV_SYNC=1 bash scripts/run_real.sh
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

### 4. 初始化 PAOS Runtime Workspace

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

### 5. 启用 Forge Gateway Target

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
  observation:
    observation_type: multimodal
    empty_observation_allowed: false
  config:
    gateway_api: paos-forge-gateway-mvp-plus.v1
    verification:
      required_image_sources: [image/front]
      capture_timeout_s: 5
      post_capture_timeout_s: 5
      max_artifact_bytes: 8388608
      association_quality: best_effort
```

`target_endpoint` 指向 Forge Gateway HTTP 地址。旧 workspace 可能仍使用 `forge_gateway_piper_sim`，建议迁移到 `forge_gateway`。
`required_image_sources` 必须与 Gateway 配置的 `image_input_ids` 完全一致；示例中的
`image/front` 不是硬编码行为规则，应按部署实际相机源修改。

在 PAOS `config.json` 中可配置 Agent-owned verifier：

```json
{
  "agents": {
    "verification": {
      "serviceEnabled": true,
      "model": null,
      "provider": null,
      "timeoutS": 180,
      "evidenceRetention": "failed",
      "maxReplansPerEpisode": 2,
      "maxVerifierCallsPerRun": 50,
      "replanTimeoutS": 120,
      "serviceHost": "127.0.0.1",
      "servicePort": 8100
    }
  }
}
```

`model/provider` 为空时沿用 Agent 默认模型和 provider。证据保留策略支持 `all`、
`failed`、`none`；即使实体证据按策略删除，bundle 中的 digest、来源、时间和删除审计仍保留。

### 6. 启动 PAOS Agent

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
  verification:
    mode: recovery
    goal: grasp the apple and leave it securely held by the robot
    success_criteria:
      - the apple is visibly secured in the gripper after execution
    constraints:
      - do not disturb unrelated objects
    evidence_policy:
      profile: forge_visual_default
      required_kinds: [rgb_image]
      required_sources: []
      minimum_association: best_effort
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

如果使用 `off` 模式，可手动执行一次 watchdog。非 `off` 模式还要求 Agent-owned
Verifier 正在运行；常规做法是通过 `python -m PhyAgentOS agent` 启动 Agent、Watchdog
和 Verifier，而不是仅运行独立 watchdog：

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

当前实现对 action session 和 runtime command 保留两条入口，但 action session 已统一
接入系统级 verification 生命周期。

### Action Session 链路

动作类任务走现有 PAOS Runtime v2 bridge：

```text
用户自然语言
  -> PAOS Agent
  -> 写入 SESSIONS.md
  -> WatchdogSupervisor
  -> GatewaySessionRunner
  -> ForgeAdapter capability preflight
  -> /ws/images + /ws/state capture before
  -> POST /agent/sessions
  -> Forge Gateway
  -> Dora PolicyCommand
  -> policy_command_status
  -> /agent/sessions/{session_id} terminal identity check
  -> /ws/images + /ws/state capture after
  -> ExecutionRecord + forge_evidence_bundle_v1
  -> awaiting_verification -> Agent Verifier
  -> succeeded / failed / awaiting_replan
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
- `PhyAgentOS/runtime/gateway/adapter.py`
- `PhyAgentOS/runtime/gateway/observation.py`
- `PhyAgentOS/runtime/gateway/evidence.py`
- `PhyAgentOS/runtime/watchdog/supervisor.py`
- `PhyAgentOS/runtime/gateway/client.py`

Gateway `/agent/sessions` 和 `policy_command_status.request_id == command_id` 是唯一执行
终态来源。Adapter 不使用静稳、固定等待或按动作定制的完成推断。Gateway 1.0.0 没有
Evidence API，因此 WebSocket 证据关联明确标为 `best_effort`。

Verifier 只读取任务 `goal`、`success_criteria`、`constraints`、Execution Record 和
Evidence Bundle。它不读取或产生诸如 `grasp_verify_enabled` 的行为开关，也不会把
Gateway `succeeded` 直接解释为任务成功。

模式语义：

- `off`：按 Gateway 执行事实终结。
- `audit`：记录 verdict，保留执行派生终态，绝不 recovery。
- `enforce`：verdict 决定任务结果，缺证或 verifier 错误 fail closed。
- `recovery`：只有 `replan_required` 可回到正常 Agent Planner；Planner 必须通过
  `create_replanned_session` 创建新 ID、新 runtime hints 和新 Gateway command ID。

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

## 兼容边界

本接入仅支持 Forge Gateway 1.0.0，要求 capabilities 的
`api_version == paos-forge-gateway-mvp-plus.v1` 以及 `sessions`、`command_id`、
`runtime_context`、`serial_actions_only` 能力。旧 `forge_runtime` Gateway 不在兼容范围。
所有适配、证据、验证和 recovery 代码均位于 PhyAgentOS；不会修改 Forge Gateway、
Forge Runtime 或 Dora dataflow。
