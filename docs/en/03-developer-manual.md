# PhyAgentOS API Developer Manual

> For secondary developers, hardware integrators, plugin authors, and maintainers. Covers API interfaces, secondary development workflows, coding style standards, implementation boundaries, and contribution rules.

---

## Table of Contents

- [3.1 About This Manual](#31-about-this-manual)
- [3.2 Architecture Deep Dive](#32-architecture-deep-dive)
- [3.3 API Reference](#33-api-reference)
  - [3.3.1 BaseDriver Interface](#331-basedriver-interface)
  - [3.3.2 BaseRolloutTarget Interface](#332-baserollouttarget-interface)
  - [3.3.3 BaseSkillRuntime Interface](#333-baseskillruntime-interface)
  - [3.3.4 TargetAdapter Interface](#334-targetadapter-interface)
  - [3.3.5 WatchdogSupervisor Internal Architecture](#335-watchdogsupervisor-internal-architecture)
  - [3.3.6 Agent-Side APIs](#336-agent-side-apis)
  - [3.3.7 Configuration Schema](#337-configuration-schema)
  - [3.3.8 File Protocol Conventions](#338-file-protocol-conventions)
- [3.4 Secondary Development Guide](#34-secondary-development-guide)
  - [3.4.1 Adding a New Driver](#341-adding-a-new-driver)
  - [3.4.2 Adding a New Target](#342-adding-a-new-target)
  - [3.4.3 Developing External Plugins](#343-developing-external-plugins)
  - [3.4.4 Adding a New Skill](#344-adding-a-new-skill)
  - [3.4.5 Integrating a New Robot](#345-integrating-a-new-robot)
  - [3.4.6 Extending the Perception Pipeline](#346-extending-the-perception-pipeline)
  - [3.4.7 Extending the Navigation Module](#347-extending-the-navigation-module)
  - [3.4.8 ROS2 Adapter Development](#348-ros2-adapter-development)
- [3.5 Coding Style Standards](#35-coding-style-standards)
- [3.6 Implementation Boundaries](#36-implementation-boundaries)
- [3.7 Testing Standards](#37-testing-standards)
- [3.8 Contribution & Submission Rules](#38-contribution--submission-rules)
- [3.9 Appendix](#39-appendix)

---

## 3.1 About This Manual

### Who This Is For

If your goal is no longer just "get the system running" but:
- Understanding module responsibilities within the repository
- Adding or modifying built-in drivers
- Integrating new robots via HAL
- Developing independent plugin repositories
- Integrating perception, navigation, or ROS2 capabilities
- Contributing tests, documentation, or deployment instructions

Then this document is your primary reference.

### Recommended Reading Path

| Goal | Start With |
|------|-----------|
| Understand runtime communication | [§3.2](#32-architecture-deep-dive) → [§3.3.8](#338-file-protocol-conventions) |
| Integrate a new robot | [§3.4.1](#341-adding-a-new-driver) → [§3.4.5](#345-integrating-a-new-robot) |
| Develop external plugins | [§3.4.3](#343-developing-external-plugins) |
| Understand full architecture | [Part 1 §1.3](../01-framework-introduction.md#13-technical-architecture) → [§3.2](#32-architecture-deep-dive) |

---

## 3.2 Architecture Deep Dive

### 3.2.1 Core Design: Cognitive-Execution Decoupling

PhyAgentOS's core value lies in decoupling the cognitive and execution layers via explicit protocols. **Many "interfaces" are fundamentally file protocols and runtime conventions, not Python function signatures.**

- **Track A (Cognitive)**: Planner / Critic / Tool / Memory
- **Track B (Execution)**: Watchdog / SessionRunner / SkillRuntime / Target
- **Protocol Boundary**: Markdown files carry shared state, not cross-layer Python calls

### 3.2.2 Runtime Files Are the "Ground Truth"

The following files are often more important than class diagrams:

| File | Logical Meaning |
|------|----------------|
| `ENVIRONMENT.md` | Environment state ground truth |
| `EMBODIED.md` | Robot capability ground truth |
| `SESSIONS.md` | Execution intent ground truth |
| `ACTION.md` | Action queue ground truth |
| `LESSONS.md` | Failure experience ground truth |

**Reading only the code without understanding the files will lead to misinterpreting system behavior.**

### 3.2.3 Single vs Fleet Development Implications

When developing any functionality involving embodied actions, navigation, or connectivity, you must explicitly consider both runtime semantics:

- **single mode**: One workspace, all state files in one place
- **fleet mode**: Shared workspace for global state, per-robot workspaces for private state

### 3.2.4 Distinguishing Templates, Profiles, and Runtime Files

| Concept | Location | Meaning |
|---------|----------|---------|
| **Templates** | `PhyAgentOS/templates/` | Define file structure and suggested fields |
| **Profile** | `hal/profiles/` | Static capability declaration for a robot type |
| **Runtime Files** | workspace/ | Actual state surface read/written by Agent/Critic/Watchdog |

In short: **Templates define structure, Profiles provide instance type descriptions, Runtime files carry live state.**

---

## 3.3 API Reference

### 3.3.1 BaseDriver Interface

**Location**: `hal/base_driver.py`

All hardware and simulation drivers must inherit from `BaseDriver`.

#### Required Abstract Methods

```python
class BaseDriver(ABC):
    def get_profile_path(self) -> str:
        """Return the path to the driver's EMBODIED.md Profile"""

    def load_scene(self, scene: dict) -> None:
        """Initialize world state from scene dictionary"""

    def execute_action(self, action_type: str, params: dict) -> str:
        """Execute atomic action, return result string"""

    def get_scene(self) -> dict:
        """Return current world state dictionary"""
```

#### Optional Overrides

```python
def connect(self) -> None:           # Establish hardware connection
def disconnect(self) -> None:        # Close connection
def is_connected(self) -> bool:      # Check connection status
def health_check(self) -> bool:      # Lightweight health check
def get_runtime_state(self) -> dict: # Return optional runtime state (nav, connection, etc.)
def close(self) -> None:             # Release hardware resources
```

#### Driver Loading

Drivers are registered in `hal/drivers/__init__.py` `DRIVER_REGISTRY` and loaded via `load_driver(name, **kwargs)`.

---

### 3.3.2 BaseRolloutTarget Interface

**Location**: `PhyAgentOS/runtime/targets/base.py` (new version)

The single entry point for all three scenarios. WatchdogSupervisor does not need to know whether the Target is a game, simulation, or real robot.

```python
class BaseRolloutTarget(ABC):
    def build(self) -> None:
        """Initialize environment (connect SMAPI, launch sim instance, establish hardware session, etc.)"""

    def reset(self, session_ctx: dict) -> dict:
        """Reset to initial state, return initial observation dict"""

    def observe(self) -> dict:
        """Get current observation (RGBD, joints, voice, game state, etc.)"""

    def step(self, executable_action: dict) -> dict:
        """Execute one action step, return obs / reward / done / info"""

    def close(self) -> None:
        """Release resources (disconnect, close sim window, etc.)"""

    def get_state(self) -> dict:
        """Return runtime state dict for ENVIRONMENT.md writeback"""
```

#### Scenario Implementation Examples

```python
# Scenario 1: Stardew Valley Game Target
class StardewTarget(BaseRolloutTarget):
    def build(self): ...       # Connect SMAPI mod (HTTP)
    def reset(self, ctx): ...  # Load game day/season
    def observe(self): ...     # Return: position/time/inventory/NPC relations/crop state
    def step(self, action): ...# Execute move_to/interact/sleep
    def close(self): ...       # Disconnect SMAPI

# Game Target: Minecraft (verified)
class MinecraftTarget(BaseLocalTarget):
    def build(self): ...       # HTTP GET /health → verify bridge reachable
    def reset(self, ctx): ...  # Initial observation (position/inventory/nearby blocks/entities)
    def observe(self): ...     # HTTP GET /state → full game snapshot
    def step(self, action): ...# HTTP POST /action → mineflayer execution
    def close(self): ...       # Release HTTP client

# Scenario 2: Simulation Target
class ManiSkillTarget(BaseRolloutTarget):
    def build(self): ...       # Initialize ManiSkill environment
    def observe(self): ...     # RGBD + proprioception + language instruction
    def step(self, action): ...# Continuous action → obs/reward/done/info

# Scenario 3: Real Composite Target
class CompositeTarget(BaseRolloutTarget):  # Go2 + Franka
    def observe(self): ...     # RGBD + force + joints + voice text
    def step(self, action): ...# chunk buffer + soft blend
```

---

### 3.3.3 BaseSkillRuntime Interface

**Location**: `PhyAgentOS/runtime/skills/base.py` (new version)

```python
class BaseSkillRuntime(ABC):
    def start(self, session_ctx: dict, target: BaseRolloutTarget) -> None:
        """Initialize skill execution context"""

    def tick(self, session_ctx: dict, target: BaseRolloutTarget) -> dict:
        """Called once per execution cycle, return status dict"""

    def cancel(self, session_ctx: dict, reason: str) -> None:
        """Interrupt execution"""

    def snapshot(self, session_ctx: dict) -> dict:
        """Return current skill snapshot"""
```

#### Skill Runtime Hierarchy

```
SkillRuntime
├── PolicyBackedSkillRuntime
│   ├── VLASkillRuntime
│   ├── OpenPISkillRuntime
│   └── GR00TSkillRuntime
├── BuiltinAlgorithmSkillRuntime
│   ├── SemanticNavigationRuntime
│   ├── TargetNavigationRuntime
│   └── ReKepGraspRuntime
├── HybridSkillRuntime
│   ├── NavThenVLARuntime
│   └── ReKepThenVLARuntime
└── DirectAtomicRuntime
```

**Key Design**: Skill runtime focuses on "how to run", target on "how to execute", adapter on "how to translate". Clear separation of concerns.

---

### 3.3.4 TargetAdapter Interface

**Location**: `PhyAgentOS/runtime/adapters/base.py` (new version)

```
TargetAdapter
├── SimAdapter (BuiltinSim / RoboCasa / LIBERO)
└── RealAdapter (Franka / Go2 / XLeRobot / UR5)
```

Responsibilities:
- Target-specific observation difference handling (coordinate transforms, sensor data normalization)
- Target-specific action difference handling (normalization/de-normalization, sticky gripper, chunk decode)
- `AdapterPlan` auto-composes adaptation steps

---

### 3.3.5 WatchdogSupervisor Internal Architecture

**Location**: `PhyAgentOS/runtime/watchdog/supervisor.py` (new version)

```
WatchdogSupervisor
├── WorkspaceWatcher      # Monitors SESSIONS.md / TARGETS.md / ENVIRONMENT.md
├── SessionRegistry       # Session lifecycle management (pending→claimed→running→succeeded/failed)
├── SessionScheduler      # Dispatches by target/skill/priority
├── TargetRuntimeRegistry # Target runtime factory/manifest
├── SkillRuntimeRegistry  # Skill runtime factory/manifest
├── HealthMonitor         # Policy server / robot / simulator / session health monitoring
├── ResultWriter          # Unified writeback to SESSIONS.md / ENVIRONMENT.md / LESSONS.md
└── FailureEscalator      # retry / reset / cancel / notify / safety stop
```

#### Session State Machine

```
pending → claimed → running → succeeded / failed / timed_out
pending → rejected
running → cancelling → cancelled
```

---

### 3.3.6 Agent-Side APIs

#### Agent Loop

**Location**: `PhyAgentOS/agent/loop.py`

```python
class AgentLoop:
    def run(self, user_input: str) -> str:
        """Main loop: receive input → build context → call LLM → handle tools → return result"""
```

Workflow:
1. Build context from workspace files (ENVIRONMENT.md, EMBODIED.md, LESSONS.md)
2. Call LLM for planning and reasoning
3. Handle tool invocations (EmbodiedActionTool, SemanticNavigationTool, etc.)
4. Write actions to ACTION.md / SESSIONS.md
5. Manage conversation history

#### Critic Validation Framework

**Location**: `PhyAgentOS/agent/tools/embodied.py`

EmbodiedActionTool responsibilities:
- Resolve target `robot_id` in fleet mode
- Locate `EMBODIED.md`, `ENVIRONMENT.md`, `ACTION.md` for target robot
- Submit action draft, environment state, capability declaration to Critic
- Write to `ACTION.md` on validation pass
- Record to `LESSONS.md` on validation failure

New Critic also validates:
1. Whether target is available
2. Whether target supports the skill
3. Whether skill meets input preconditions
4. Whether session exceeds safety boundaries
5. Whether task should be assigned to sim or real
6. Whether fallback chain exists

#### Skill System

**Location**: `PhyAgentOS/agent/skills.py`

Each Skill is a directory containing `SKILL.md` (skill definition) and execution scripts. 13 built-in Skills:
`agent-mode`, `clawhub`, `cron`, `github`, `image`, `memory`, `pipergo2-demo`,
`rekep-robot-onboarding`, `robot-management-guideline`, `skill-creator`, `summarize`, `tmux`, `weather`.

#### CLI Entry Points

| Command | Description |
|---------|-------------|
| `paos onboard` | Initialize workspace, sync template files |
| `paos agent` | Start interactive Agent CLI |
| `paos agent -m "..."` | Single-turn message call |
| `paos gateway` | Start long-running gateway service |

---

### 3.3.7 Configuration Schema

**Location**: `PhyAgentOS/config/schema.py`

Pydantic configuration model core structure:

```python
class EmbodimentInstanceConfig(BaseModel):
    robot_id: str
    driver: str
    workspace: str

class EmbodimentsConfig(BaseModel):
    mode: Literal["single", "fleet"]
    shared_workspace: str | None = None
    instances: list[EmbodimentInstanceConfig] = []

class Config(BaseModel):
    agents: AgentsConfig
    providers: ProvidersConfig
    gateway: GatewayConfig | None
    tools: ToolsConfig | None
    embodiments: EmbodimentsConfig
```

---

### 3.3.8 File Protocol Conventions

#### ACTION.md Format

Watchdog extracts the first JSON code block from `ACTION.md`:

```json
{
  "action_type": "move_to",
  "parameters": {
    "x": 10,
    "y": 20,
    "z": 5
  },
  "status": "pending"
}
```

When developing custom tools or external plugins, you MUST maintain this convention, or the Watchdog cannot parse.

#### SESSIONS.md Format (New Protocol)

```json
{
  "session_id": "uuid",
  "goal": "pick up the red cube",
  "target": "simulation://default",
  "skill": "vla_pick",
  "params": {"object": "red_cube"},
  "status": "pending"
}
```

#### Action Validate-Dispatch-Execute Pipeline

```
1. Agent forms action intent
2. EmbodiedActionTool performs Critic validation
3. On pass: writes to ACTION.md / SESSIONS.md
4. Watchdog consumes and executes action
5. Results written back to ENVIRONMENT.md / LESSONS.md
```

When debugging, distinguish: action generation issue / Critic rejection / Watchdog execution failure / execution succeeded but state not written back.

---

## 3.4 Secondary Development Guide

### 3.4.1 Adding a New Driver

Minimum workflow for adding a built-in driver:

1. Create driver implementation file in `hal/drivers/`
2. Inherit `BaseDriver`, implement 4 abstract methods
3. Create corresponding Profile in `hal/profiles/`
4. Register in `hal/drivers/__init__.py` `DRIVER_REGISTRY`
5. Validate by starting directly: `hal/hal_watchdog.py --driver <name>`
6. Full-pipeline integration test with `paos agent`

#### Built-in Driver vs External Plugin

| Modify Main Repo | External Plugin |
|------------------|-----------------|
| Fix existing driver bugs | Heavy third-party SDK dependencies |
| Enhance built-in simulation | Vendor-private runtimes |
| Universal changes | Complex real-robot deployment logic |
| | Independent versioning and dependency management desired |

---

### 3.4.2 Adding a New Target

Adding a new scenario requires only implementing a `BaseRolloutTarget` subclass (~100 lines):

```python
class MyTarget(BaseRolloutTarget):
    def build(self) -> None:
        # Initialize environment

    def reset(self, session_ctx: dict) -> dict:
        # Reset and return initial observation
        return {"obs": ..., "info": ...}

    def observe(self) -> dict:
        # Return current observation
        return {"rgb": ..., "depth": ..., "joint": ...}

    def step(self, executable_action: dict) -> dict:
        # Execute one step
        return {"obs": ..., "reward": ..., "done": ..., "info": ...}

    def close(self) -> None:
        # Release resources

    def get_state(self) -> dict:
        # Return runtime state
        return {"status": ..., "position": ...}
```

**No need to understand**: Watchdog, Session state machine, file protocol, Critic — the Base layer handles all of that.

> **Reference implementation**: `runtime/targets/game/minecraft_target.py` (182 lines) is a clean `BaseLocalTarget` implementation. It has zero Minecraft protocol dependencies (no pyCraft), communicating only via HTTP to an external mineflayer bridge. Suitable as a reference template for game-type Targets.
>
> Deployment guides, usage details, and 9 troubleshooting entries are in the [Minecraft scenario docs](../../scenarios/game/minecraft/en/deployment.md).

---

### 3.4.3 Developing External Plugins

#### Plugin Registration Mechanism

**Location**: `hal/plugins.py`

1. Plugin repo provides `PhyAgentOS_plugin.toml` manifest
2. Deployment script clones or copies plugin repo to `~/.PhyAgentOS/plugins/repos/`
3. Main repo reads manifest and writes to local plugin registry
4. When built-in `DRIVER_REGISTRY` doesn't find target driver, dynamically resolves from external registry

#### Plugin Template Structure

```
my-plugin/
├── PhyAgentOS_plugin.toml    # Plugin manifest
├── requirements.txt          # Dependencies
├── driver.py                 # Driver implementation (extends BaseDriver)
├── profile.md                # Robot Profile
└── README.md                 # Usage instructions
```

#### Deployment Script Reference

```bash
python scripts/deploy_rekep_real_plugin.py \
  --repo-url https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin.git
```

---

### 3.4.4 Adding a New Skill

Each Skill is a directory containing a `SKILL.md` definition file and execution scripts:

```
PhyAgentOS/skills/my-skill/
├── SKILL.md      # Skill metadata and prompt
└── run.sh        # Execution entry point
```

**SKILL.md format**:
```markdown
# Skill Name
Description of what this skill does.

## Parameters
- param1: description
- param2: description

## Usage
...
```

---

### 3.4.5 Integrating a New Robot

#### Profile Writing Guidelines

A Profile should contain (a capability specification for Critic and Agent):
- Identity and type
- Sensor capabilities
- Supported action table
- Physical constraints (workspace, torque limits, etc.)
- Connection method
- Runtime protocol mapping

#### driver-config JSON Pass-Through Mechanism

`hal_watchdog.py` supports passing a JSON object via `--driver-config`, transparently forwarded to the target driver constructor:

```bash
python hal/hal_watchdog.py \
  --driver my_driver \
  --driver-config examples/my_driver_config.json
```

Benefits: avoids frequent Watchdog CLI changes, each driver defines its own init params, config examples are persisted in the repo.

---

### 3.4.6 Extending the Perception Pipeline

**Location**: `hal/perception/`

Perception pipeline layer structure:

```
service.py                 # Service orchestration entry point
  ├── geometry_pipeline.py # Geometric processing (point clouds, transforms)
  ├── segmentation_pipeline.py  # Semantic segmentation
  ├── fusion_pipeline.py   # Multi-source fusion → scene graph
  └── environment_writer.py     # Write perception results to ENVIRONMENT.md
```

**Development advice**: Clearly separate "perception processing" from "environment writeback". Don't cram all logic into the driver.

---

### 3.4.7 Extending the Navigation Module

**Location**: `hal/navigation/`

```
target_navigation_engine.py    # Core navigation engine, semantic goal resolution
  └── target_navigation_backend.py  # Navigation execution backend abstraction
        └── bridge.py          # Bridge between HAL and navigation backend
```

The most important thing in navigation extension is not just "making the robot move", but making state **visible, writable, and interpretable**.

---

### 3.4.8 ROS2 Adapter Development

**Location**: `hal/ros2/`

```
bridge.py          # ROS2 communication bridge
messages.py        # Message type definitions and conversions
adapters/          # Robot-specific ROS2 adapters
```

When integrating new ROS2 topics / sensors / control channels, prefer extending by adapter dimension rather than piling ad-hoc logic into a single driver.

---

## 3.5 Coding Style Standards

### Python

| Standard | Requirement |
|----------|-------------|
| Python version | ≥ 3.11 |
| Line length | Max 100 characters |
| Lint tool | ruff |
| Lint rules | E / F / I / N / W |
| Ignored rules | E501 (line length handled by ruff formatter) |
| Type annotations | Required on all public functions |
| Docstrings | Google-style docstrings |
| Import ordering | isort auto-sorted (stdlib → third-party → project internal) |

### Pydantic Schema Conventions

- All runtime data structures defined using Pydantic BaseModel
- Fields use explicit type annotations and default values
- Complex nested fields defined as separate models

### File Organization

- One clear responsibility per module
- Don't cram all logic into the driver
- Perception, navigation, ROS2 each have independent layers

---

## 3.6 Implementation Boundaries

### Strictly Forbidden Cross-Boundary Behavior

| Component | Must NOT Know |
|-----------|---------------|
| **RolloutTarget** | Policy inference, Skill logic, upper Agent |
| **SkillRuntime** | Target internal implementation details |
| **TargetAdapter** | Policy inference, Target internal state |
| **WatchdogSupervisor** | How to execute step specifics |
| **Base layer** | Any import from scenario modules |

### Design Guardrails

1. **Base layer must NOT import any scenario module**
2. **Each new scenario = ~100 lines of BaseRolloutTarget subclass**
3. **Three scenarios progress in parallel without blocking**
4. **Real-robot final safety adjudication MUST stay on the local control machine** (no final stop decisions on the cloud Agent side)

### Safety Boundary (Real-Robot Scenario)

```
Sensor → ObservationProvider → PolicyServer → ActionChunk
  → ChunkBuffer (local) → SoftBlend → SafetyGuard (local) → MotorCommand
```

Cloud Agent only generates intent-level session specs. Local Runtime layer executes and performs final safety checks.

---

## 3.7 Testing Standards

### Four-Layer Validation System

| Layer | Content | Command |
|-------|---------|---------|
| 1. Pure Python unit tests | Interfaces, config, registration, parsing logic | `pytest tests/test_hal_base_driver.py` |
| 2. Driver local smoke test | Start Watchdog directly | `python hal/hal_watchdog.py --driver <name>` |
| 3. Dry-run preflight | Pre-check real plugin or remote runtime | preflight + dry-run |
| 4. Agent full-pipeline integration | Agent → Critic → ACTION → Watchdog → ENVIRONMENT | `paos agent` + Watchdog |

### Key Test Files

| Test File | Coverage |
|-----------|----------|
| `tests/test_hal_external_plugins.py` | Plugin registration & external driver resolution |
| `tests/test_hal_base_driver.py` | Driver base contract |
| `tests/test_hal_watchdog_driver_config.py` | `driver-config` pass-through |
| `tests/test_go2_navigation_stack.py` | Go2 navigation stack |
| `tests/test_perception_service.py` | Perception service |
| `tests/test_commands.py` | CLI commands |
| `tests/test_fleet_watchdog.py` | Fleet Watchdog workflows |

### Minimum Test Commands

```bash
# Full suite
pytest tests/

# Single module
pytest tests/test_hal_external_plugins.py
```

### Real-Robot/Plugin Verification Sequence

```
preflight → dry-run → Watchdog direct connection validation → Agent full-pipeline validation
```

---

## 3.8 Contribution & Submission Rules

### PR Workflow

1. Fork the repo and create a feature branch
2. Write code + tests + documentation
3. Ensure `pytest tests/` all pass
4. Ensure `ruff check .` has no errors
5. Submit PR with clear description of changes and motivation

### Commit Conventions

- Use semantic commit messages: `feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`
- One commit, one thing
- Never commit secrets (`.env`, credentials, etc.)

### Documentation Layering

| Doc Layer | Target Audience | Change Trigger |
|-----------|----------------|----------------|
| README | Everyone | Major feature changes |
| Framework Introduction | Everyone | Architecture evolution, new features, demo updates |
| User Manual | Users | Command changes, config structure changes, new scenario support |
| Developer Manual | Developers | API changes, new modules, process changes |

### When to Split Out a Separate Doc

Split out when BOTH conditions are met:
- Beyond "quick reference" scope, needs background + deployment + troubleshooting + examples + FAQ
- Has a stable, specific audience (e.g., plugin authors, ROS2 developers, operators)

---

## 3.9 Appendix

### Module Path Quick Reference

| Function | Path |
|----------|------|
| BaseDriver | `hal/base_driver.py` |
| Watchdog | `hal/hal_watchdog.py` / `PhyAgentOS/runtime/watchdog/` |
| Built-in Drivers | `hal/drivers/` |
| Robot Profiles | `hal/profiles/` |
| Driver Config Examples | `examples/` |
| Agent Loop | `PhyAgentOS/agent/loop.py` |
| EmbodiedActionTool | `PhyAgentOS/agent/tools/embodied.py` |
| Semantic Navigation Tool | `PhyAgentOS/agent/tools/target_navigation.py` |
| Config Schema | `PhyAgentOS/config/schema.py` |
| External Plugins | `hal/plugins.py` |
| Perception Service | `hal/perception/service.py` |
| Navigation Engine | `hal/navigation/target_navigation_engine.py` |
| ROS2 Bridge | `hal/ros2/bridge.py` |
| Skill System | `PhyAgentOS/agent/skills.py` |
| CLI Entry | `PhyAgentOS/cli/commands.py` |
| Test Suite | `tests/` |

### Old Module → New Module Mapping (Runtime V2 Refactoring)

| Current Module | New Module | Treatment |
|---------------|------------|-----------|
| `hal/base_driver.py` | `runtime/targets/*` + `local_control/*` | Deprecated |
| `hal/drivers/*` | `runtime/targets/*` | Split and migrated |
| `hal/hal_watchdog.py` | `runtime/watchdog/supervisor.py` | Rewritten, retains role |
| `ACTION.md` | `SESSIONS.md` | Session schema replacement |
| `ROBOTS.md` | `TARGETS.md` | Extended to unified sim+real index |
| Built-in nav actions | `SemanticNavigationRuntime` | Elevated to SkillRuntime |
| ReKep grasp plugin | `ReKepRuntime` | Elevated to SkillRuntime |
| Simulation driver | `SimTarget` | Elevated to RolloutTarget |
| `ENVIRONMENT.md` | Continues as state bus | Preserved and extended |
| `EMBODIED.md` | Continues as target profile | Preserved and extended |
| `LESSONS.md` | Continues as failure experience base | Preserved and extended |

---

## Further Reading

- [Part 1: Framework Introduction](../01-framework-introduction.md) — Design philosophy, architecture, roadmap
- [Part 2: User Manual](../02-user-manual.md) — Quick start, scenario configuration, troubleshooting

> **External Plugin Reference**: The ReKep real-robot plugin [GitHub](https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin) is the best external plugin implementation reference.
