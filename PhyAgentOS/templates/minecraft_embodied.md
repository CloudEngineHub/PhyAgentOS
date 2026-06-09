# EMBODIED.md — Minecraft Java Bot

## Identity

- **Name**: paos (minecraft_java_env)
- **Type**: game target (Minecraft Java Edition bot)
- **Driver/Profile**: mineflayer bridge via HTTP (ngrok tunnel)

## Supported Actions

| Action | Parameters | Description |
|--------|-----------|-------------|
| `move` | `dx, dy, dz, absolute` | Move bot by delta (absolute=false) or to world coords (absolute=true). Also supports `target` for entity tracking. |
| `look` | `yaw, pitch` | Set bot head rotation (degrees). 0=south, 90=west, 180=north, -90=east. |
| `jump` | — | Make bot jump |
| `sneak` | `sneaking` (bool) | Toggle sneaking |
| `sprint` | — | Toggle sprinting |
| `attack` | — | Attack the entity the bot is looking at |
| `interact` | `x, y, z` | Right-click a block at coordinates |
| `place` | `x, y, z, face` | Place a block against the specified face |
| `dig` | `x, y, z` | Break a block at coordinates |
| `use` | `x, y, z` | Use/activate a block (e.g. chest, crafting table) |
| `select_slot` | `slot` (0-8) | Switch hotbar to the given slot index |
| `drop` | `slot` (optional) | Drop item from hotbar |
| `chat` | `message` | Send a chat message |
| `collect` | `block_type, count` | Locate and collect blocks of the given type |
| `equip` | `type, dest` | Equip an item |
| `craft` | `item, count` | Craft items |

## Physical Constraints

- **Pathfinder**: mineflayer `pathfinder` for `move` actions; can fail on complex terrain or unreachable coordinates.
- **Render distance**: limited by Minecraft server settings (typically 8-12 chunks).
- **Action latency**: each action has a step delay (~0.1s default); move actions may take several seconds to complete.
- **Block reach**: ~4.5 blocks from bot position for dig/place/interact.

## Connection

- **Transport**: HTTP REST API via ngrok tunnel to Windows bridge server
- **Host**: bridge_url (e.g. `https://xxxx.ngrok-free.app`)
- **Health Check**: `GET /health` (returns `bot_spawned` flag)
- **State**: `GET /state` (returns bot position, health, nearby entities, etc.)
- **Action**: `POST /action` (body: `{"type": "...", "params": {...}}`)

## Observer

prismarine-viewer on port 3007 provides browser-based 3D first-person view (independent side-channel, not connected to the Python pipeline).
