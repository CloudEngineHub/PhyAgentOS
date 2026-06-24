# Forge Gateway Action Manifest 组织设计

## 1. 背景与目标

PAOS-Forge 融合后，PAOS Agent 负责高层任务理解、规划与决策，Forge Gateway 负责将 Agent action 稳定映射到 Forge dataflow 内的 policy command，并汇总运行时状态。

因此，Gateway 的 action 定义不应长期写在 `config.yaml` 中。`config.yaml` 更适合描述端口、状态目录、readiness、`policy_id` 等基础运行配置；而 action 是面向 Agent 和人的能力说明，应该以类似 PAOS `SKILLS.md` 的方式组织成 Markdown manifest。

本设计目标：

- 将 action 能力定义从基础配置中拆出。
- 使用 Markdown 作为 Agent/人类可读上下文。
- 使用 YAML frontmatter 作为 Gateway 可解析的确定性协议源。
- 支持同一 robot 下多个 policy manifest。
- 为复杂多步骤任务保留 Gateway 层支持能力，但短期不改造 PAOS Agent 代码。

## 2. 路径规范

推荐路径：

```text
./actions/{robot_id}/{policy_id}.md
```

示例：

```text
actions/
└── piper/
    ├── sam3.md
    ├── nav.md
    └── pour.md
```

路径语义：

- `{robot_id}` 表示机器人或运行目标，例如 `piper`、`franka`、`aloha`、`mujoco_piper`。
- `{policy_id}` 表示 Forge dataflow 内可接收 `PolicyCommand.policy_id` 的 policy 节点或策略能力域，例如 `sam3`、`nav`、`pour`。
- 一个文件只描述一个 `robot_id + policy_id` 下的 action 集合。
- Gateway 可加载多个 manifest，并汇总为 `/agent/runtime/capabilities`。

与 `./actions/{policy}_{robot}.md` 相比，`./actions/{robot_id}/{policy_id}.md` 更利于按机器人隔离能力集，也更符合未来多 policy、多机器人、多部署环境的组织方式。

## 3. Gateway 配置方式

Gateway 基础配置只保存 manifest 路径，不直接内嵌 action 映射。

示例：

```yaml
agent:
  enabled: true
  state_dir: /tmp/paos_forge_gateway_state
  write_context_snapshot: true
  action_manifests:
    - ./actions/piper/sam3.md
    - ./actions/piper/nav.md
    - ./actions/piper/pour.md
```

路径解析建议：

- 相对路径优先相对 Gateway 配置文件所在目录解析。
- 也可支持绝对路径，方便部署包外置 manifest。
- Gateway 启动时解析 manifest，失败时应明确报错，避免运行时 action 路由不确定。
- MVP 阶段可保留内置默认 manifest 作为 fallback，但生产部署应显式配置 `action_manifests`。

当前实现：

- Gateway 包内置默认 manifest：`forge_runtime/packages/nodes/gateway/actions/piper/sam3.md`。
- `sam3_grasp_runner` 仿真配置显式使用：`sam3_grasp_runner/actions/piper/sam3.md`。
- `sam3_grasp_runner/configs/common/sam3_gateway.yaml` 通过 `agent.action_manifests: ../../actions/piper/sam3.md` 加载 action。
- `sam3_grasp_runner/dataflows/sim/sam3_dataflow_sim.yaml` 将 `sam3_policy/policy_command_status` 回连到 `gateway/policy_command_status`。

## 4. Manifest 文件结构

Manifest 使用 Markdown + YAML frontmatter。Gateway 只解析 frontmatter，Markdown 正文作为 Agent/人类可读说明。

Frontmatter 示例：

```yaml
---
version: 1
robot_id: piper
policy_id: sam3
policy_command_topic: gateway/policy_command
status_topic: sam3_policy/policy_command_status
actions:
  grasp:
    command: grasp_simple
    required_parameters: ["target_name"]
    input_mapping:
      target: target_name
      target_name: target_name
    resources: ["arm", "gripper", "camera"]
    timeout_s: 120
    result_semantics: command_completed
    completion:
      type: policy_status
    description: "抓取指定目标物体"

  place:
    command: explore_and_place
    required_parameters: ["target_name"]
    input_mapping:
      target: target_name
      target_name: target_name
    resources: ["arm", "gripper", "camera"]
    timeout_s: 120
    result_semantics: command_completed
    completion:
      type: policy_status
    description: "将已抓取物体放置到目标区域"

  check_target:
    command: check_target
    required_parameters: ["target_name"]
    input_mapping:
      target: target_name
      target_name: target_name
    resources: ["camera"]
    timeout_s: 30
    result_semantics: task_verified
    completion:
      type: policy_status
    description: "检查目标物体是否可见"
---
```

Markdown 正文示例：

````markdown
# SAM3 Piper Actions

本文件描述 Piper 机器人在 SAM3 policy 下可供 PAOS Agent 调用的高层动作。

## 约束

- `grasp` 需要目标物体在相机视野中可检测。
- `place` 默认表示将已抓取物体放置到指定目标区域。
- 当前 `succeeded` 表示 policy 已接受并完成命令级反馈，不等价于长期任务目标一定成功。

## 示例

抓取苹果：

```json
{
  "action_type": "grasp",
  "target_name": "apple"
}
```
````

设计原则：

- Gateway 只解析 frontmatter，不从 Markdown 正文推断协议。
- Markdown 正文用于 Agent 上下文、人类说明、限制条件、示例、已知失败模式。
- `actions.*.command` 映射到 `forge_msgs.PolicyCommand.command`。
- `policy_id` 映射到 `forge_msgs.PolicyCommand.policy_id`。
- `required_parameters` 用于 Gateway 入参校验。
- `input_mapping` 用于兼容 Agent 参数命名与 policy 输入命名。
- `timeout_s` 可作为 Watchdog MVP+ 的命令超时参考。
- `resources` 用于描述该 action 可能占用的机器人资源；MVP+ 仅记录，不用于开启并行。
- `completion` 用于描述 Gateway 如何判断该 action 的命令级完成状态。

## 5. Capabilities 汇总

Gateway 启动后解析所有 action manifest，并在 `/agent/runtime/capabilities` 中返回结构化能力清单。

示例：

```json
{
  "api_version": "paos-forge-gateway-mvp-plus.v1",
  "robot_id": "piper",
  "supports": {
    "sessions": true,
    "command_id": true,
    "runtime_context": true,
    "serial_actions_only": true
  },
  "policies": {
    "sam3": {
      "manifest": "./actions/piper/sam3.md",
      "actions": {
        "grasp": {
          "command": "grasp_simple",
          "required_parameters": ["target_name"],
          "description": "抓取指定目标物体"
        },
        "place": {
          "command": "explore_and_place",
          "required_parameters": ["target_name"],
          "description": "将已抓取物体放置到目标区域"
        }
      }
    },
    "nav": {
      "manifest": "./actions/piper/nav.md",
      "actions": {
        "move_to": {
          "command": "move_to",
          "required_parameters": ["location"],
          "description": "移动到指定语义位置"
        }
      }
    }
  }
}
```

为了方便 PAOS Agent 获取完整上下文，Gateway 可在 `/agent/runtime/context` 中附带：

- 当前已加载 manifest 列表。
- 每个 policy 的 action 摘要。
- 当前 robot/environment 状态。
- 最近一次 command/session 结果。
- 可选的 manifest Markdown 原文路径或摘要。

## 6. Agent Session 到 PolicyCommand 的映射

PAOS Agent 仍通过 `/agent/sessions` 创建单步 session。

请求示例：

```json
{
  "session_id": "sess_grasp_001",
  "command_id": "cmd_grasp_001",
  "action_type": "grasp",
  "target_name": "coffee_cup",
  "source": "paos-agent"
}
```

Gateway 根据 manifest 解析：

```text
action_type=grasp
  -> policy_id=sam3
  -> command=grasp_simple
  -> inputs.target_name=coffee_cup
  -> request_id=cmd_grasp_001
```

下发到 Forge：

```json
{
  "policy_id": "sam3",
  "command": "grasp_simple",
  "request_id": "cmd_grasp_001",
  "inputs_json": {
    "session_id": "sess_grasp_001",
    "command_id": "cmd_grasp_001",
    "action_type": "grasp",
    "target_name": "coffee_cup",
    "source": "paos-agent"
  }
}
```

policy 返回 `PolicyCommandStatus` 后，Gateway 通过 `request_id` 或 `outputs.command_id` 关联 `CommandState`，并更新 session 到 `running`、`succeeded`、`failed`、`cancelled` 等状态。

## 7. 复杂任务支持方案

示例复杂任务：

```text
移动到茶水间 -> 抓起咖啡杯 -> 倒咖啡 -> 将咖啡杯送回桌上
```

底层可能涉及多个 policy：

```text
nav.move_to(location="tea_room")
sam3.grasp(target_name="coffee_cup")
pour.pour_into(target_name="coffee_cup", source="coffee_machine")
nav.move_to(location="desk")
sam3.place(target_name="desk")
```

短期推荐采用 **Agent-orchestrated workflow**：

1. PAOS Agent 读取 `/agent/runtime/capabilities` 和 action manifest。
2. Agent 根据用户目标生成步骤计划。
3. Agent 逐步调用 `/agent/sessions`。
4. 每一步等待 Gateway 返回 `succeeded` 或 `failed`。
5. Agent 根据 `/agent/runtime/context` 判断下一步、重试或终止。

该模式下：

- PAOS Agent 是 planner 和 workflow owner。
- Gateway 不负责长程任务规划。
- Gateway 负责 action 校验、policy 路由、session/command 状态、runtime context 聚合。
- Forge dataflow 负责实际 policy 执行与反馈。

### 7.1 Gateway 的职责边界

复杂任务的长程规划不应由 Gateway 控制。Gateway 在架构上是 **上层控制动作入口** 和 **Forge runtime control plane**，不是 planner。

Gateway 应提供：

- 可发现的 action capabilities。
- 稳定的 `/agent/sessions` action 调用入口。
- action 到 `PolicyCommand` 的确定性映射。
- session/command 状态机。
- `runtime_context`、event log、snapshot。
- 可选的 workflow trace 记录。

Gateway 不应负责：

- 将用户自然语言拆成完整长程计划。
- 决定复杂任务的下一步语义动作。
- 根据失败结果自动重写计划。
- 承担跨 policy 的高层任务目标验证。

这些能力更适合保留在 PAOS Agent 层。Gateway 只需要把底层可执行动作、状态和结果稳定暴露给 Agent。

### 7.2 串行与并发策略

MVP+ 阶段采用 **同一 robot 强制串行执行**：

- 同一时刻只允许一个会占用 robot 执行资源的 action 处于 `queued/running`。
- `nav`、`sam3`、`pour` 等不同 policy 可以同时存在于 Forge dataflow 中，但 Gateway 本期不会让它们并发接管同一台 robot。
- 对机械臂、夹爪、底盘、相机感知等 action，本期统一按串行 session 处理。
- 不提供通过 manifest 或 `config.yaml` 打开并行动作的配置项。

Manifest 中可以保留 `resources` 作为未来资源锁元数据：

```yaml
resources: ["arm", "gripper"]
```

但 MVP+ 不根据 `resources` 做并发调度。Gateway 应以全局 active session 约束实现串行执行，例如同一时刻只允许一个 `queued/running` session。未来如果要支持部分动作并发，再基于 `resources` 增加资源锁和冲突检测。

## 8. Gateway 层预留能力

虽然短期不改造 PAOS Agent 层代码，Gateway 仍应为复杂动作保留少量扩展点。MVP+ 只做记录和暴露，不做调度。

### 8.1 Workflow Trace

Gateway 可在内存状态、event log 和 `runtime_context.json` 中记录来自同一上层任务的多个 session。

建议请求字段：

```json
{
  "goal_id": "goal_make_coffee_001",
  "step_index": 2,
  "depends_on": ["cmd_move_to_tea_room"]
}
```

MVP+ 可先只记录，不做调度。

### 8.2 Context Carry-over

上一步 policy 的输出可进入 `runtime_context.last_result`，由 PAOS Agent 读取后决定下一步。Gateway 不理解业务语义，只负责稳定保存和暴露结果。

例如：

```json
{
  "last_result": {
    "policy_id": "sam3",
    "command": "check_target",
    "outputs": {
      "found": true,
      "target_pose": "optional"
    }
  }
}
```

### 8.3 未来预留字段

Manifest 可保留少量未来字段，但 MVP+ 不围绕这些字段实现复杂逻辑：

```yaml
resources: ["arm", "gripper"]
preconditions:
  - runtime.ready == true
  - gripper.empty == true
result_semantics: command_completed
completion:
  type: policy_status
```

这些字段本期主要用于 capabilities 展示和 Agent 提示。并行调度、资源锁、复杂前置条件校验、VLA 结束态判断都不在 MVP+ 范围内。

### 8.4 VLA 简化原则

后续引入 VLA 模型时，需要注意 VLA 可能没有自然结束态。MVP+ 只保留一个原则：不要把 VLA 的“命令已启动”误认为“任务已完成”。

如果某个 VLA action 只能持续运行并等待外部停止，则它的 `result_semantics` 应标记为 `command_accepted` 或类似语义；真正的任务成功应由 PAOS Agent、用户确认或额外 verifier action 判断。Gateway 本期只负责保持 session 状态、支持 cancel/stop，并暴露最新上下文。

## 9. 不建议短期实现的内容

MVP+ 不实现 Gateway workflow engine，也不实现可配置并行动作。Gateway 当前重心是稳定打通 action manifest、串行 session 状态、policy 路由和 context 闭环。

以下能力只保留为后续方向：

- workflow DAG 调度。
- 跨 policy 自动回滚。
- 复杂条件分支。
- 可配置资源并发。
- VLA 任务成功自动判定。

## 10. 分阶段实施建议

### Phase 1：Manifest 外置

- 新增 `action_manifests` 配置。
- 新增 `./actions/{robot_id}/{policy_id}.md` 解析。
- `/agent/runtime/capabilities` 返回 manifest 汇总结果。
- `/agent/sessions` 使用 manifest 做 action -> policy command 映射。
- Gateway 强制保持同一 robot 串行 session，不提供并行配置。

### Phase 2：Context 增强

- `/agent/runtime/context` 暴露 manifest 摘要。
- event log 记录 manifest action、policy_id、robot_id。
- `runtime_context.json` 记录当前 robot/action capabilities。
- 可选记录 `goal_id`、`step_index`、`depends_on`，但只作为 trace，不做调度。

## 11. 结论

`./actions/{robot_id}/{policy_id}.md` 是更合理的 action 组织方式。它把机器人维度、policy 维度和 Agent 可读能力文档自然分开，同时保留 Gateway 对 action 的确定性解析能力。

复杂任务的短期最佳路径不是把 Gateway 改造成 planner，而是让 PAOS Agent 基于 capabilities 和 action manifest 做步骤规划，并逐步调用 `/agent/sessions`。Gateway 保持 runtime control plane 职责，提供 policy 路由、状态跟踪、事件日志、runtime context 和未来 workflow trace 扩展点。
