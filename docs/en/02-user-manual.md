# PhyAgentOS User Manual

> An operations manual for users, integrators, and demo operators. Covers single-machine mode, Fleet multi-robot mode, scenario configuration, and troubleshooting.

---

## Table of Contents

- [2.1 About This Manual](#21-about-this-manual)
- [2.2 How the System Works](#22-how-the-system-works)
- [2.3 Installation & Environment Setup](#23-installation--environment-setup)
- [2.4 5-Minute Quick Start](#24-5-minute-quick-start)
- [2.5 Configuration Details](#25-configuration-details)
- [2.6 Scenario Usage Guide](#26-scenario-usage-guide)
  - [2.6.1 Simulation](#261-simulation)
  - [2.6.2 Real Robot Arm (Franka Research 3)](#262-real-robot-arm-franka-research-3)
  - [2.6.3 Mobile Robot (Go2)](#263-mobile-robot-go2)
  - [2.6.4 Remote Chassis (XLeRobot)](#264-remote-chassis-xlerobot)
  - [2.6.5 ReKep Real-Robot Plugin](#265-rekep-real-robot-plugin)
  - [2.6.6 Fleet Multi-Robot Coordination](#266-fleet-multi-robot-coordination)
  - [2.6.7 Minecraft Game Agent](#267-minecraft-game-agent)
- [2.7 Runtime File Reference](#27-runtime-file-reference)
- [2.8 Common Interaction Examples](#28-common-interaction-examples)
- [2.9 Troubleshooting](#29-troubleshooting)

---

## 2.1 About This Manual

### Who This Is For

- First-time users wanting to get PhyAgentOS running
- Integrators needing command-line or gateway-based Agent interaction
- Demo operators starting simulation, Go2, remote chassis, or real-robot plugins
- Debuggers needing to understand runtime workspace file changes

### Who This Is NOT For

If you need secondary development, driver authoring, plugin development, or internal architecture research, read [Part 3: API Developer Manual](../03-developer-manual.md).

---

## 2.2 How the System Works

### 2.2.1 Dual-Track Structure

PhyAgentOS is an explicitly decoupled dual-track runtime architecture:

- **Track A (Agent / Brain)**: Handles user input understanding, action planning, tool invocation, and Critic validation. Started via `paos agent` or `paos gateway`.
- **Track B (Runtime / Execution Layer)**: Handles instruction reading, hardware driving, action execution, and state writeback. Started via `python -m PhyAgentOS.runtime.watchdog`.

Shared state between the two is expressed through Markdown files in the workspace, not through cross-layer Python function calls.

### 2.2.2 Single Mode vs Fleet Mode

| Mode | Workspace | Use Case |
|------|-----------|----------|
| **Single** | `~/.PhyAgentOS/workspace` | Single robot or simulation quick validation |
| **Fleet** | Shared + per-robot workspaces | Heterogeneous multi-robot coordination |

### 2.2.3 A Typical Run Cycle

1. Run `paos onboard` to initialize config and workspace
2. Start Watchdog, which installs `EMBODIED.md` (robot capability declaration)
3. Start `paos agent` or `paos gateway`
4. User inputs a natural language task
5. Agent reads workspace files like `ENVIRONMENT.md` for planning
6. Critic validates actions against `EMBODIED.md` for safety and feasibility
7. Validated actions are written to `ACTION.md` or `SESSIONS.md`
8. Watchdog reads, parses, and executes actions via driver
9. Watchdog writes back latest state to `ENVIRONMENT.md`

---

## 2.3 Installation & Environment Setup

### Prerequisites

- Python 3.11 or higher
- Git
- Accessible LLM provider API or compatible service
- Optional for simulation: `pybullet`, Isaac Sim
- Optional for bridge/frontend: Node.js 18+

### Clone & Install

```bash
git clone https://github.com/PhyAgentOS/PhyAgentOS.git
cd PhyAgentOS
pip install -e .             # Python ≥ 3.11
pip install -e ".[dev]"      # Dev dependencies
```

### What You Get After Installation

The CLI entry point `paos` comes from the project's Python package:

- `paos onboard` — Initialize workspace
- `paos agent` — Start interactive Agent CLI
- `paos agent -m "..."` — Single-turn message call
- `paos gateway` — Start long-running gateway service

---

## 2.4 5-Minute Quick Start

### Step 1: Install

```bash
git clone https://github.com/PhyAgentOS/PhyAgentOS.git && cd PhyAgentOS
pip install -e .
```

### Step 2: Initialize Workspace

```bash
paos onboard
```

This command: creates/refreshes `~/.PhyAgentOS/config.json`, prepares default workspace, syncs template files.

### Step 3: Start Runtime (Track B)

Open Terminal A:

```bash
python -m PhyAgentOS.runtime.watchdog
```

Uses the built-in simulation driver by default — zero hardware needed for full pipeline validation.

### Step 4: Start Agent (Track A)

Open Terminal B:

```bash
paos agent
```

Enter interactive mode and type natural language tasks, for example:

```text
Look around the room and tell me what objects you see.
```

### Verify Pipeline Without Hardware

```bash
python scripts/init_runtime_workspace.py --workspace /tmp/paos_runtime_smoke
python scripts/run_runtime_watchdog.py --workspace /tmp/paos_runtime_smoke --once
# → session marked succeeded, results in artifacts/
```

---

## 2.5 Configuration Details

### Minimal Configuration

```json
{
  "agents": {
    "defaults": {
      "model": "openrouter/openai/gpt-4o-mini"
    }
  },
  "providers": {
    "openrouter": {
      "api_key": "YOUR_API_KEY"
    }
  }
}
```

Location: `~/.PhyAgentOS/config.json`

### Key Configuration Domains

| Domain | Purpose |
|--------|---------|
| `agents.defaults` | Default model, workspace path |
| `providers` | LLM provider API keys and addresses |
| `gateway` | Gateway service configuration |
| `tools` | Tool enable/disable |
| `embodiments` | Embodiment config (single / fleet mode) |

### Fleet Mode Minimum Configuration

```json
{
  "embodiments": {
    "mode": "fleet",
    "shared_workspace": "~/.PhyAgentOS/workspaces/shared",
    "instances": [
      {
        "robot_id": "go2_edu_001",
        "driver": "go2_edu",
        "workspace": "~/.PhyAgentOS/workspaces/go2_edu_001"
      }
    ]
  }
}
```

### Workspace Paths

| Mode | Path |
|------|------|
| Single mode | `~/.PhyAgentOS/workspace` |
| Fleet shared workspace | `~/.PhyAgentOS/workspaces/shared` |
| Fleet robot workspace | `~/.PhyAgentOS/workspaces/<robot_id>` |

> After each config change, re-run `paos onboard` to refresh templates and add new fields.

---

## 2.6 Scenario Usage Guide

### 2.6.1 Simulation

The built-in `simulation` driver is the fastest way to validate the full pipeline.

```bash
# Terminal 1: Start simulation Watchdog
python -m PhyAgentOS.runtime.watchdog

# Terminal 2: Start Agent
paos agent
```

**Isaac Sim High-Fidelity Simulation (PIPER + Go2 Composite)**:

```bash
# GUI mode (requires local X display)
python hal/hal_watchdog.py --gui --interval 0.05 \
  --driver pipergo2_manipulation \
  --driver-config examples/pipergo2_manipulation_driver.json

# VNC mode (remote server/container, browser access)
python hal/hal_watchdog.py --vnc --interval 0.05 \
  --driver pipergo2_manipulation \
  --driver-config examples/pipergo2_manipulation_driver.json
# Open http://<host>:31315/vnc.html in browser
```

Then send Agent commands:

```bash
paos agent -m "open simulation"
paos agent -m "go to desk"
paos agent -m "pick up the red cube and return to the starting position"
```

> `--gui` and `--vnc` are mutually exclusive. Without either flag, runs headless.

---

### 2.6.2 Real Robot Arm (Franka Research 3)

#### Network Architecture

```
WorkStation PC → Control Box (Shop Floor: 172.16.0.x) → Robot Arm
```

#### First-Time Setup

1. Ethernet cable: PC ↔ Control Box (Shop Floor port)
2. Set PC wired network IP to `172.16.0.x` (e.g., `172.16.0.1`)
3. Activate FCI in Control Box Desk interface
4. Install backend drivers

#### Backend Installation

```bash
# pylibfranka (official Python bindings)
pip install pylibfranka

# franky-control (alternative high-level library, looser compatibility)
pip install git+https://github.com/TimSchneider42/franky.git
```

#### Driver Selection

| Driver Name | Description | Use Case |
|:------------|:------------|:---------|
| `franka_research3` | Raw pylibfranka driver | Precise control or real-time 1kHz |
| `franka_multi` | Multi-backend negotiation driver | Auto-selects available backend |

#### Launch

```bash
# Multi-backend auto-negotiation (recommended)
python hal/hal_watchdog.py --driver franka_multi

# Raw pylibfranka driver
python hal/hal_watchdog.py --driver franka_research3

# Custom configuration
python hal/hal_watchdog.py \
  --driver franka_multi \
  --driver-config examples/franka_research3.driver.json
```

#### Supported Actions

`move_to` (Cartesian position), `move_joints` (joint positions), `grasp`, `move_gripper`, `stop`, etc.

#### Real-Time Control Mode

Set `realtime_mode: true` to enable 1 kHz real-time control (requires real-time kernel).

> Before installation, verify library version compatibility with your robot system version.

---

### 2.6.3 Mobile Robot (Go2)

```bash
python hal/hal_watchdog.py \
  --driver go2_edu \
  --driver-config examples/go2_driver_config.json
```

The driver config JSON is passed through to the Go2 driver for remote ROS2, video, state streaming, and motion backend initialization.

---

### 2.6.4 Remote Chassis (XLeRobot)

```bash
python hal/hal_watchdog.py \
  --driver xlerobot_2wheels_remote \
  --driver-config examples/xlerobot_2wheels_remote.driver.json
```

Configuration includes ZMQ communication parameters, remote host address, etc.

---

### 2.6.5 ReKep Real-Robot Plugin

`rekep_real` is integrated via an external plugin repository:

```bash
# Deploy plugin
python scripts/deploy_rekep_real_plugin.py \
  --repo-url https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin.git

# Start
python hal/hal_watchdog.py --driver rekep_real
```

---

### 2.6.6 Fleet Multi-Robot Coordination

#### When to Use

- One Agent coordinates multiple robot instances
- Separate shared environment from per-robot action queues
- Explicit independent `EMBODIED.md` and `ACTION.md` per robot

#### Startup Sequence

1. Set `embodiments.mode = "fleet"`
2. Run `paos onboard`
3. Start one Watchdog per robot instance
4. Start a single `paos agent`

```bash
# Robot 1
python hal/hal_watchdog.py \
  --robot-id go2_edu_001 \
  --driver-config examples/go2_driver_config.json

# Robot 2
python hal/hal_watchdog.py \
  --robot-id xlerobot_lab_001 \
  --driver-config examples/xlerobot_2wheels_remote.driver.json

# Unified Agent
paos agent
```

#### Fleet Mode File Layout

| File | Location | Purpose |
|------|----------|---------|
| `ENVIRONMENT.md` | shared/ | Global environment state |
| `ROBOTS.md` | shared/ | Robot instance directory summary |
| `TASK.md` | shared/ | Multi-step task state |
| `ORCHESTRATOR.md` | shared/ | Global orchestration state |
| `EMBODIED.md` | per-robot/ | Per-robot runtime capability declaration |
| `ACTION.md` | per-robot/ | Per-robot action queue |

---

### 2.6.7 Minecraft Game Agent

PhyAgentOS remotely controls a local Minecraft Java Edition (1.20.4) via an HTTP bridge, enabling cloud-based Agent control of an in-game bot. Full deployment guides, usage manuals, configuration examples, and troubleshooting are maintained in dedicated scenario documents.

#### Three-Layer Document Index

| Reading Path | Document | Content |
|-------------|----------|---------|
| Understand architecture | [scenario overview](https://github.com/PhyAgentOS/PhyAgentOS/tree/main/docs/scenarios/game/minecraft) | File structure, bridge_server.js source |
| Get running quickly | [Deployment Guide](../../scenarios/game/minecraft/en/deployment.md) | Zero-to-deploy: Windows ngrok + bridge → Linux connection |
| Daily usage | [Usage Guide](../../scenarios/game/minecraft/en/usage.md) | CLI control, chat listener, bot teleport, script reference |

#### Quick Start

**Windows side** (see [Deployment Guide](../../scenarios/game/minecraft/en/deployment.md)):
```powershell
cd E:\mc_bridge
$env:MC_HOST="localhost"; $env:MC_PORT="25565"; $env:BOT_NAME="paos"
$env:MC_VERSION="1.20.4"; $env:API_PORT="3001"
node bridge_server.js
# Another terminal: ngrok http 3001 --region=ap
```

**Linux cloud**:
```python
from PhyAgentOS.runtime.targets.game.minecraft_target import MinecraftTarget
t = MinecraftTarget({"bridge_url": "https://xxx.ngrok-free.app"})
t.build(); t.reset({})
t.step({"type": "chat", "params": {"message": "Hello"}})
t.close()
```

Or via CLI:
```bash
paos minecraft say "mine 5 oak logs and come over"
```

#### Full Content Location

| Content | Location |
|---------|----------|
| Windows 9-step deployment | [deployment.md](../../scenarios/game/minecraft/en/deployment.md) |
| Observation space schema | [deployment.md §3.3](../../scenarios/game/minecraft/en/deployment.md#33-observation-space) |
| 16 action types | [deployment.md §4](../../scenarios/game/minecraft/en/deployment.md#4-action-space-16-types) |
| TARGETS.md / SKILLS.md config | [deployment.md §5-6](../../scenarios/game/minecraft/en/deployment.md#5-targetsmd-configuration) |
| Agent → SESSIONS.md pipeline | [deployment.md §7](../../scenarios/game/minecraft/en/deployment.md#7-full-pipeline-agent-task-dispatch) |
| CLI & chat control | [usage.md](../../scenarios/game/minecraft/en/usage.md) |
| Bot teleporting | [usage.md §3](../../scenarios/game/minecraft/en/usage.md#3-bot-teleporting) |
| 9 troubleshooting entries | [usage.md §5](../../scenarios/game/minecraft/en/usage.md#5-troubleshooting) |
| Code change reference | [usage.md §6](../../scenarios/game/minecraft/en/usage.md#6-code-change-reference) |

---

## 2.7 Runtime File Reference

| File | Location | Purpose |
|------|----------|---------|
| `ACTION.md` | Single or per-robot workspace | Pending action queue (JSON format) |
| `EMBODIED.md` | Single or per-robot workspace | Current robot capabilities, constraints, and connection declarations |
| `ENVIRONMENT.md` | Single or shared workspace | Current environment, objects, map, robot states |
| `LESSONS.md` | Single or shared workspace | Failure experience recording after Critic rejections |
| `TASK.md` | Single or shared workspace | Multi-step task decomposition state |
| `SESSIONS.md` | Single or shared workspace | Execution session queue (new protocol) |
| `TARGETS.md` | Shared workspace | Target (robot/simulation) registration index |
| `ORCHESTRATOR.md` | Shared workspace | Orchestration layer state |
| `ROBOTS.md` | Fleet shared workspace | Robot instance directory summary |

---

## 2.8 Common Interaction Examples

### Environment Query

```text
Look around and tell me what objects are present.
```

Verify: Agent can read `ENVIRONMENT.md`, environment state has been correctly written back by Watchdog.

### Robot Arm Manipulation Task

```text
Pick up the red apple on the table and place it on the tray.
```

Verify: Target object exists in environment state, robot profile declares corresponding actions, Watchdog successfully executes and clears the action queue.

### Mobile Robot Navigation

```text
Move near the refrigerator and stop.
```

Verify: Target semantic location exists in scene graph, current mobile robot supports navigation actions.

### Fleet Multi-Robot Coordination

```text
Send Go2 to patrol the doorway first, then have the robot arm grab the package on the table for handoff.
```

Verify: Agent recognizes multiple robot instances, actions dispatched to correct robot workspaces, `ROBOTS.md` correctly updates states.

### Isaac Sim Environment Manipulation

```bash
paos agent -m "open simulation"
paos agent -m "go to desk"
paos agent -m "pick up the red cube and return to the starting position"
```

### Minecraft Natural Language Control

```bash
paos minecraft say "mine 5 oak logs and come over"
```

The LLM auto-converts natural language into Minecraft action sequences.

You can also command the bot through in-game chat:
```bash
python test/chat_listener.py
# In Minecraft chat say: paos mine 5 oak logs
```

### VLA Model Grasping

```bash
paos agent -m "deploy a VLA to pick up the red cube"
```

Customize your VLA checkpoint by editing the `vla` block in `examples/pipergo2_manipulation_driver.json`.

---

## 2.9 Troubleshooting

### No API Key

**Symptom**: Agent starts but reports missing API key.

**Resolution**:
1. Check `~/.PhyAgentOS/config.json` for `providers.<name>.api_key`
2. Verify `agents.defaults.model` matches the provider
3. Ensure API key format is correct with no extra whitespace

### No EMBODIED.md After Watchdog Start

**Symptom**: Critic reports `EMBODIED.md` not found.

**Resolution**:
1. Confirm `paos onboard` was executed
2. Confirm Watchdog started successfully
3. Verify the selected driver's profile file exists and is readable
4. In Fleet mode, verify you're inspecting the correct robot's workspace

### ACTION.md Has Content But No Execution

**Resolution**:
1. Confirm the corresponding Watchdog is still running
2. Check `ACTION.md` JSON code block format integrity
3. Check Watchdog terminal output for driver errors
4. Check if `driver-config` is missing critical parameters

### Action Rejected by Critic

**Resolution**:
1. First check `LESSONS.md` for failure reasons
2. Check if target action is declared in `EMBODIED.md` Supported Actions
3. Check `ENVIRONMENT.md` for the corresponding target object, map info, or robot connection state
4. Verify action parameters (coordinates, joint angles) are within physical constraints

### Fleet Mode Task Not Dispatched to Correct Robot

**Resolution**:
1. Verify `robot_id`, `driver`, `workspace` in config match
2. Confirm Watchdog started with `--robot-id`
3. Check shared workspace `ROBOTS.md` correctly generated
4. Confirm task semantics explicitly identify target robot

### rekep_real Driver Not Found

**Resolution**:
1. Confirm plugin deployment script was executed: `python scripts/deploy_rekep_real_plugin.py`
2. Confirm plugin repo is registered in `~/.PhyAgentOS/plugins/`
3. Restart Watchdog for plugin to take effect

### Isaac Sim Startup Failure

**Resolution**:
1. Confirm Isaac Sim is correctly installed
2. Check path config in `pipergo2_manipulation_driver.json` `isaac_env` block
3. In `--vnc` mode, inspect first-start re-exec logs
4. Verify `LD_LIBRARY_PATH` is correctly set (auto-handled in VNC mode)

### Minecraft Bridge Connection Failure (SSL Error)

**Symptom**: `SSL: CERTIFICATE_VERIFY_FAILED`.

**Resolution**:
1. Free ngrok has incomplete certificates; add `"verify_ssl": false` in TARGETS.md config
2. If still failing, check for extra whitespace around the `bridge_url` value

### Minecraft API Returns Empty or HTML

**Symptom**: `JSONDecodeError: Expecting value` or HTML confirmation page returned.

**Resolution**:
1. Free ngrok shows a confirmation page first; ensure `ngrok-skip-browser-warning: true` header is set in `minecraft_target.py`
2. Verify the ngrok tunnel is still running
3. Confirm the bridge URL includes the `https://` prefix

### Minecraft Bot Teleport Not Working

**Symptom**: Bot stuck at spawn point, can't move to player.

**Resolution**:
1. Ensure cheats are enabled (Esc → Open to LAN → Allow Cheats: ON)
2. Player must be within the bot's render distance
3. Use `test/tp_bot.py` to manually teleport the bot to your coordinates

---

## Further Reading

- [Part 1: Framework Introduction](../01-framework-introduction.md) — Design philosophy, architecture, roadmap
- [Part 3: API Developer Manual](../03-developer-manual.md) — API reference, secondary development, coding style
