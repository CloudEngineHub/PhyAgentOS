# PhyAgentOS × Minecraft — 使用指南

> 阅读路径 2：**快速跑通系统** — 日常使用与交互方式。
> 前提：已完成 [部署指南](deployment.md)，bridge 正常运行。
> 返回 [用户手册 §2.6.7](../../../../zh/02-user-manual.md#267-minecraft-game-agent)

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

**实现位置**：`PhyAgentOS/cli/commands.py:959`（`minecraft_say` 函数）。

---

## 二、游戏对话控制

后台运行监听脚本，在 Minecraft 聊天里打字，bot 自动响应。

```bash
python test/chat_listener.py
```

然后在游戏里说：
```
wissingcc: paos 过来
wissingcc: paos 挖5个橡木
```

**原理**：bridge 捕获聊天 → 写入 `state.last_chats[]` → chat_listener 轮询 `GET /state` → 发现新消息 → 生成动作 → 执行。

不需要额外端口或 ngrok 隧道——复用已有的 bridge HTTP API。

**bridge 侧改动**（已内置到 `bridge_server.js`）：
```javascript
let recentChats = [];
bot.on('chat', (username, message) => {
    if (username === BOT_NAME) return;
    recentChats.push({ username, message, time: Date.now() });
});
```

---

## 三、bot 传送

bot 在世界出生点生成，需要传送到玩家身边。

**自动传送**（bridge 侧）：bot 生成 2 秒后自动 `/tp @s <玩家名>`。LAN 模式开启作弊后可用。

**手动传送**：`test/tp_bot.py`

```python
MY_X = -15.0    # F3 查看你的坐标
MY_Y = 63.0
MY_Z = -83.7
t.step({"type": "move", "params": {"dx": MY_X, "dy": MY_Y, "dz": MY_Z, "absolute": True}})
```

```bash
python test/tp_bot.py
```

---

## 四、脚本速查

| 脚本 | 功能 | 用法 |
|------|------|------|
| `test/test_1.py` | 验证 Target 连通性 | `python test/test_1.py` — 见 [部署指南 §3.2](deployment.md#32-快速测试) |
| `test/test_2.py` | 完整 Pipeline 演示 | `python test/test_2.py` — 见 [部署指南 §7](deployment.md#七完整-pipelineagent-下发任务) |
| `test/tp_bot.py` | 手动传送 bot | 改坐标后 `python test/tp_bot.py` |
| `test/chat_listener.py` | 游戏对话监听 | `python test/chat_listener.py`（后台） |
| CLI | 终端一键指令 | `paos minecraft say "挖5个橡木"` |

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

---

## 六、代码变更速查

| 文件 | 变更 | 说明 |
|------|------|------|
| `minecraft_target.py` | `_get_http()` 加 `verify_ssl` + `ngrok-skip-browser-warning` header | 解决 ngrok 证书和确认页 |
| | `__init__` 中 `bridge_url.strip()` | 防空格 |
| | 新增 `describe/configure_session/start_session/action_chunk/execution_status/cancel` | 基类新抽象方法 |
| `minecraft_skill_runtime.py` | 新增 `start/cancel/snapshot` + `runtime_kind` | 基类新抽象方法 |
| `commands.py` | 新增 `paos minecraft say` 命令 | 终端 LLM 控制 |
| `minecraft_target.py` | step 中 `info.success` → `info.ok` | 语义修正 |

---

> 返回：[部署指南](deployment.md) | [用户手册 §2.6.7](../../../../zh/02-user-manual.md#267-minecraft-game-agent)
