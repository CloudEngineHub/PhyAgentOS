# PhyAgentOS × Minecraft — Agent 闭环

> 承接 [1_hello.md](1_hello.md)。Agent 通过 SESSIONS.md 下发给 WatchdogSupervisor 执行，形成多轮观察-推理-交互闭环。**当前状态：已完整可运行。**

---

## 已验证链路

| 步骤 | 状态 | 说明 |
|------|------|------|
| `paos agent --workspace` 启动 | ✅ | RuntimeWorkspaceManager 部署模板 + 启动 watchdog |
| ContextBuilder 注入 TARGETS.md/SKILLS.md | ✅ | `EMBODIED_FILES` 包含两者，Agent 系统提示词自动感知 |
| EMBODIED.md 自动部署 | ✅ | `_deploy_embodied_from_targets` 检测 `minecraft_java_env`，部署 `configs/runtime/embodied/minecraft.md` → `EMBODIED.md` |
| Agent 用 `write_file` 写 SESSIONS.md | ✅ | YAML 格式正确，`perception_queries` 使用 `type` + `params` |
| WatchdogSupervisor 拾取 session | ✅ | Preflight 通过（`environment_outputs: []` 跳过 perception 检查） |
| SessionRunner → SafetyClampBridge | ✅ | dict action 自动透传，不触发 numpy 转换 |
| MinecraftTarget.build() | ⚠️ | 需要 `bridge_url` 非空，否则 `TARGET_CONNECTION` |
| action_chunk → bridge HTTP POST | ✅ | MinecraftAdapter → MinecraftTarget → HTTP POST /action |
| 动作结果校验 | ✅ | `run_builtin_loop()` 检查 `ok`/`result` |
| ENVIRONMENT.md 回写 | ✅ | ResultWriter 自动更新 target snapshot |
| Agent 读结果验证 | ✅ | Agent 读 ENVIRONMENT.md 确认执行结果 |

```
paos agent --workspace workspaces/minecraft
  │
  ├─ RuntimeWorkspaceManager     ← 部署 TARGETS.md/SKILLS.md/EMBODIED.md
  ├─ BackgroundWatchdog          ← daemon 线程，轮询 SESSIONS.md
  │    └─ WatchdogSupervisor     ← preflight → resolve → SessionRunner
  │         ├─ TargetRegistry    ← MinecraftTargetRuntime (factory.py:82)
  │         ├─ SkillRegistry     ← MinecraftSkillRuntime (runtime_registry.py)
  │         └─ SessionRunner     ← build → observe → run_builtin_loop
  │              ├─ SafetyClampBridge    ← dict action 自动透传
  │              ├─ MinecraftAdapter     ← to_executable_action_chunk
  │              ├─ TargetSessionHandle  ← action_chunk/observe 封装
  │              └─ MinecraftSkillRuntime ← episode 驱动循环
  │
  └─ AgentLoop                   ← LLM 推理循环
       └─ ContextBuilder         ← 自动注入 6 文件到系统提示词
```

---

## 完整数据通路（v0.1.4 对齐后）

```
              workspace: workspaces/minecraft/
              ┌──────────────────────────────────────────────────────┐
              │                                                      │
              │  EMBODIED.md    ← _deploy_embodied_from_targets 自动部署 │
              │  ENVIRONMENT.md ← watchdog 写入（执行后回写）        │
              │  SESSIONS.md    ← Agent 写 / watchdog 消费           │
              │  LESSONS.md     ← ResultWriter 写入（成功+失败经验）  │
              │  TARGETS.md     ← 包含 minecraft_java_env 条目       │
              │  SKILLS.md      ← 包含 minecraft_navigate 条目       │
              │                                                      │
     ┌────────┴──────────────────────────────────────────────────┐   │
     │  paos agent --workspace workspaces/minecraft              │   │
     │  (watchdog 自动启动，无需手动管理)                          │   │
     │                                                           │   │
     │  AgentLoop:                                               │   │
     │   ContextBuilder 自动注入:                                │   │
     │    ├─ EMBODIED.md         → 16 种动作 + Critic Guidance   │   │
     │    ├─ ENVIRONMENT.md      → bot 当前状态                   │   │
     │    ├─ LESSONS.md          → 历史经验                       │   │
     │    ├─ TARGETS.md          → minecraft_java_env 可用        │   │
     │    └─ SKILLS.md           → minecraft_navigate skill       │   │
     │                                                           │   │
     │  WatchdogSupervisor（后台线程）:                            │   │
     │   轮询 SESSIONS.md → resolve → SessionRunner.start()      │   │
     │   → SkillRuntime.run_builtin_loop()                       │   │
     │   → ResultWriter 写 ENVIRONMENT.md + LESSONS.md           │   │
     │                                                           │   │
     └───────────────────────────────────────────────────────────┘   │
```

---

## 执行时序

```
用户: paos agent --workspace workspaces/minecraft

paos agent 自动:
  ├─ 启动 RuntimeWorkspaceManager（部署模板 + 启动 watchdog）
  └─ 启动 Agent 推理循环

  Agent 上下文（ContextBuilder 自动加载）:
    ├─ TARGETS.md          → 看到 minecraft_java_env 可用
    ├─ SKILLS.md           → 看到 minecraft_navigate skill
    ├─ EMBODIED.md         → 看到 16 种动作 + Critic Guidance
    ├─ ENVIRONMENT.md      → 看到 bot 当前状态（watchdog 回写）
    └─ LESSONS.md          → 看到历史经验

用户: "采集5个橡木原木"

Agent 内部循环:
  iter 1: read_file ENVIRONMENT.md     → pos, nearby_blocks, inventory
  iter 2: LLM 推理 → write_file SESSIONS.md:
            sessions:
              - session_id: mc_001
                target_ref: target://minecraft_java_env
                skill_ref: skill://minecraft_navigate
                task_description: "采集5个橡木原木"
                execution: {max_steps: 30}
                runtime_hints:
                  perception_queries:
                    - {type: collect, params: {block_type: "oak_log", count: 5}}

Watchdog: 轮询到 pending session
  → resolve TARGETS.md → MinecraftTarget(bridge_url=ngrok_url)
  → resolve SKILLS.md → MinecraftSkillRuntime
  → SessionRunner.start():
      build target → start_session → observe (写 ENVIRONMENT.md 初始值)
      run_builtin_loop():
        for action in perception_queries:
          target_handle.action_chunk()  → POST /action
          target_handle.observe()       → GET /state
          写 ENVIRONMENT.md
      → 返回 SkillRuntimeResult

Agent:
  iter 3: read_file ENVIRONMENT.md → last_action=collect, last_action_ok=true
                                   → inventory.hotbar[0]: oak_log×5
  iter 4: LLM: "完成！已采集5个橡木原木" → 回复用户

失败反思:
  iter N: read_file ENVIRONMENT.md → last_action_ok=false
  iter N+1: read_file LESSONS.md → "附近没有橡木，向东走10格找到"
  iter N+2: write_file SESSIONS.md → 新 session: move(forward:10) + collect(...)
  ...循环直到成功
```

---

## 链路逐条验证

| 链路 | 状态 | 实现位置 |
|------|------|---------|
| watchdog → ENVIRONMENT.md | ✅ | `WatchdogSupervisor` → `ResultWriter` — 执行后自动回写 |
| ENVIRONMENT.md → Agent 系统提示词（自动） | ✅ | `ContextBuilder` — 启动时自动注入 |
| Agent → SESSIONS.md | ✅ | Agent 使用 `write_file` 写入 session 定义 |
| SESSIONS.md → WatchdogSupervisor 调度 | ✅ | `scheduler.py` — 解析 SessionSpec，resolve target/skill |
| SessionRunner → TargetSessionHandle | ✅ | `session_runner.py:start()` — 封装 target 访问 |
| TargetSessionHandle.action_chunk → bridge | ✅ | `target_session_handle.py:67` → adapter → target → HTTP POST /action |
| 动作结果校验 | ✅ | `minecraft_skill_runtime.py:run_builtin_loop()` — 检查 `ok`/`result` |
| 成功/失败 → LESSONS.md | ✅ | `WatchdogSupervisor` → `ResultWriter` — 自动记录 |

---

## 关键设计决策

### 1. MinecraftSkillRuntime 继承 BuiltinSkillRuntime

对齐 v0.1.4 框架，`minecraft_skill_runtime.py` 从 `BaseSkillRuntime` 改为继承 `BuiltinSkillRuntime`，实现 `run_builtin_loop(skill_ctx, target_handle, adapter_plan) -> SkillRuntimeResult`。

旧版直接调用 `target.step()` 和 `target.observe()`；新版通过 `TargetSessionHandle.action_chunk()` 和 `.observe()` 访问 target，由 SessionRunner 管理完整生命周期（build → configure → start → loop → result）。

### 2. 模板对齐 Pydantic Schema

`TARGETS.md` 和 `SKILLS.md` 模板字段完全对齐 `TargetSpec` / `SkillSpec` 的 Pydantic schema（`extra="forbid"`）：

| 旧字段 | 新字段 | 原因 |
|--------|--------|------|
| `type: sim` | `target_class: local` + `target_kind: game` | TargetSpec schema |
| `target_endpoint` | 删除 | local target 不需要 |
| `perception` 块 | 删除 | 使用默认值 |
| `category: builtin` | `runtime_kind: builtin` | SkillSpec schema |
| `supported_targets: [...]` | `supported_target_kinds: [game]` | 按 kind 匹配，非 target ID |
| - | `runtime_contract_ref: configs/runtime/contracts/minecraft.runtime.yaml` | 必填 Path 字段 |
| - | `loop_mode: open_loop_step` | 必填 |
| - | `agent_exposure: none` | 必填 |
| - | `observation_contract` | 必填 |

### 3. 场景区分：不同 workspace = 不同配置

```bash
paos agent --workspace workspaces/minecraft    → EMBODIED.md(16种MC动作) → 游戏场景
paos agent --workspace workspaces/libero_real  → EMBODIED.md(仿真动作)   → 仿真场景
```

ContextBuilder 自动加载对应 workspace 下的文件。新增场景只需对 workspace 部署对应的 EMBODIED.md + TARGETS.md + SKILLS.md。

---

## CLI 使用方式

```bash
# 一切通过 paos agent 完成，watchdog 自动启动
paos agent --workspace workspaces/minecraft

# Agent 交互界面:
You: 采集5个橡木原木           → Agent 自动写 SESSIONS.md → watchdog 执行 → 回复结果
You: 往前走20步，看看周围有什么  → Agent 读 ENVIRONMENT.md → 决策 → 执行 → 汇报
```

**已删除的命令**（不再需要）：
- `paos minecraft say` → 由 `paos agent` 对话替代
- `paos minecraft listen` → 由 `paos agent` + HEARTBEAT.md 替代
- `paos minecraft watchdog` → `paos agent` 自动启动 WatchdogSupervisor
- `paos minecraft tp` → 删除。如需传送，Agent 可使用 `{"type": "move", "params": {"dx": x, "dy": y, "dz": z, "absolute": true}}`

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `runtime/targets/game/minecraft_target.py` | MinecraftTarget — HTTP 客户端，继承 BaseLocalTarget |
| `runtime/adapters/minecraft/minecraft_adapter.py` | Observation/Action 归一化 |
| `runtime/skills/game/minecraft_skill_runtime.py` | Episode 驱动循环，继承 BuiltinSkillRuntime |
| `runtime/watchdog/runtime_registry.py` | 注册 MinecraftSkillRuntime |
| `templates/TARGETS.md` | 含 minecraft_java_env（target_class: local, target_kind: game） |
| `templates/SKILLS.md` | 含 minecraft_navigate（runtime_kind: builtin） |
| `templates/configs/runtime/embodied/minecraft.md` | 含 `## Critic Guidance`，`_deploy_embodied_from_targets` 自动部署到 workspace 为 EMBODIED.md |
| `templates/configs/runtime/contracts/minecraft.runtime.yaml` | 运行时契约（safety/action_contract） |
| `runtime/adapters/bridges.py` | SafetyClampBridge — dict action 透传修复 |
| `.kilo/project/game/bridge_server.js` | mineflayer bridge（部署到 Windows） |
