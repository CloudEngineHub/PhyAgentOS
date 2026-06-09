# PhyAgentOS × Minecraft — Usage Guide

> Reading Path 2: **Get the system running** — Daily usage and interaction methods.
> Prerequisite: [Deployment Guide](deployment.md) completed, bridge running.
> Back to [User Manual §2.6.7](../../../../en/02-user-manual.md#267-minecraft-game-agent)

---

## 1. Terminal Control: `paos minecraft say`

Natural language controls the bot directly. LLM auto-converts instructions into Minecraft action sequences.

```bash
paos minecraft say "mine 5 oak logs and come over"
```

**Execution flow**:
```
User says "mine 5 oak logs"
  → LLM generates:
    [{"type":"chat","params":{"message":"Got it, starting collection"}},
     {"type":"collect","params":{"block_type":"oak_log","count":5}},
     {"type":"chat","params":{"message":"Collection complete"}}]
  → MinecraftSkillRuntime.run()
  → bot chats + collects + chats in-game
```

If ngrok address changes:
```bash
paos minecraft say "say hello" --url https://new-address.ngrok-free.dev
```

**Implementation**: `PhyAgentOS/cli/commands.py:959` (`minecraft_say` function).

---

## 2. In-Game Chat Control

Run the listener script in the background; type in Minecraft chat and the bot auto-responds.

```bash
python test/chat_listener.py
```

In Minecraft chat say:
```
wissingcc: paos come here
wissingcc: paos mine 5 oak logs
```

**How it works**: bridge captures chat → writes to `state.last_chats[]` → chat_listener polls `GET /state` → detects new messages → generates actions → executes.

No extra ports or ngrok tunnels needed — reuses the existing bridge HTTP API.

**Bridge-side changes** (already built into `bridge_server.js`):
```javascript
let recentChats = [];
bot.on('chat', (username, message) => {
    if (username === BOT_NAME) return;
    recentChats.push({ username, message, time: Date.now() });
});
```

---

## 3. Bot Teleporting

The bot spawns at world spawn and needs to be moved to the player.

**Auto-teleport** (bridge-side): bot auto-executes `/tp @s <player>` 2 seconds after spawn. Requires cheats enabled in LAN mode.

**Manual teleport**: `test/tp_bot.py`

```python
MY_X = -15.0    # Check your coordinates via F3
MY_Y = 63.0
MY_Z = -83.7
t.step({"type": "move", "params": {"dx": MY_X, "dy": MY_Y, "dz": MY_Z, "absolute": True}})
```

```bash
python test/tp_bot.py
```

---

## 4. Script Reference

| Script | Function | Usage |
|--------|----------|-------|
| `test/test_1.py` | Verify Target connectivity | `python test/test_1.py` — see [Deployment Guide §3.2](deployment.md#32-quick-test) |
| `test/test_2.py` | Full Pipeline demo | `python test/test_2.py` — see [Deployment Guide §7](deployment.md#7-full-pipeline-agent-task-dispatch) |
| `test/tp_bot.py` | Manual bot teleport | Edit coords first, `python test/tp_bot.py` |
| `test/chat_listener.py` | In-game chat listener | `python test/chat_listener.py` (background) |
| CLI | One-liner terminal control | `paos minecraft say "mine 5 oak logs"` |

---

## 5. Troubleshooting

| # | Issue | Cause | Fix |
|---|-------|-------|-----|
| 1 | `SSL: CERTIFICATE_VERIFY_FAILED` | Free ngrok incomplete certs | `httpx.Client(verify=False)`, add `"verify_ssl": false` in config |
| 2 | `Expecting value: line 1 column 1` | ngrok returns HTML confirmation page | Add header `ngrok-skip-browser-warning: true` |
| 3 | `Request URL is missing protocol` | Extra whitespace around bridge_url | `.strip()` in `__init__` |
| 4 | `Can't instantiate abstract class MinecraftTarget` | Base class got new abstract methods | Implement `describe/configure_session/start_session/action_chunk/execution_status/cancel` |
| 5 | `Can't instantiate abstract class MinecraftSkillRuntime` | Same as above | Implement `start/cancel/snapshot` + `runtime_kind = "builtin"` |
| 6 | Pipeline stops after 1 step | `step()` used `info.success` with `ok` semantics | Change `success` → `ok`, use only `done` to control termination |
| 7 | Bridge teleport not working | Bot at spawn, player outside render distance | Use `/tp @s <player>` command |
| 8 | `/op` command doesn't exist | LAN mode doesn't need OP | `Esc → Open to LAN → Allow Cheats: ON` |
| 9 | `JSONDecodeError: Expecting value` | LLM returns empty response | Check API key and network; confirm LLM call chain is working |

---

## 6. Code Change Reference

| File | Change | Description |
|------|--------|-------------|
| `minecraft_target.py` | `_get_http()` add `verify_ssl` + `ngrok-skip-browser-warning` header | Fix ngrok cert and confirmation page |
| | `__init__` add `bridge_url.strip()` | Prevent whitespace |
| | Add `describe/configure_session/start_session/action_chunk/execution_status/cancel` | Base class new abstract methods |
| `minecraft_skill_runtime.py` | Add `start/cancel/snapshot` + `runtime_kind` | Base class new abstract methods |
| `commands.py` | Add `paos minecraft say` command | Terminal LLM control |
| `minecraft_target.py` | step `info.success` → `info.ok` | Semantic fix |

---

> Back: [Deployment Guide](deployment.md) | [User Manual §2.6.7](../../../../en/02-user-manual.md#267-minecraft-game-agent)
