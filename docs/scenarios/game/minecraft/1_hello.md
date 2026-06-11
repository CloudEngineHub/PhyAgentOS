# PhyAgentOS × Minecraft — 智能控制

> 承接 [0_start.md](0_start.md)。假设环境已通，bridge 正常运行。

---

## 一、启动 Agent

Minecraft 交互全部通过标准 `paos agent` 完成，不再有独立的 `minecraft` 子命令。

```bash
paos agent --workspace workspaces/minecraft
```

**发生了什么**：
1. `paos agent` 自动检测 runtime 配置，启动 `RuntimeWorkspaceManager`
2. RuntimeWorkspaceManager 将 `TARGETS.md`、`SKILLS.md` 复制到 workspace；检测到 `minecraft_java_env` 目标，自动将 `configs/runtime/embodied/minecraft.md` 部署为 `EMBODIED.md`
3. 自动启动 `WatchdogSupervisor` —— 后台 daemon 线程轮询 `SESSIONS.md`，调度执行 session
4. Agent 推理循环启动 —— `ContextBuilder` 自动注入 `EMBODIED.md`（16 种动作）、`ENVIRONMENT.md`（目标快照）、`LESSONS.md`（历史经验）、`TARGETS.md`、`SKILLS.md`、`RUNTIME.md`

**首次使用注意**：`TARGETS.md` 中 `bridge_url` 默认为空，需先填入 ngrok URL 再下达任务。`connection_state` 在 `bridge_url` 为空时显示 `unconfigured`。

---

## 二、对话式控制

在 Agent 交互界面中，直接用自然语言下达任务：

```
You: 采集5个橡木原木

Agent:
  1. 读 ENVIRONMENT.md → 获取 bot 当前位置和周围方块
  2. LLM 推理 → 生成 SessionSpec → 写入 SESSIONS.md
  3. WatchdogSupervisor 轮询到 pending session:
     - resolve MinecraftTarget + MinecraftSkillRuntime
     - SessionRunner 执行: build → observe → action_chunk → 循环
     - 写 LESSONS.md（经验记录）
  4. 读 ENVIRONMENT.md 验证结果
  5. 回复用户
```

**对比旧版（已删除）**：
- 旧版 `paos minecraft say "挖5个橡木"` → 单次 LLM 盲生成全量动作 → 直接执行，无环境感知
- 新版 `paos agent` → 多轮观察-推理-交互闭环，watchdog 自动执行，失败自动反思

---

## 三、动作空间（16 种）

所有动作已定义在 `EMBODIED.md`（由 `templates/minecraft_embodied.md` 部署到 workspace）。

### 移动与视角

```python
# 面朝方向前进（相对）
t.step({"type": "move", "params": {"forward": 5}})    # 前进5步
t.step({"type": "move", "params": {"forward": -3}})   # 后退3步

# 追踪实体（相对）
t.step({"type": "move", "params": {"target": "player"}})
t.step({"type": "move", "params": {"target": "pig"}})

# 路径规划到绝对坐标
t.step({"type": "move", "params": {"dx": 100, "dy": 64, "dz": 200, "absolute": True}})

# 转向（角度制）
t.step({"type": "look", "params": {"yaw": 90.0, "pitch": 0.0}})
```

### 按键控制

```python
t.step({"type": "jump",     "params": {"duration_ms": 500}})
t.step({"type": "sneak",    "params": {"start": True}})
t.step({"type": "sprint",   "params": {"start": True}})
```

### 方块操作

```python
t.step({"type": "dig",   "params": {"x": 100, "y": 63, "z": 200}})
t.step({"type": "place", "params": {"x": 100, "y": 63, "z": 200, "face": 1}})
```

### 实体交互

```python
t.step({"type": "attack",   "params": {"target_type": "pig"}})
t.step({"type": "interact", "params": {"entity_id": "..."}})
```

### 物品操作

```python
t.step({"type": "use",         "params": {}})
t.step({"type": "select_slot", "params": {"slot": 0}})
t.step({"type": "drop",        "params": {}})
```

### 聊天与命令

```python
t.step({"type": "chat", "params": {"message": "hello"}})
```

### 高级动作

```python
t.step({"type": "collect", "params": {"block_type": "oak_log", "count": 10}})
t.step({"type": "craft",   "params": {"recipe_id": "crafting_table", "count": 1}})
t.step({"type": "equip",   "params": {"item": "stone_pickaxe", "destination": "hand"}})
```

---

## 四、动作验证清单

以下指令在 Agent 闭环模式下可用（agent 自动将自然语言转为 SessionSpec，watchdog 执行）。

### 聊天

```
You: 说你好
You: 打个招呼
```

### 移动（面朝方向）

```
You: 往前走5步
You: 后退3步
```

### 移动（追踪实体）

```
You: 来到我身边
You: 去找猪
```

### 转向

```
You: 向后转
You: 右转90度
You: 左转90度
```

### 按键

```
You: 跳一下
You: 潜行
You: 开始疾跑
```

### 物品栏

```
You: 切到第2格
You: 使用手中的物品
You: 扔掉手里的东西
```

### 组合任务

```
You: 采集5个橡木原木
You: 往前走到树那里，砍3棵树，然后回来
```

> 复杂任务（采集、合成、建造、环境感知）需要 Agent 闭环——见 [2_agent_loop.md](2_agent_loop.md)。

---

## 五、踩坑记录

| # | 问题 | 原因 | 修复 |
|---|------|------|------|
| 1 | `SSL: CERTIFICATE_VERIFY_FAILED` | ngrok 免费版证书不完整 | `httpx.Client(verify=False)`，config 加 `"verify_ssl": false` |
| 2 | `Expecting value: line 1 column 1` | ngrok 返回 HTML 确认页 | 加 header `ngrok-skip-browser-warning: true` |
| 3 | `Request URL is missing protocol` | bridge_url 前后有空格 | `__init__` 中 `.strip()` |
| 4 | `Can't instantiate abstract class MinecraftTarget` | 基类新增抽象方法 | 补齐 `describe/configure_session/start_session/action_chunk/execution_status/cancel` |
| 5 | `Can't instantiate abstract class MinecraftSkillRuntime` | 同上 | 补齐 `start/cancel/snapshot` + 继承 `BuiltinSkillRuntime` |
| 6 | Pipeline 只跑 1 步就停 | `step()` 中 `info.success` 用了 `ok` 语义 | 改 `success` → `ok`，仅 `done` 控制终止 |
| 7 | bridge 传送不生效 | bot 在出生点，玩家超出 render distance | 改用 `/tp @s <玩家>` 命令 |
| 8 | `/op` 命令不存在 | LAN 模式不需要 OP | `Esc → 对局域网开放 → 允许作弊: 开` |
| 9 | `JSONDecodeError: Expecting value` | LLM 返回空响应 | 检查 API key 和网络，确认 LLM 调用正常 |
| 10 | `Cannot read properties of undefined (reading 'chestLocations')` | mineflayer-collectblock 插件未初始化 | bridge 中 `bot.on('spawn')` 内手动初始化 `chestLocations`/`chestsToOpen`/`tempChests` |
| 11 | LLM 生成不存在动作 | 系统 Prompt 未约束动作空间 | EMBODIED.md 列出 16 种有效动作，Critic 校验 |
| 12 | chat 监听无响应 | `MinecraftTarget.observe()` 未透传 `last_chats` | `observe()` 返回值中加入 `"last_chats"` 字段 |
| 13 | `look` bot 不转向 | bridge `bot.look()` 接受弧度，Python 传角度 | bridge 端加 `* Math.PI / 180` 转换 |
| 14 | `dig`/`place` 坐标不准 | LLM 不知道 bot 周围的地形 | 用 `collect` 代替 `dig`；精确方块操作需要 Agent 读取 ENVIRONMENT.md |
| 15 | `runtime_contract_ref` 缺失 | `TargetSpec` schema 中 `runtime_contract_ref` 是必填 `Path` | 创建 `configs/runtime/contracts/minecraft.runtime.yaml` 占位文件 |
| 16 | Pydantic `extra="forbid"` 拒绝模板字段 | `type: sim`/`category: builtin` 等不是 schema 合法字段 | 模板与 schema 完全对齐（target_class/target_kind/runtime_kind 等） |
| 17 | `RUNTIME_PREFLIGHT_FAILED: TARGET_ACTION_CONTRACT_INVALID` | `minecraft.runtime.yaml` 中 `require_target_side_validation: false`，Pydantic `Literal[True]` 只接受 `true` | 改为 `true` |
| 18 | `perception.enabled must be true` 拒绝 session | SKILLS.md 中 `environment_outputs: [player_position, nearby_blocks]` 触发 perception 前置检查，但 Minecraft 不需要 perception | 改为 `environment_outputs: []` |
| 19 | `SafetyClampBridge` 报 `float() argument must be a string or real number, not 'dict'` | `SafetyClampBridge.apply()` 对所有 action 强制 `np.asarray(..., dtype=np.float32)`，Minecraft 的 dict 格式 action 无法转换 | SafetyClampBridge 检测 list 中全为 dict 时直接透传，跳过 numpy 转换 |
| 20 | Agent 用 `edit_file` 写 SESSIONS.md 导致 YAML 格式崩溃 | `edit_file` 做字符串替换，结构化 YAML 缩进全丢 | AGENTS.md 明确要求用 `write_file` 整体重写 SESSIONS.md |
| 21 | Agent 写 `action: move` 但 skill runtime 只认 `type: move` | RUNTIME.md 模板无示例，Agent 不知道 perception_queries 的字段名 | RUNTIME.md 新增格式示例：`{type: move, params: {forward: 5}}` |

---

## 六、脚本速查

| 脚本 | 功能 | 用法 |
|------|------|------|
| `test/test_1.py` | 验证 Target 连通 | `python test/test_1.py` — 见 0_start §3.2 |
| `test/test_2.py` | 完整 Pipeline 演示 | `python test/test_2.py` — 见 0_start §7 |
| `test/tp_bot.py` | 传送 bot | 改坐标后 `python test/tp_bot.py` |
| CLI `agent` | 标准 Agent 交互 | `paos agent --workspace workspaces/minecraft` |
| 计划 | 未来功能 | 见 `.kilo/project/game/todo_list.md` |
