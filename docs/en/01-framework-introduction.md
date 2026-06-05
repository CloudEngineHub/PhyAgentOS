# PhyAgentOS Framework Introduction

> A project overview for everyone: design philosophy, technical architecture, current progress, roadmap, TODO list, and demo showcases.

---

## Table of Contents

- [1.1 Project Overview](#11-project-overview)
- [1.2 Design Philosophy](#12-design-philosophy)
- [1.3 Technical Architecture](#13-technical-architecture)
- [1.4 Core Features](#14-core-features)
- [1.5 Current Progress](#15-current-progress)
- [1.6 Architecture Evolution Roadmap](#16-architecture-evolution-roadmap)
- [1.7 Future Development Directions](#17-future-development-directions)
- [1.8 Detailed TODO List](#18-detailed-todo-list)
- [1.9 Demo Showcases](#19-demo-showcases)
- [1.10 Project Structure](#110-project-structure)

---

## 1.1 Project Overview

**PhyAgentOS** (Physical Agent Operating System) is a self-evolving embodied intelligence framework based on agentic workflows. Jointly developed by **Sun Yat-sen University HCP Lab** and **Peng Cheng Laboratory**, built on the [nanobot](https://github.com/HKUDS/nanobot) lightweight agent framework.

### Core Value Proposition

Traditional "LLM-direct-to-hardware" approaches tightly couple reasoning to execution — switching robots means rewriting the entire pipeline. PhyAgentOS changes this through **Cognitive-Physical Decoupling**:

- **One Codebase, Any Hardware**: Adding a new robot means implementing one Target Adapter (~100 lines); zero changes to the scheduling layer
- **Three Safety Layers**: Critic validation → Strict Preflight → Target-side SafetyGuard; mandatory for real-robot deployment
- **Fully Auditable**: State, actions, and perception results are written to Markdown + YAML files; every step is traceable and reproducible
- **Zero-Friction Migration**: The same Session protocol runs identically across sim, real, and game targets

### Key Metrics

| Metric | Value |
|--------|-------|
| Framework Version | v0.2.1 |
| Python Requirement | ≥ 3.11 |
| License | MIT |
| HAL Drivers | 10+ |
| Robot Profiles | 9 |
| Channel Integrations | 14 |
| Built-in Skills | 13 |
| Test Files | 49 |

### Related Resources

- **GitHub**: [https://github.com/PhyAgentOS/PhyAgentOS](https://github.com/PhyAgentOS/PhyAgentOS)
- **Project Website**: [https://phy-agent-os.net/](https://phy-agent-os.net/)
- **ReKep Real-Robot Plugin**: [https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin](https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin)
- **Unitree G1 Voice Plugin**: [https://github.com/shawnmsw28/PhyAgentOS-unitree-g1-voice-plugin](https://github.com/shawnmsw28/PhyAgentOS-unitree-g1-voice-plugin)

---

## 1.2 Design Philosophy

### 1.2.1 State-as-a-File

PhyAgentOS exposes all runtime state as Markdown files in the local workspace. Track A (brain) and Track B (execution layer) communicate not through Python function calls, but through reading and writing shared Markdown files.

```
Track A (Agent)          Workspace Files         Track B (Runtime)
    │                                               │
    ├── reads ENVIRONMENT.md ──────────────→ writes state
    │                                               │
    ├── writes SESSIONS.md ────────────────→ consumes execution
    │                                               │
    ├── reads LESSONS.md ←─────────────────── writes experiences
```

Three key benefits:
- **Complete Decoupling**: Agent and Runtime can be separate processes, separate machines, separate languages
- **Extreme Transparency**: Open a Markdown file at any time to view current system state
- **Naturally Auditable**: All historical states are preserved as files, traceable and reproducible

### 1.2.2 Cognitive-Physical Decoupling (Dual-Track)

The system is divided into two fully independent tracks:

| Track | Responsibility | Entry Point |
|-------|---------------|-------------|
| **Track A (Cognitive)** | Intent understanding, action planning, safety validation, memory management | `paos agent` / `paos gateway` |
| **Track B (Execution)** | Instruction reading, hardware driving, action execution, state writeback | `python -m PhyAgentOS.runtime.watchdog` |

The two tracks are strictly isolated by a file protocol boundary. Track A doesn't know the motor model, Track B doesn't know the LLM prompt.

### 1.2.3 Session-Centered Runtime

The new architecture upgrades hardware abstraction from "driver-centered" to "session-centered":

- **Old Model (Driver-Centered)**: observe / execute / profile / safety coupled in a single Driver class
- **New Model (Session-Centered)**: RolloutTarget (what to execute on) + SkillRuntime (how to execute) + TargetAdapter (how to translate) — three-way decoupling

The same Session protocol runs identically across four target kinds: game / debug / simulation / real_robot.

### 1.2.4 Three-Scenario Synergy

Three parallel scenarios share the Base Runtime kernel and evolve independently:

- **Game Agent (Stardew Valley)**: Low-cost validation of long-term memory and autonomous decision-making → strategies reusable in Sim/Real
- **Sim (MuJoCo + ManiSkill)**: Benchmark evaluation + batch experience mining → experience transfer to Real
- **Real (Mobile Manipulation + Voice)**: Real interaction data → improved Sim fidelity

---

## 1.3 Technical Architecture

### 1.3.1 Overall Architecture

```
                    ┌─────────────────────────────┐
                    │     Cognitive (Track A)      │
                    │  Planner / Critic / Memory   │
                    │     → writes SESSIONS.md     │
                    └──────────────┬──────────────┘
                                   │ File Protocol Boundary
                    ┌──────────────┴──────────────┐
                    │     Base Runtime (Shared)    │
                    │  WatchdogSupervisor           │
                    │  SessionRegistry              │
                    │  LESSONS.md Experience Base   │
                    │  Critic Validation Framework  │
                    └──────┬──────┬──────┬────────┘
                           │      │      │
              ┌────────────┼──────┼──────┼────────────┐
              ▼            ▼      ▼      ▼            ▼
   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
   │Scn 1: Game   │ │  Scn 2: Sim  │ │ Scn 3: Real  │
   │Stardew Valley│ │ MuJoCo+      │ │Mobile Mani+  │
   │Long Memory   │ │ ManiSkill    │ │Voice         │
   │Autonomous    │ │ Self-Evolve  │ │Human-Like    │
   └──────────────┘ └──────────────┘ └──────────────┘
```

### 1.3.2 Runtime Execution Pipeline

```
WatchdogSupervisor
  → SessionScheduler (reads SESSIONS.md)
    → SessionRunner (binds Target + Skill)
      → SkillRuntime (execution strategy loop)
        → TargetSessionHandle (drives Target.step())
          → writes back ENVIRONMENT.md / LESSONS.md
```

### 1.3.3 Three-Way Decoupling: Adapter + Bridge

```
Agent generates action intent
  → TargetAdapter (translates intent to target-executable actions)
    → PolicyAdapter (translates observations to policy-consumable format)
      → ActionBridge (bridges policy output to target input)
```

`AdapterPlan` auto-composes adaptation steps, eliminating the target × skill combinatorial explosion.

### 1.3.4 Core Interfaces

The single entry point for all three scenarios is `BaseRolloutTarget`:

```python
class BaseRolloutTarget(ABC):
    def build(self) -> None: ...          # Initialize environment
    def reset(self, session_ctx: dict) -> dict: ...  # Reset → return initial obs
    def observe(self) -> dict: ...        # Get current observation
    def step(self, action) -> dict: ...   # Execute one step
    def close(self) -> None: ...          # Release resources
    def get_state(self) -> dict: ...      # Runtime state (for ENVIRONMENT.md writeback)
```

WatchdogSupervisor does not need to know whether the Target is a game, simulation, or real robot.

### 1.3.5 Decoupling Boundaries

| Component | May Know | Must NOT Know |
|-----------|----------|---------------|
| **RolloutTarget** | How to build/reset/step itself | Policy inference, Skill logic, upper Agent |
| **SkillRuntime** | How to call target and policy_client | Target internal implementation |
| **TargetAdapter** | How to do data transformation | Policy inference, target internal state |
| **WatchdogSupervisor** | How to manage state machine and routing | How to execute step specifics |

---

## 1.4 Core Features

| Feature | Description |
|---------|-------------|
| **Session-Centered Runtime** | `WatchdogSupervisor` → `SessionRunner` → `SkillRuntime` → `TargetSessionHandle` pipeline |
| **Target-Configured** | `game` / `debug` / `simulation` / `real_robot` four target kinds, registered in `TARGETS.md` |
| **Adapter + Bridge** | `TargetAdapter` + `PolicyAdapter` + `ActionBridge` three-way decoupling, auto-composed |
| **Dual Skill Runtimes** | `PolicySkillRuntime` maintains policy closed-loop + `BuiltinSkillRuntime` manages agent interactive loop |
| **Strict Preflight** | 10 validation checks (target / sensor / perception / contract / tool); rejected before execution |
| **File Protocol Matrix** | `TARGETS.md` · `SKILLS.md` · `SESSIONS.md` · `ENVIRONMENT.md` · `LESSONS.md` |
| **Multi-Layer Safety** | Critic validation → Preflight contract checks → Target-side SafetyGuard → Operator Override |
| **Fleet Mode** | Multi-robot coordination, shared + per-robot workspaces, priority-based serial scheduling |
| **Perception Plugin System** | `SensorConfig` / `PerceptionConfig` YAML + `EnvironmentWriter` auditable writeback |
| **External Plugin Mechanism** | Dynamic loading of third-party drivers via `PhyAgentOS_plugin.toml`, no core code changes |

---

## 1.5 Current Progress

### Version History

| Version | Date | Milestone |
|:--------|:-----|:----------|
| v0.1.0 | 2026-04-29 | Hackathon baseline: plugin-based HAL, ReKep / SAM3 real-robot grasping & VLN full pipeline |
| v0.1.1 | 2026-05-18 | Session-Centered Runtime MVP: `DummySimTarget` + `DummyAdapter` + `DummyClient` serial pipeline |
| v0.1.2 | 2026-05-20 | Perception plugin system: `SensorConfig` / `PerceptionConfig` YAML + `EnvironmentWriter` auditable writeback |
| v0.1.3 | 2026-05-25 | Strict separation of `PolicySkillRuntime` / `BuiltinSkillRuntime`; Game Agent & Benchmarking ready |
| v0.2.1 | 2026-05-29 | Minecraft ready: cloud agent connects to user's local server |

### Achieved Capabilities

- 10+ HAL driver implementations (simulation, Franka, Go2, XLeRobot, PIPER+Go2 composite, etc.)
- 9 robot Profiles (simulation, franka, go2_edu, xlerobot, etc.)
- 14 channel integrations (Telegram, Discord, Slack, Feishu, DingTalk, etc.)
- 13 built-in Skills (agent-mode, clawhub, cron, github, image, etc.)
- Built-in simulation support (PyBullet physics + Isaac Sim high-fidelity)
- Fleet multi-robot coordination mode
- Perception pipeline (GeometryPipeline + SegmentationPipeline + FusionPipeline)
- Semantic navigation (SemanticNavigationTool, semantic goal → physical coordinates)
- External plugin dynamic loading mechanism

---

## 1.6 Architecture Evolution Roadmap

### Current Architecture (v0.2.1, Driver-Centered HAL)

Current Track B is centered on `BaseDriver`: observe / execute / profile / safety coupled in one subclass. Track A and Track B communicate via `ACTION.md` (atomic action queue).

### Refactoring Target (Session-Centered Runtime)

Documents in `plans/` (not ordinary plans, but architecture specifications) define the upgrade from Driver-Centered HAL to Session-Centered Runtime:

| Old Module | New Module | Note |
|------------|------------|------|
| `BaseDriver` | `RolloutTarget` + `SkillRuntime` + `TargetAdapter` | Split into three first-class objects |
| `hal_watchdog.py` | `WatchdogSupervisor` | Upgraded from action poller to execution session supervisor |
| `ACTION.md` | `SESSIONS.md` | Session schema replaces action schema |
| `ROBOTS.md` | `TARGETS.md` | Extended to unified sim+real index |
| Navigation/ReKep as driver-internal functions | `SkillRuntime` (BuiltinAlgorithmSkillRuntime) | Elevated to first-class skill runtime |
| Simulation driver | `SimTarget` | Elevated to first-class rollout target |

### Development Sequence: Base First, Three Scenarios in Parallel

```
Phase 0: Base MVP (1-2 weeks)
  → Schema + State I/O + Watchdog + Dummy closed-loop

Phase 1: Three scenarios in parallel (1-2 weeks each, non-blocking)
  ├── Scenario 1: Stardew Valley Game Agent (current highest priority)
  ├── Scenario 2: MuJoCo + ManiSkill Simulation
  └── Scenario 3: Real-Robot Mobile Manipulation + Voice

Phase 2: Deep Evolution
  → Policy Server / LIBERO / RoboCasa / Hybrid Skill
```

> **Design Guardrails**: Base layer must NOT import any scenario module; each new scenario = ~100 lines of `BaseRolloutTarget` subclass; three scenarios progress in parallel without blocking each other.

---

## 1.7 Future Development Directions

### Roadmap Phases

| Phase | Focus | Key Goals |
|-------|-------|-----------|
| **Phase 1** (current) | Desktop closed-loop & Markdown protocol | Single-robot development loop, Markdown protocol communication |
| **Phase 2** | Multi-embodiment coordination & multimodal memory | Heterogeneous multi-robot coordination, rich memory systems |
| **Phase 3** | Constraint solving & advanced heterogeneous coordination | Complex constraint satisfaction, advanced orchestration |

### Short-term Priorities (1-2 months)

1. **Stardew Valley Game Agent (Scenario 1)**
   - StardewTarget implementation: connect to SMAPI mod (HTTP)
   - Cross-season long-term memory validation
   - NPC relationship network social memory training
   - 14-day autonomous run acceptance test

2. **Base Runtime Completion**
   - Session state machine: pending → claimed → running → succeeded / failed / timed_out
   - Goal Graph + Session Compiler
   - Fallback chain mechanism

3. **Perception Deepening**
   - Standardized camera/LiDAR integration
   - Segmentation model dependency management
   - Scene graph construction and writeback protocol refinement

### Mid-term Directions (3-6 months)

- **Scenario 2: MuJoCo + ManiSkill Simulation**
  - ManiSkillTarget implementation
  - BenchmarkHarness automated evaluation
  - Self-evolving experience loop (LESSONS.md auto-accumulation)

- **Scenario 3: Real Mobile Manipulation + Voice**
  - CompositeTarget multi-robot composition
  - SafetyGuard local safety adjudication
  - Action Chunk buffer mechanism (chunk_size=8, soft blend)

- **Policy Server Standardization**
  - WebSocket + msgpack communication protocol
  - Unified Policy Backend abstraction
  - Unified client API for sim/real

### Long-term Vision

1. **Any Hardware**: Plugin architecture supports any Python-controllable device
2. **Any Task**: From simple grasping to long-horizon manipulation
3. **Any Scale**: From desktop arm to industrial Fleet
4. **Self-Evolving**: LESSONS.md + SKILLS.md continuous improvement loop
5. **Safe & Transparent**: Markdown protocol makes all states inspectable
6. **Open Ecosystem**: Community plugins, benchmarks, integrations

---

## 1.8 Detailed TODO List

### Base Runtime (Phase 0)

- [ ] Pydantic Session Schema definition (session_id, goal, target, skill, params, status)
- [ ] State I/O layer: read/write tools for SESSIONS.md / TARGETS.md / ENVIRONMENT.md
- [ ] WatchdogSupervisor core state machine (pending → claimed → running → succeeded/failed)
- [ ] SessionRegistry registration and lifecycle management
- [ ] HealthMonitor (policy server / robot / simulator / session health monitoring)
- [ ] ResultWriter unified writeback module
- [ ] FailureEscalator (retry / reset / cancel / notify / safety stop)
- [ ] DummySimTarget + DummyAdapter + DummyClient closed-loop acceptance

### Scenario 1: Stardew Valley Game Agent (Phase 1A, Current Priority)

- [ ] SMAPI Mod development (HTTP API exposing game state)
- [ ] StardewTarget implementation (build / reset / observe / step / close)
- [ ] StardewAdapter data transformation (game coords → target coords)
- [ ] NPC relationship network memory structure
- [ ] Cross-season / cross-day memory persistence
- [ ] Planner autonomous goal generation (mining/fishing/social/farming parallel goals)
- [ ] 14-day autonomous run validation
- [ ] LESSONS.md game failure experience accumulation

### Scenario 2: MuJoCo + ManiSkill Simulation (Phase 1B)

- [ ] ManiSkillTarget implementation (build / observe / step, RGBD + proprioception)
- [ ] BenchmarkHarness evaluation framework (run_benchmark → BenchmarkResult)
- [ ] Batch rollout parallel execution
- [ ] Auto LESSONS.md experience accumulation
- [ ] Benchmark score tracking and visualization

### Scenario 3: Real Mobile Manipulation + Voice (Phase 1C)

- [ ] CompositeTarget interface definition (multi-robot composition)
- [ ] SafetyGuard local safety adjudicator
- [ ] Action Chunk buffering + soft blend
- [ ] VoiceChannel interface (interface-only initially)
- [ ] Go2 + Franka real-robot dry-run validation

### Follow-up Deep Evolution

- [ ] OpenPI Policy Server integration
- [ ] LIBERO / RoboCasa benchmark integration
- [ ] Goal Graph + Session Compiler
- [ ] Hybrid Skill (Nav → VLA → ReKep mixed pipeline)
- [ ] ESP32 IoT device integration
- [ ] Huaner series educational robot drivers
- [ ] Cross-robot experience sharing (inter-Fleet LESSONS.md sharing)

---

## 1.9 Demo Showcases

### Verified Demo Scenarios

| Demo | Robot | Capability |
|------|-------|------------|
| One-Click Deploy | AgileX PIPER | Code-free robot arm deployment |
| XLeRobot Dual-Arm | XLeRobot | Base movement + dual-arm motion |
| SAM3 Semantic Grasping | AgileX PIPER | Natural language driven semantic grasping |
| ReKep Constraint Grasping | Dobot Nova 2 | Natural language driven constraint grasping |
| Franka QA + Grasping | Franka Research 3 | Real-time dialogue + NL driven grasping |
| Go2 Semantic Navigation | Unitree Go2 | Semantic goal navigation ("go patrol at the door") |
| Isaac Sim Composite Operation | PIPER + Go2 | Code-free Isaac Sim environment manipulation |
| Minecraft Cloud Agent | Minecraft | Cloud agent connecting to local server |

### Supported Devices

| Type | Model | Status | Notes |
|------|-------|--------|-------|
| Desktop Arm | AgileX PIPER | 🟢 Verified | ReKep & SAM3 full pipeline |
| Composite | PIPER + Unitree Go2 | 🟡 Partial | Locomotion adaptation in progress |
| Desktop Arm | Dobot Nova 2 | 🟢 Verified | ReKep deployment verified |
| Quadruped | Unitree Go2 | 🟡 Partial | Movement + semantic navigation |
| Dual-Arm | XLeRobot | 🟢 Verified | Dual-arm grasping implemented |
| IoT | ESP32 | 🟡 Partial | Voice dialogue interaction |
| Industrial | Franka Research 3 | 🟢 Verified | Visual reasoning + grasping |
| Educational | Huaner Series | 🔴 Not adapted | Driver plugin pending |
| General | Built-in Simulator | 🟢 Verified | Disk-mapping-based lightweight sim |

### Launch Examples

**Hardware-Free Smoke Test**:
```bash
python scripts/init_runtime_workspace.py --workspace /tmp/paos_runtime_smoke
python scripts/run_runtime_watchdog.py --workspace /tmp/paos_runtime_smoke --once
# → session marked succeeded, results in artifacts/
```

**Simulated Robot Arm**:
```bash
# Terminal 1: Start Runtime
python -m PhyAgentOS.runtime.watchdog

# Terminal 2: Start Agent
paos agent -m "pick up the red cube on the table"
```

**Isaac Sim High-Fidelity Simulation**:
```bash
python hal/hal_watchdog.py --gui --interval 0.05 \
  --driver pipergo2_manipulation \
  --driver-config examples/pipergo2_manipulation_driver.json
paos agent -m "open simulation"
paos agent -m "go to desk"
paos agent -m "pick up the red cube and return to the starting position"
```

---

## 1.10 Project Structure

```
PhyAgentOS/
│
├── PhyAgentOS/agent/          # Track A — Planner / Critic / Memory
│   ├── loop.py                #   Main Agent loop
│   ├── context.py             #   Context window construction
│   ├── memory.py              #   Short/long-term memory system
│   ├── skills.py              #   Skill loading and execution
│   ├── subagent.py            #   Sub-agent spawning
│   ├── tools/                 #   Built-in tools (File, Shell, EmbodiedAction, etc.)
│   ├── cli/                   #   CLI entry: paos onboard / agent / gateway
│   ├── providers/             #   LLM Provider adapters
│   ├── channels/              #   14+ messaging platform integrations
│   └── config/                #   Pydantic config models
│
├── PhyAgentOS/runtime/        # Track B — Execution Plane
│   ├── watchdog/              #   WatchdogSupervisor
│   ├── sessions/              #   SessionRunner / TargetSessionHandle
│   ├── targets/               #   RolloutTarget (game·debug·sim·real)
│   ├── skills/                #   PolicySkillRuntime / BuiltinSkillRuntime
│   ├── adapters/              #   TargetAdapter / PolicyAdapter / Bridge
│   ├── perception/            #   Perception Runtime / EnvironmentWriter
│   ├── preflight/             #   RuntimeCompatibilityPreflight
│   └── schemas/               #   Pydantic Schema
│
├── PhyAgentOS/skills/         # Built-in Skills (13)
│
├── hal/                       # Legacy HAL (deprecated, phased out)
│   ├── hal_watchdog.py        #   Legacy Watchdog entry
│   ├── base_driver.py         #   BaseDriver abstract base class
│   ├── drivers/               #   Built-in driver implementations (10+)
│   ├── profiles/              #   Robot Profiles (9)
│   ├── navigation/            #   Navigation stack
│   ├── perception/            #   Perception service
│   ├── ros2/                  #   ROS2 bridge
│   ├── simulation/            #   Simulation scene
│   └── plugins.py             #   External plugin registry
│
├── bridge/                    # TypeScript bridge layer
├── configs/runtime/           # Sensor / Perception / Contract YAML
├── scripts/                   # Deployment scripts
├── examples/                  # Driver config examples (14)
├── tests/                     # pytest test suite (49 files)
└── docs/                      # Legacy docs (reference)
```

---

## Further Reading

- [Part 2: User Manual](../02-user-manual.md) — Quick start, scenario configuration, troubleshooting
- [Part 3: API Developer Manual](../03-developer-manual.md) — API reference, secondary development, coding style
