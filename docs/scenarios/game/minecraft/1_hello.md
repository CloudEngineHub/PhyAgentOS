# PhyAgentOS × Minecraft — 智能控制

> 承接 [0_start.md](0_start.md)。假设环境已通，bridge 正常运行。

---

## 一、终端控制：`paos minecraft say`

自然语言直接控制 bot。LLM 自动将指令转为 Minecraft 动作序列。

```bash
paos minecraft say "挖5个橡木然后过来"
```

**执行流程**：
```
用户说 "挖5个橡木"
  → LLM 生成:
    [{"type":"chat","params":{"message":"收到，开始采集"}},
     {"type":"collect","params":{"block_type":"oak_log","count":5}},
     {"type":"chat","params":{"message":"采集完成"}}]
  → MinecraftSkillRuntime.run()
  → bot 在游戏里聊天 + 采集 + 聊天
```

如果 ngrok 地址变了：
```bash
paos minecraft say "打个招呼" --url https://新地址.ngrok-free.dev
```

**实现位置**：`PhyAgentOS/cli/minecraft_commands.py:40`（`minecraft_say` 函数）。

---

## 二、游戏对话控制

后台运行监听命令，在 Minecraft 聊天里打字，bot 自动响应。

```bash
paos minecraft listen
```

然后在游戏里说：
```
wissingcc: paos 过来
wissingcc: paos 挖5个橡木
```

**原理**：bridge 捕获聊天 → 写入 `state.last_chats[]` → listener 轮询 `GET /state` → 发现新消息 → LLM 生成动作 → `MinecraftSkillRuntime.run()` 执行。

不需要额外端口或 ngrok 隧道——复用已有的 bridge HTTP API。

**实现位置**：`PhyAgentOS/cli/minecraft_commands.py:100`（`minecraft_listen` 函数）。

---

## 三、bot 传送

bot 在世界出生点生成，需要传送到玩家身边。

```bash
# 传送 bot 到你的坐标（在游戏里按 F3 查看 x, y, z）
paos minecraft tp -15 63 -83.7

# 或指定 bridge URL
paos minecraft tp 100 64 200 --url https://新地址.ngrok-free.dev
```

**手动传送（旧版）**：`test/tp_bot.py`

---

## 四、动作验证清单

以下指令在**当前开环模式**（LLM 一次性生成全量动作，无环境感知）下可用。需要环境感知的复杂动作见 [2_agent_loop.md](2_agent_loop.md)。

### 聊天

```bash
paos minecraft say "说你好"
paos minecraft say "打个招呼"
```

### 移动（面朝方向）

```bash
paos minecraft say "往前走5步"
paos minecraft say "后退3步"
```

### 移动（追踪实体）

```bash
paos minecraft say "来到我身边"
paos minecraft say "去找猪"
```

### 转向

```bash
paos minecraft say "向后转"           # yaw=180
paos minecraft say "右转90度"         # yaw=-90
paos minecraft say "左转90度"         # yaw=90
```

### 按键

```bash
paos minecraft say "跳一下"
paos minecraft say "潜行"
paos minecraft say "开始疾跑"
```

### 物品栏

```bash
paos minecraft say "切到第2格"
paos minecraft say "使用手中的物品"
paos minecraft say "扔掉手里的东西"
```

### 组合

```bash
paos minecraft say "说收到，然后往前走3步，说完成"
paos minecraft say "跳一下转一圈说你好"
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
| 5 | `Can't instantiate abstract class MinecraftSkillRuntime` | 同上 | 补齐 `start/cancel/snapshot` + `runtime_kind = "builtin"` |
| 6 | Pipeline 只跑 1 步就停 | `step()` 中 `info.success` 用了 `ok` 语义 | 改 `success` → `ok`，仅 `done` 控制终止 |
| 7 | bridge 传送不生效 | bot 在出生点，玩家超出 render distance | 改用 `/tp @s <玩家>` 命令 |
| 8 | `/op` 命令不存在 | LAN 模式不需要 OP | `Esc → 对局域网开放 → 允许作弊: 开` |
| 9 | `JSONDecodeError: Expecting value` | LLM 返回空响应 | 检查 API key 和网络，确认 LLM 调用正常 |
| 10 | `Cannot read properties of undefined (reading 'chestLocations')` | mineflayer-collectblock 插件未初始化 | bridge 中 `bot.on('spawn')` 内手动初始化 `chestLocations`/`chestsToOpen`/`tempChests` |
| 11 | LLM 生成 `turn`/`speak` 等不存在动作 | 系统 Prompt 未约束动作空间 | Prompt 列出 16 种有效动作名，强调"不能编造，其他都会失败" |
| 12 | `paos minecraft listen` 无响应 | `MinecraftTarget.observe()` 未透传 `last_chats` | `observe()` 返回值中加入 `"last_chats"` 字段 |
| 13 | `look yaw=180` bot 不转向 | bridge `bot.look()` 接受弧度，Python 传角度 | 移除 Python 端的角度→弧度转换（当前不做转换，待 bridge 端统一约定） |
| 14 | `dig`/`place` 坐标不准，bot 找不到方块 | LLM 不知道 bot 周围的地形 | 用 `collect` 代替 `dig`；精确方块操作需要 Agent 闭环（见 todo_list.md §2） |
| 15 | `look yaw=360` bot 不转 | bridge `bot.look()` 期望弧度，LLM 传角度 | bridge 端加 `* Math.PI / 180` 转换 |

---

## 六、代码变更速查

| 文件 | 变更 | 说明 |
|------|------|------|
| `minecraft_target.py` | `_get_http()` 加 `verify_ssl` + `ngrok-skip-browser-warning` header | 解决 ngrok 证书和确认页 |
| | `__init__` 中 `bridge_url.strip()` | 防空格 |
| | 新增 `describe/configure_session/start_session/action_chunk/execution_status/cancel` | 基类新抽象方法 |
| | `step()` 中 `info.success` → `info.ok` | 语义修正 |
| | `observe()` 加入 `last_chats`/`players`/`inventory` 透传 | 支持聊天监听+状态查询 |
| `minecraft_skill_runtime.py` | 新增 `start/cancel/snapshot` + `runtime_kind` | 基类新抽象方法 |
| | 保留 `_find_nearest_entity` + `_build_move_to_entity` + `_wait_for_arrival` | entity 追踪解析 + 移动到达检测 |
| `commands.py` | 新增 `paos minecraft say` 命令（L1008） | 终端 LLM 控制 |
| | 新增 `paos minecraft listen` 命令（L1077） | 游戏聊天监听 |
| `bridge_server.js` | 加入 `chestLocations` 初始化 + collect 错误捕获 | 修复 mineflayer-collectblock |
| | 移除 prismarine-viewer | canvas 无法编译，见 todo_list.md |

---

## 七、脚本速查

| 脚本 | 功能 | 用法 |
|------|------|------|
| `test/test_1.py` | 验证 Target 连通 | `python test/test_1.py` — 见 0_start §3.2 |
| `test/test_2.py` | 完整 Pipeline 演示 | `python test/test_2.py` — 见 0_start §7 |
| `test/tp_bot.py` | 传送 bot | 改坐标后 `python test/tp_bot.py` |
| `test/chat_listener.py` | 游戏对话监听（旧版，已废弃） | 改用 `paos minecraft listen` |
| CLI `say` | 终端一键指令 | `paos minecraft say "挖5个橡木"` |
| CLI `listen` | 游戏聊天监听 | `paos minecraft listen` |
| CLI `tp` | 传送 bot | `paos minecraft tp -15 63 -83.7` |
| 计划 | 未来功能 | 见 `.kilo/project/game/todo_list.md` |
