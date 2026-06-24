# PAOS-Forge 融合总体设计

### 1.1 背景与目标

当前 PAOS preview 分支已经完成 Runtime v2 会话化改造，旧 `ACTION.md + hal_watchdog + policy_http` 链路已从主线移除。继续基于旧 `command_server` 或旧 HAL watchdog 做 PAOS-Forge 融合，会引入新的兼容层和重复 gateway。

新的融合方向应直接以 Forge 内置 gateway 为 runtime 控制面，以 Forge Dora dataflow 作为执行层：

```text
PAOS Agent Layer
  |
  | /agent/* API
  v
Forge Gateway
  |
  | forge_msgs.PolicyCommand
  v
Forge Dataflow Execution Plane
  |
  +--> policy node
  +--> task_robot
  +--> robot / sim / sensor / recorder nodes
  |
  | policy_command_status / runtime_status / state
  v
Forge Gateway
  |
  | runtime context / result / lessons mirror
  v
PAOS Agent Layer
```

核心目标：

- PAOS 不再维护底层 runtime execution model。
- Forge Gateway 成为 Agent 和执行层之间的唯一稳定边界。
- Forge dataflow 承担 policy、robot、sim、sensor、recorder、benchmark plugin 的执行。
- PAOS Agent 只通过 command / context / result 协议与 Forge 交互。

### 1.2 非目标

MVP+ 阶段不做以下事项：

- 不继续沿用旧 `ACTION.md + hal_watchdog + policy_http` 主链路。
- 不将 PAOS Runtime v2 的 `TargetSessionHandle`、`BaseRolloutTarget`、`PerceptionRuntime`、`OpenPISkillRuntime` 原样迁入 Forge。
- 不实现完整工业安全 watchdog 和硬件 E-stop。
- 不实现 Game Agent。
- 不实现 LIBERO / RoboCasa 等 benchmark 的具体 plugin，只定义规划接口。
- 不引入数据库作为强一致状态存储。

### 1.3 边界划分

#### PAOS Agent Layer

PAOS 保留：

- 自然语言理解
- Agent 工具选择
- Critic / 任务前校验
- 任务规划和重试决策
- 对 runtime context 的理解
- 任务后总结、lessons、memory 使用

PAOS 不再负责：

- target lifecycle
- skill runtime loop
- perception runtime loop
- policy client lifecycle
- robot/sim adapter execution
- session runner / watchdog 执行

#### Forge Gateway

Forge Gateway 负责：

- 提供 `/agent/*` API。
- 分配 `session_id` 和 `command_id`。
- 维护轻量 session / command 状态。
- 从 `./actions/{robot_id}/{policy_id}.md` action manifest 解析可用动作。
- 将 Agent action 转换为 `forge_msgs.PolicyCommand`。
- 汇总 policy、robot、sim、sensor、recorder 的状态。
- 生成 Agent 可读 runtime context。
- 写出 JSONL 事件日志和 context snapshot。
- 支持 session cancel，并向对应 policy 下发 `stop`。
- 为后续 watchdog、reset、estop、benchmark API 预留接口。

#### Forge Dataflow Execution Plane

Forge dataflow 负责：

- 执行 policy。
- 输出 robot action。
- 路由 `JointState` / `JointCommand`。
- 执行真机或仿真。
- 采集传感器数据。
- 输出状态事件和结果事件。
- 后续支持 recorder、benchmark plugin、verifier。

### 1.4 对 PAOS Runtime v2 Session 的取舍

PAOS Runtime v2 的 session 当前承担了多种职责：

- 任务队列
- target / skillruntime 绑定
- policy / target endpoint 路由
- 执行参数
- 超时和重试
- preflight
- safety profile
- result / lesson 写回

Forge 替代 runtime 后，这些职责应拆分：

| 原 PAOS Runtime v2 职责 | 新架构归属 |
|---|---|
| `session_id` / 任务描述 | Forge Gateway 轻量 session |
| `target_ref` / `skillruntime_ref` | Forge action manifest / command mapping |
| `policy_endpoint` / `target_endpoint` | Forge dataflow 配置 |
| `max_steps` / `control_hz` / chunk 参数 | policy node / sim node / dataflow config |
| preflight | Gateway readiness + 后续 capability check |
| safety profile | Gateway safety policy + driver/node safety，MVP 只预留 |
| result / lesson | Gateway result/context mirror，PAOS Agent 消费 |
| `SessionRunner` | 不迁移，由 Forge dataflow 替代 |

关键原则：

```text
保留 session 语义，不保留 PAOS Runtime v2 的 session 执行对象模型。
```

### 1.5 Game Agent 与 Benchmark

#### Game Agent

Game Agent 暂时作为独立 Agent 分支，不纳入 PAOS-Forge runtime 融合主线。

Gateway 协议可以预留 `target_kind` 字段，但 MVP+ 不实现 `game` target。

#### Benchmark

Benchmark 采用规划设计，不进入 MVP+ 实现。

推荐方向：

```text
Benchmark 框架作为外部 server 或 plugin node 接入 Forge。
Forge core 提供 benchmark protocol、gateway API、result aggregator。
具体 LIBERO / RoboCasa / Behavior 等接入在模块开发阶段细化。
```

MVP+ 只预留：

- `/agent/benchmarks`
- benchmark context schema
- benchmark result schema

### 1.6 分阶段改造重心

#### Phase 0：协议冻结

目标：PAOS、Gateway、Forge policy 可以并行开发。

产出：

- Agent Command Protocol
- Runtime Feedback Protocol
- Runtime Context Protocol
- PolicyCommand 输入规范
- `policy_command_status` 输出规范
- action manifest 路径与字段规范

#### Phase 1：Forge Gateway MVP+

目标：基于 Forge 内置 gateway 增加 Agent-facing 能力。

新增：

- `/agent/sessions`
- `/agent/sessions/{session_id}`
- `/agent/runtime/status`
- `/agent/runtime/context`
- `/agent/runtime/capabilities`
- 轻量 SessionState / CommandState
- 内存状态表
- JSONL 事件日志
- `runtime_context.json` snapshot
- `PolicyCommand` output
- `PolicyCommandStatus` input
- `./actions/{robot_id}/{policy_id}.md` manifest 解析
- 同一 robot 强制串行执行 action

#### Phase 2：SAM3 Policy 支持 `PolicyCommand`

目标：抛弃旧 `command_server` 主线，让现有 SAM3 policy 对齐 Forge 标准协议。当前 MVP+ 已在 `sam3_grasp_runner` 中使用 `gateway/policy_command` 与 `sam3_policy/policy_command_status` 打通闭环。

改造：

- `sam3_policy` 订阅 `policy_command`。
- 从 `PolicyCommand.command` 解析业务动作 mode。
- 从 `PolicyCommand.inputs` 读取 `target_name`、`session_id`、`command_id`。
- 保持原 `action` 输出不变。
- 输出 `policy_command_status`。
- `sam3_grasp_runner/dataflows/sim/sam3_dataflow_sim.yaml` 和 real dataflow 将 `sam3_policy/policy_command_status` 回连到 Gateway。

#### Phase 3：Feedback 闭环

目标：Gateway 能够基于 `PolicyCommandStatus.request_id` 维护 session 状态。

新增：

- `policy_command_status` 回流
- `request_id == command_id` 关联
- `accepted/running/done/rejected/error` 到 Gateway command/session 状态映射
- runtime context 更新

#### Phase 4：Context 镜像与 Agent 消费

目标：PAOS Agent 可以稳定读取下层能力、状态、结果。

新增：

- `runtime_context.json`
- 可选 `FORGE_RUNTIME.md`
- 可选 `ENVIRONMENT.md` mirror
- 可选 `LESSONS.md` append

#### Phase 5：Watchdog 基础能力

目标：非实时安全监督。

新增：

- readiness check
- stale detection
- node heartbeat
- policy timeout
- cancel 基础接口：Gateway 将目标 session 标记为 `cancelled`，并向原 policy 下发 `stop`
- reset 基础接口
- estop placeholder

#### Phase 6：Benchmark Protocol

目标：规划 benchmark server / plugin 接入，不实现具体 benchmark。

新增：

- `/agent/benchmarks`
- benchmark job schema
- benchmark status/result context
