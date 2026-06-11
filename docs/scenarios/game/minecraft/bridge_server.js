/**
 * mineflayer bridge — HTTP API for Minecraft bot.
 *
 * Usage:
 *   node bridge_server.js
 *
 * Env vars: MC_HOST, MC_PORT, BOT_NAME, MC_VERSION, API_PORT
 *
 * Endpoints:
 *   GET  /health        → bot status
 *   GET  /state         → bot position, nearby blocks, entities, chat
 *   POST /action        → execute one action
 *
 * PhyAgentOS 集成: 此 bridge 运行在 Windows 端，通过 ngrok 暴露公网。
 * Linux 端的 MinecraftTarget 通过 HTTP 连接此 bridge；
 * paos agent --workspace workspaces/minecraft 自动管理 watchdog + skill runtime。
 */

const express = require('express');
const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');
const app = express();
app.use(express.json());

const HOST = process.env.MC_HOST || 'localhost';
const PORT = parseInt(process.env.MC_PORT || '25565', 10);
const BOT_NAME = process.env.BOT_NAME || 'paos';
const API_PORT = parseInt(process.env.BRIDGE_PORT || '3001', 10);
const STATE_RADIUS = parseInt(process.env.STATE_RADIUS || '5', 10);

let bot = null, botSpawned = false, spawnTime = 0;
let recentChats = [];

// ── Bot ─────────────────────────────────────────────────────────
const MC_VERSION = process.env.MC_VERSION || '1.20.4';

function createBot() {
    bot = mineflayer.createBot({ host: HOST, port: PORT, username: BOT_NAME, version: MC_VERSION });
    bot.loadPlugin(pathfinder);

    bot.on('spawn', () => {
        botSpawned = true; spawnTime = Date.now();
        console.log(`[bridge] Bot spawned: ${BOT_NAME} (MC ${MC_VERSION})`);
    });

    bot.on('death', () => { botSpawned = false; setTimeout(() => { if (bot) bot.respawn(); }, 3000); });
    bot.on('kicked', (r) => { console.log(`[bridge] Kicked: ${r}`); botSpawned = false; });
    bot.on('error', (e) => console.error(`[bridge] Error: ${e.message}`));
    bot.on('end', (r) => { console.log(`[bridge] Disconnected: ${r}`); botSpawned = false; });

    bot.on('chat', (username, message) => {
        if (username === BOT_NAME) return;
        recentChats.push({ username, message, time: Date.now() });
    });
}

// ── State ───────────────────────────────────────────────────────
function getState() {
    if (!bot || !bot.entity) return { bot: null, error: 'not spawned' };

    const pos = bot.entity.position;
    const nearbyBlocks = [];
    const nearbyEntities = [];

    // nearby blocks (radius = STATE_RADIUS)
    const r = STATE_RADIUS;
    for (let dx = -r; dx <= r; dx++) {
        for (let dy = -r; dy <= r; dy++) {
            for (let dz = -r; dz <= r; dz++) {
                const b = bot.blockAt(pos.offset(dx, dy, dz));
                if (b && b.name !== 'air') {
                    nearbyBlocks.push({
                        name: b.name,
                        position: { x: pos.x + dx, y: pos.y + dy, z: pos.z + dz }
                    });
                }
            }
        }
    }

    // nearby entities
    for (const id in bot.entities) {
        const e = bot.entities[id];
        if (e === bot.entity) continue;
        const dist = e.position.distanceTo(pos);
        if (dist <= STATE_RADIUS * 2) {
            nearbyEntities.push({
                type: e.name || e.type || 'unknown',
                position: { x: e.position.x, y: e.position.y, z: e.position.z },
                health: e.health,
            });
        }
    }

    // players
    const players = Object.values(bot.players).map(p => ({
        username: p.username,
        position: {
            x: Math.round(p.entity.position.x * 10) / 10,
            y: Math.round(p.entity.position.y * 10) / 10,
            z: Math.round(p.entity.position.z * 10) / 10,
        },
    }));

    // inventory hotbar
    const hotbarSlots = bot.inventory.slots.slice(36, 45);
    const hotbar = hotbarSlots.map((item, i) => item ? {
        slot: i,
        name: item.name,
        count: item.count,
    } : null).filter(Boolean);

    return {
        bot: {
            position: { x: pos.x, y: pos.y, z: pos.z },
            rotation: { yaw: bot.entity.yaw, pitch: bot.entity.pitch },
            on_ground: bot.entity.onGround,
            health: bot.health,
        },
        health: bot.health,
        hunger: bot.food,
        dimension: bot.game.dimension,
        world: { time: bot.time.timeOfDay, raining: bot.isRaining },
        player_list: Object.keys(bot.players),
        nearby_blocks: nearbyBlocks,
        nearby_entities: nearbyEntities,
        players: players,
        inventory: { hotbar },
        last_chats: recentChats,
    };
}

// ── Actions ─────────────────────────────────────────────────────
function executeAction(action) {
    return new Promise((resolve) => {
        if (!bot || !bot.entity) return resolve({ ok: false, result: 'bot not spawned' });
        const t = action.type, p = action.params || {};
        try {
            switch (t) {
                case 'move': {
                    const pos = bot.entity.position;
                    let gx, gy, gz;
                    if (p.forward != null) {
                        const dist = parseFloat(p.forward);
                        gx = pos.x - Math.sin(bot.entity.yaw) * dist;
                        gy = pos.y;
                        gz = pos.z + Math.cos(bot.entity.yaw) * dist;
                    } else {
                        gx = p.absolute ? parseFloat(p.dx) : pos.x + parseFloat(p.dx || 0);
                        gy = p.absolute ? parseFloat(p.dy) : pos.y + parseFloat(p.dy || 0);
                        gz = p.absolute ? parseFloat(p.dz) : pos.z + parseFloat(p.dz || 0);
                    }
                    bot.pathfinder.setMovements(new Movements(bot));
                    bot.pathfinder.setGoal(new goals.GoalBlock(Math.floor(gx), Math.floor(gy), Math.floor(gz)));
                    resolve({ ok: true, result: `moving to (${gx.toFixed(1)}, ${gy.toFixed(1)}, ${gz.toFixed(1)})` }); break;
                }
                case 'look': {
                    const yaw = p.yaw != null ? parseFloat(p.yaw) * Math.PI / 180 : bot.entity.yaw;
                    const pitch = p.pitch != null ? parseFloat(p.pitch) * Math.PI / 180 : bot.entity.pitch;
                    bot.look(yaw, pitch, true);
                    resolve({ ok: true, result: 'ok' });
                    break;
                }
                case 'jump': bot.setControlState('jump', true); setTimeout(() => bot.setControlState('jump', false), parseInt(p.duration_ms || 500)); resolve({ ok: true, result: 'ok' }); break;
                case 'sneak': bot.setControlState('sneak', p.start !== false); resolve({ ok: true, result: 'ok' }); break;
                case 'sprint': bot.setControlState('sprint', p.start !== false); resolve({ ok: true, result: 'ok' }); break;
                case 'dig': {
                    const b = bot.blockAt({ x: parseInt(p.x), y: parseInt(p.y), z: parseInt(p.z) });
                    if (!b || b.name === 'air') return resolve({ ok: false, result: 'no block' });
                    bot.dig(b, (e) => resolve(e ? { ok: false, result: e.message } : { ok: true, result: `dug ${b.name}` })); break;
                }
                case 'place': {
                    const rb = bot.blockAt({ x: parseInt(p.x), y: parseInt(p.y), z: parseInt(p.z) });
                    if (!rb) return resolve({ ok: false, result: 'no reference block' });
                    const fv = [{ x: 0, y: -1, z: 0 }, { x: 0, y: 1, z: 0 }, { x: 0, y: 0, z: -1 }, { x: 0, y: 0, z: 1 }, { x: -1, y: 0, z: 0 }, { x: 1, y: 0, z: 0 }];
                    bot.placeBlock(rb, fv[parseInt(p.face) || 1], (e) => resolve(e ? { ok: false, result: e.message } : { ok: true, result: 'placed' })); break;
                }
                case 'attack': {
                    let target = p.entity_id ? bot.entities[p.entity_id] : null;
                    if (!target && p.target_type) for (const id in bot.entities) if (bot.entities[id] !== bot.entity && bot.entities[id].name === p.target_type) { target = bot.entities[id]; break; }
                    if (!target) return resolve({ ok: false, result: 'no target' });
                    bot.attack(target); resolve({ ok: true, result: 'attacked' }); break;
                }
                case 'interact': { const e = bot.entities[p.entity_id]; if (!e) return resolve({ ok: false, result: 'entity not found' }); bot.activateEntity(e); resolve({ ok: true, result: 'ok' }); break; }
                case 'use': bot.activateItem(); resolve({ ok: true, result: 'ok' }); break;
                case 'select_slot': { const s = Math.max(0, Math.min(8, parseInt(p.slot || 0))); bot.setQuickBarSlot(s); resolve({ ok: true, result: `slot ${s}` }); break; }
                case 'drop': { const it = p.slot != null ? bot.inventory.slots[parseInt(p.slot)] : bot.inventory.slots[bot.quickBarSlot]; if (!it) return resolve({ ok: false, result: 'nothing to drop' }); bot.tossStack(it); resolve({ ok: true, result: `dropped ${it.name}` }); break; }
                case 'chat': { const m = String(p.message || ''); if (!m) return resolve({ ok: false, result: 'empty' }); bot.chat(m); resolve({ ok: true, result: `sent: ${m}` }); break; }
                case 'collect': {
                    (async () => {
                        try {
                            const blockType = p.block_type;
                            const count = parseInt(p.count || 1);

                            // Validate the block name exists in minecraft-data
                            const mcData = require('minecraft-data')(bot.version);
                            const block = mcData.blocksByName[blockType];
                            if (!block) return resolve({ ok: false, result: `unknown block: ${blockType}` });

                            let collected = 0;
                            for (let i = 0; i < count; i++) {
                                // Use name-based matching (more reliable than numeric ID)
                                const target = bot.findBlock({
                                    matching: (b) => b.name === blockType,
                                    maxDistance: 64,
                                    count: 1,
                                });
                                if (!target) {
                                    if (collected === 0) return resolve({ ok: false, result: `no ${blockType} found within 64 blocks` });
                                    return resolve({ ok: true, result: `collected ${collected}x ${blockType} (no more found)` });
                                }
                                console.log(`[bridge] collect ${blockType} ${i + 1}/${count}: at (${target.position.x.toFixed(1)}, ${target.position.y.toFixed(1)}, ${target.position.z.toFixed(1)})`);

                                try {
                                    bot.pathfinder.setMovements(new Movements(bot));
                                    await bot.pathfinder.goto(new goals.GoalGetToBlock(target.position.x, target.position.y, target.position.z));
                                } catch (pathErr) {
                                    console.log(`[bridge] pathfinder failed: ${pathErr.message}`);
                                    continue;
                                }

                                try {
                                    await bot.dig(target);
                                    collected++;
                                } catch (digErr) {
                                    console.log(`[bridge] dig failed: ${digErr.message}`);
                                    continue;
                                }
                            }
                            resolve({ ok: true, result: `collected ${collected}x ${blockType}` });
                        } catch (e) {
                            resolve({ ok: false, result: e.message });
                        }
                    })();
                    break;
                }
                case 'equip': { const item = bot.inventory.items().find(i => i.name === p.item); if (!item) return resolve({ ok: false, result: `no ${p.item}` }); bot.equip(item, p.destination || 'hand', (e) => resolve(e ? { ok: false, result: e.message } : { ok: true, result: 'ok' })); break; }
                case 'craft': {
                    const mcData = require('minecraft-data')(bot.version);
                    const id = mcData.itemsByName[p.recipe_id]; if (!id) return resolve({ ok: false, result: `unknown: ${p.recipe_id}` });
                    const recipes = bot.recipesFor(id.id, null, 1, null); if (!recipes.length) return resolve({ ok: false, result: 'no recipe' });
                    bot.craft(recipes[0], parseInt(p.count || 1), null, (e) => resolve(e ? { ok: false, result: e.message } : { ok: true, result: `crafted ${p.count}x ${p.recipe_id}` })); break;
                }
                default: resolve({ ok: false, result: `unknown type: ${t}` });
            }
        } catch (e) { resolve({ ok: false, result: e.message }); }
    });
}

// ── HTTP ────────────────────────────────────────────────────────
app.get('/health', (_req, res) => res.json({ ok: true, bot_spawned: botSpawned, uptime_seconds: botSpawned ? Math.floor((Date.now() - spawnTime) / 1000) : 0 }));
app.get('/state', (_req, res) => res.json(getState()));
app.post('/action', async (req, res) => {
    if (!req.body?.type) return res.status(400).json({ ok: false, error: 'missing type' });
    res.json(await executeAction(req.body));
});

// ── Start ───────────────────────────────────────────────────────
console.log(`[bridge] Starting for Minecraft ${MC_VERSION}`);
createBot();
app.listen(API_PORT, '0.0.0.0', () => console.log(`[bridge] HTTP API listening on port ${API_PORT}`));
