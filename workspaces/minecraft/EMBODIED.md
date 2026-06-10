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

## Critic Guidance

- This is a Minecraft game bot, not a physical robot. No physical safety constraints apply.
- The bot operates in a virtual 3D block world via mineflayer API.
- `move` action accepts absolute coordinates (dx, dy, dz, absolute=true) or relative moves (forward=N). Also supports target=entity for tracking. Mineflayer pathfinder handles obstacle avoidance automatically.
- `look` action accepts yaw/pitch in degrees. 0=south, 90=west, 180=north, -90=east. Verify angles are within valid ranges.
- `dig` action requires absolute coordinates (x, y, z). Reject dig if coordinates are unknown. Prefer collect over dig for gathering blocks.
- `collect` action requires block_type and count. The mineflayer-collectblock plugin handles pathfinding automatically.
- `place` action requires x, y, z and face (0=down, 1=up, 2=north, 3=south, 4=west, 5=east).
- `craft` action requires recipe_id and count. Standard Minecraft recipes only.
- `select_slot` action requires slot 0-8. Reject if slot is out of range.
- `chat` action: any non-empty message is valid.
- Block reach is approximately 4.5 blocks. Reject dig/place actions targeting blocks beyond this range if the bot's current position is known from ENVIRONMENT.md.
- Empty parameters or unknown keys are NOT automatically invalid — some actions work with no params (use {}) or accept optional params that the mineflayer bridge may handle gracefully.
- 不需要 scene_asset_path, objects, robot_start, arm_mass_scale 等物理机器人参数。如果参数中出现这些字段应忽略，不应因此拒绝动作。

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
