# PhyAgentOS API 开发者手册

> 面向二次开发者、硬件接入者、插件作者与维护者。覆盖 API 接口文档、二次开发流程、代码风格规范、实现边界与贡献规则。

---

## 目录

- [3.1 手册定位](#31-手册定位)
- [3.2 架构深度解析](#32-架构深度解析)
- [3.3 API 接口文档](#33-api-接口文档)
  - [3.3.1 BaseDriver 接口](#331-basedriver-接口)
  - [3.3.2 BaseRolloutTarget 接口](#332-baserollouttarget-接口)
  - [3.3.3 BaseSkillRuntime 接口](#333-baseskillruntime-接口)
  - [3.3.4 TargetAdapter 接口](#334-targetadapter-接口)
  - [3.3.5 WatchdogSupervisor 内部架构](#335-watchdogsupervisor-内部架构)
  - [3.3.6 Agent 侧 API](#336-agent-侧-api)
  - [3.3.7 配置 Schema](#337-配置-schema)
  - [3.3.8 文件协议约定](#338-文件协议约定)
- [3.4 二次开发指南](#34-二次开发指南)
  - [3.4.1 添加新驱动](#341-添加新驱动)
  - [3.4.2 添加新 Target](#342-添加新-target)
  - [3.4.3 开发外部插件](#343-开发外部插件)
  - [3.4.4 添加新 Skill](#344-添加新-skill)
  - [3.4.5 接入新机器人](#345-接入新机器人)
  - [3.4.6 扩展感知管线](#346-扩展感知管线)
  - [3.4.7 扩展导航模块](#347-扩展导航模块)
  - [3.4.8 ROS2 适配开发](#348-ros2-适配开发)
- [3.5 代码风格规范](#35-代码风格规范)
- [3.6 实现边界](#36-实现边界)
- [3.7 测试规范](#37-测试规范)
- [3.8 贡献与提交规则](#38-贡献与提交规则)
- [3.9 附录](#39-附录)

---

## 3.1 手册定位

### 适合谁

如果你的目标已经不是"把系统跑起来"，而是：
- 理解仓库内各模块分工
- 新增或修改内置驱动
- 基于 HAL 接入新机器人
- 开发独立插件仓库
- 接入感知、导航、ROS2 相关能力
- 为项目补测试、补文档

那么本文档是你的主要参考资料。

### 推荐阅读路径

| 目标 | 建议先读 |
|------|---------|
| 理解运行时通信 | [§3.2](#32-架构深度解析) → [§3.3.8](#338-文件协议约定) |
| 接一个新机器人 | [§3.4.1](#341-添加新驱动) → [§3.4.5](#345-接入新机器人) |
| 开发外部插件 | [§3.4.3](#343-开发外部插件) |
| 理解架构全貌 | [Part 1 §1.3](../01-framework-introduction.md#13-技术架构) → [§3.2](#32-架构深度解析) |

---

## 3.2 架构深度解析

### 3.2.1 核心设计：认知与执行解耦

PhyAgentOS 的核心价值是将认知层与执行层通过显式协议解耦。**很多"接口"本质上是文件协议与运行时约定，而不是 Python 函数签名。**

- **Track A（认知层）**：Planner / Critic / Tool / Memory
- **Track B（执行层）**：Watchdog / SessionRunner / SkillRuntime / Target
- **协议边界**：Markdown 文件承载共享状态，而非跨层 Python 调用

### 3.2.2 运行时文件是"真实状态面"

以下文件通常比类图更重要：

| 文件 | 逻辑含义 |
|------|---------|
| `TARGETS.md` | target registry 与 endpoint / adapter / contract |
| `SKILLRUNTIME.md` | 可执行 skill runtime 声明 |
| `SESSIONS.md` | 执行意图与结果真相 |
| `ENVIRONMENT.md` | 环境状态真相 |
| `EMBODIED.md` | 面向 Agent 的 target 能力描述 |
| `SKILLS.md` | 面向 Agent 的 skill 发现与加载规则 |
| `LESSONS.md` | 失败经验真相 |

**只看代码不看文件会误解系统行为。**

### 3.2.3 single 与 fleet 的开发含义

开发任何涉及具身动作、导航或连接状态的功能时，必须显式考虑两种运行语义：

- **single 模式**：一个工作区，所有状态文件在一处
- **fleet 模式**：共享工作区存放全局状态，per-robot 工作区存放机器人私有状态

### 3.2.4 模板、Profile 与运行时文件的区别

| 概念 | 位置 | 含义 |
|------|------|------|
| **模板（templates）** | `PhyAgentOS/templates/` | 定义文件结构与建议字段 |
| **Profile** | `hal/profiles/` | 某类机器人的静态能力声明 |
| **运行时文件** | workspace/ | 真正被 Agent、Watchdog 与 runtime writer 读写的状态面 |

简而言之：**模板定义结构，Profile 提供实例类型说明，运行时文件承载真实状态。**

---

## 3.3 API 接口文档

### 3.3.1 BaseDriver 接口

**位置**：`hal/base_driver.py`

所有硬件和仿真驱动必须继承 `BaseDriver`。

#### 必须实现的抽象方法

```python
class BaseDriver(ABC):
    def get_profile_path(self) -> str:
        """返回驱动的 EMBODIED.md Profile 路径"""

    def load_scene(self, scene: dict) -> None:
        """从场景字典初始化世界状态"""

    def execute_action(self, action_type: str, params: dict) -> str:
        """执行原子动作，返回结果字符串"""

    def get_scene(self) -> dict:
        """返回当前世界状态字典"""
```

#### 可选覆盖的方法

```python
def connect(self) -> None:           # 建立硬件连接
def disconnect(self) -> None:        # 关闭连接
def is_connected(self) -> bool:      # 检查连接状态
def health_check(self) -> bool:      # 轻量级健康检查
def get_runtime_state(self) -> dict: # 返回可选运行时状态（导航、连接等）
def close(self) -> None:             # 释放硬件资源
```

#### 驱动加载

驱动注册在 `hal/drivers/__init__.py` 中的 `DRIVER_REGISTRY`，通过 `load_driver(name, **kwargs)` 加载。

---

### 3.3.2 BaseRolloutTarget 接口

**位置**：`PhyAgentOS/runtime/targets/base.py`（新版）

三个场景唯一的接入点。WatchdogSupervisor 不需要知道 Target 是游戏、仿真还是真机。

```python
class BaseRolloutTarget(ABC):
    def build(self) -> None:
        """初始化环境（连接 SMAPI、启动仿真实例、建立硬件会话等）"""

    def reset(self, session_ctx: dict) -> dict:
        """重置到初始状态，返回初始观测字典"""

    def observe(self) -> dict:
        """获取当前观测（RGBD、关节、语音、游戏状态等）"""

    def step(self, executable_action: dict) -> dict:
        """执行一步动作，返回 obs / reward / done / info"""

    def close(self) -> None:
        """释放资源（断开连接、关闭仿真窗口等）"""

    def get_state(self) -> dict:
        """返回运行态字典，供 ENVIRONMENT.md 回写"""
```

#### 场景实现示例

```python
# 场景 1: 星露谷 Game Target
class StardewTarget(BaseRolloutTarget):
    def build(self): ...       # 连接 SMAPI mod (HTTP)
    def reset(self, ctx): ...  # 加载游戏日/season
    def observe(self): ...     # 返回：位置/时间/背包/NPC关系/作物状态
    def step(self, action): ...# 执行 move_to/interact/sleep
    def close(self): ...       # 断开 SMAPI 连接

# Game Target: Minecraft（已验证）
class MinecraftTarget(BaseLocalTarget):
    def build(self): ...       # HTTP GET /health → 验证 bridge 可达
    def reset(self, ctx): ...  # 初始观察（位置/背包/附近方块/实体）
    def observe(self): ...     # HTTP GET /state → 完整游戏快照
    def step(self, action): ...# HTTP POST /action → mineflayer 执行
    def close(self): ...       # 释放 HTTP 客户端

# 场景 2: 仿真 Target
class ManiSkillTarget(BaseRolloutTarget):
    def build(self): ...       # 初始化 ManiSkill 环境
    def observe(self): ...     # RGBD + proprioception + 语言指令
    def step(self, action): ...# 连续动作 → obs/reward/done/info

# 场景 3: 真机 Composite Target
class CompositeTarget(BaseRolloutTarget):  # Go2 + Franka
    def observe(self): ...     # RGBD + 力觉 + 关节 + 语音文本
    def step(self, action): ...# chunk 缓冲 + soft blend
```

---

### 3.3.3 BaseSkillRuntime 接口

**位置**：`PhyAgentOS/runtime/skillruntime/base.py`（新版）

```python
class BaseSkillRuntime(ABC):
    def start(self, session_ctx: dict, target: BaseRolloutTarget) -> None:
        """初始化 skill 执行上下文"""

    def tick(self, session_ctx: dict, target: BaseRolloutTarget) -> dict:
        """每个执行周期调用一次，返回状态字典"""

    def cancel(self, session_ctx: dict, reason: str) -> None:
        """中断执行"""

    def snapshot(self, session_ctx: dict) -> dict:
        """返回 skill 当前快照"""
```

#### Skill Runtime 抽象层级

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

**关键设计**：skill runtime 专注"怎么跑"，target 专注"怎么执行"，adapter 专注"怎么翻译"。三者职责清晰分离。

---

### 3.3.4 TargetAdapter 接口

**位置**：`PhyAgentOS/runtime/adapters/base.py`（新版）

```
TargetAdapter
├── SimAdapter (BuiltinSim / RoboCasa / LIBERO)
└── RealAdapter (Franka / Go2 / XLeRobot / UR5)
```

职责：
- 观测的 target-specific 差异处理（坐标系变换、传感器数据归一化）
- 动作的 target-specific 差异处理（归一化/反归一化、sticky gripper、chunk decode）
- `AdapterPlan` 自动编排适配步骤

---

### 3.3.5 WatchdogSupervisor 内部架构

**位置**：`PhyAgentOS/runtime/watchdog/supervisor.py`（新版）

```
WatchdogSupervisor
├── WorkspaceWatcher      # 监听 SESSIONS.md / TARGETS.md / ENVIRONMENT.md
├── SessionRegistry       # Session 生命周期管理（pending→claimed→running→succeeded/failed）
├── SessionScheduler      # 根据 target/skill/priority 分发
├── TargetRuntimeRegistry # Target runtime factory/manifest
├── SkillRuntimeRegistry  # Skill runtime factory/manifest
├── HealthMonitor         # policy server / robot / simulator / session 健康监控
├── ResultWriter          # 统一写回 SESSIONS.md / ENVIRONMENT.md / LESSONS.md
└── FailureEscalator      # retry / reset / cancel / notify / safety stop
```

#### Session 状态机

```
pending → claimed → running → succeeded / failed / timed_out
pending → rejected
running → cancelling → cancelled
```

---

### 3.3.6 Agent 侧 API

#### Agent Loop

**位置**：`PhyAgentOS/agent/loop.py`

```python
class AgentLoop:
    def run(self, user_input: str) -> str:
        """主循环：接收输入 → 构建上下文 → 调用 LLM → 处理工具 → 返回结果"""
```

工作流：
1. 从 bootstrap 文件（`AGENTS.md`、`SOUL.md`、`USER.md`、`TOOLS.md`、`SKILLS.md`）以及 `ENVIRONMENT.md`、`EMBODIED.md`、`LESSONS.md` 等状态文件构建上下文
2. 调用 LLM 进行规划和推理
3. 处理工具调用与 skill 引导的工作流
4. 需要 runtime 执行时，读取 `TARGETS.md` / `SKILLRUNTIME.md` 并将任务追加到 `SESSIONS.md`
5. 管理对话历史

#### Runtime Session 校验

**位置**：`PhyAgentOS/runtime/preflight/`

Runtime 执行前会解析 session 中的 `target_ref` 与 `skillruntime_ref`，检查 target 是否支持对应 skill runtime，校验 sensor、perception、runtime contract 与 adapter/bridge 兼容性，不合法的 session 会在 target 或 policy runtime 启动前被拒绝。

#### Skill 系统

**位置**：`PhyAgentOS/agent/skills.py`

每个 Skill 包含 `SKILL.md`（Skill 定义）和执行脚本。13 个内置 Skill：
`agent-mode`、`clawhub`、`cron`、`github`、`image`、`memory`、`pipergo2-demo`、
`rekep-robot-onboarding`、`robot-management-guideline`、`skill-creator`、`summarize`、`tmux`、`weather`。

#### CLI 入口

| 命令 | 说明 |
|------|------|
| `paos onboard` | 初始化工作区，同步模板文件 |
| `paos agent` | 启动交互式 Agent CLI |
| `paos agent -m "..."` | 单轮消息调用 |
| `paos gateway` | 启动长期在线网关服务 |

---

### 3.3.7 配置 Schema

**位置**：`PhyAgentOS/config/schema.py`

Pydantic 配置模型核心结构：

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

### 3.3.8 文件协议约定

#### SESSIONS.md 格式

```yaml
version: runtime_sessions_v1
sessions:
  - session_id: sess_example
    target_ref: target://dummy_sim
    skillruntime_ref: skillruntime://openpi_sim_vla
    task_description: run a smoke test
    status: pending
    priority: normal
```

#### Session 校验-分发-执行链路

```
1. Agent 形成任务意图
2. Agent 从 TARGETS.md / SKILLRUNTIME.md 解析 target 与 skill runtime
3. Agent 向 SESSIONS.md 追加 pending session
4. WatchdogSupervisor claim session，执行 preflight
5. SessionRunner 运行 target/skill runtime，结果回写到 SESSIONS.md、ENVIRONMENT.md、LOG.md 与 artifacts
```

排查时要区分：任务生成有问题 / target 或 skillruntime 不匹配 / preflight 拒绝 / Watchdog 执行失败 / 执行成功但环境未回写。

---

## 3.4 二次开发指南

### 3.4.1 添加新驱动

添加内置 driver 的最小流程：

1. 在 `hal/drivers/` 中新增驱动实现文件
2. 继承 `BaseDriver`，实现 4 个抽象方法
3. 在 `hal/profiles/` 中新增对应 Profile
4. 在 `hal/drivers/__init__.py` 的 `DRIVER_REGISTRY` 中注册
5. 用 `hal/hal_watchdog.py --driver <name>` 直接启动验证
6. 用 `paos agent` 做全链路联调

#### 内置 driver vs 外部插件

| 适合直接改主仓库 | 更适合做外部插件 |
|------------------|-----------------|
| 修复现有驱动 bug | 依赖较重的第三方 SDK |
| 增强内置仿真 | 厂商私有运行时 |
| 普适性改动 | 真实机器人部署逻辑复杂 |
| | 希望独立发版、独立维护依赖 |

---

### 3.4.2 添加新 Target

引入新场景只需实现 `BaseRolloutTarget` 子类（约 100 行）：

```python
class MyTarget(BaseRolloutTarget):
    def build(self) -> None:
        # 初始化环境

    def reset(self, session_ctx: dict) -> dict:
        # 重置并返回初始观测
        return {"obs": ..., "info": ...}

    def observe(self) -> dict:
        # 返回当前观测
        return {"rgb": ..., "depth": ..., "joint": ...}

    def step(self, executable_action: dict) -> dict:
        # 执行一步
        return {"obs": ..., "reward": ..., "done": ..., "info": ...}

    def close(self) -> None:
        # 释放资源

    def get_state(self) -> dict:
        # 返回运行态
        return {"status": ..., "position": ...}
```

**不需要懂**: Watchdog、Session 状态机、文件协议、Critic——Base 层已处理。

> **参考实现**：`runtime/targets/game/minecraft_target.py`（182 行）是一个干净的 `BaseLocalTarget` 实现。它完全不依赖 Minecraft 协议库（无 pyCraft），仅通过 HTTP 与外部 mineflayer bridge 通信。适合作为 game 类型 Target 的参考模板。
>
> 部署指南、使用细节与 9 条踩坑记录见 [Minecraft scenario 文档](../../scenarios/game/minecraft/zh/deployment.md)。

---

### 3.4.3 开发外部插件

#### 插件注册机制

**位置**：`hal/plugins.py`

1. 插件仓库提供 `PhyAgentOS_plugin.toml` 描述文件
2. 部署脚本 clone 或复制插件仓库到 `~/.PhyAgentOS/plugins/repos/`
3. 主仓库读取 manifest 并写入本地插件 registry
4. 当内置 `DRIVER_REGISTRY` 找不到目标 driver 时，从外部 registry 动态解析

#### 插件模板结构

```
my-plugin/
├── PhyAgentOS_plugin.toml    # 插件描述文件
├── requirements.txt          # 依赖
├── driver.py                 # 驱动实现（继承 BaseDriver）
├── profile.md                # 机器人 Profile
└── README.md                 # 使用说明
```

#### 部署脚本参考

```bash
python scripts/deploy_rekep_real_plugin.py \
  --repo-url https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin.git
```

---

### 3.4.4 添加新 Skill

每个 Skill 是一个目录，包含 `SKILL.md` 定义文件和执行脚本：

```
PhyAgentOS/skills/my-skill/
├── SKILL.md      # Skill 元数据与 Prompt
└── run.sh        # 执行入口
```

**SKILL.md 格式**：
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

### 3.4.5 接入新机器人

#### Profile 编写规范

Profile 应包含（给 Critic 和 Agent 看的能力说明书）：
- 身份与类型
- 传感器能力
- 支持动作表
- 物理约束（工作空间、力矩限制等）
- 连接方式
- 运行时协议映射

#### driver-config JSON 透传机制

`hal_watchdog.py` 支持通过 `--driver-config` 传入一个 JSON 对象，原样透传给目标 driver 构造器：

```bash
python hal/hal_watchdog.py \
  --driver my_driver \
  --driver-config examples/my_driver_config.json
```

好处：避免频繁改 Watchdog CLI、保持每个 driver 自己定义初始化参数、配置示例以文件形式沉淀在仓库中。

---

### 3.4.6 扩展感知管线

**位置**：`hal/perception/`

感知管线分层结构：

```
service.py                 # 服务化编排入口
  ├── geometry_pipeline.py # 几何处理（点云、变换）
  ├── segmentation_pipeline.py  # 语义分割
  ├── fusion_pipeline.py   # 多源融合 → 场景图
  └── environment_writer.py     # 将感知结果写入 ENVIRONMENT.md
```

**开发建议**：把"感知处理"和"环境落盘"明确分层，不要把逻辑塞进 driver。

---

### 3.4.7 扩展导航模块

**位置**：`hal/navigation/`

```
target_navigation_engine.py    # 核心导航引擎，语义目标解析
  └── target_navigation_backend.py  # 导航执行后端抽象
        └── bridge.py          # HAL 与导航后端桥接
```

导航能力扩展最重要的不是"让机器人动起来"，而是让**状态可见、可回写、可解释**。

---

### 3.4.8 ROS2 适配开发

**位置**：`hal/ros2/`

```
bridge.py          # ROS2 通信桥接
messages.py        # 消息类型定义与转换
adapters/          # 机器人专用 ROS2 适配器
```

接入新 ROS2 topic / sensor / control 通道时，优先按 adapter 维度扩展，不要在单一 driver 内部堆砌临时逻辑。

---

## 3.5 代码风格规范

### Python

| 规范项 | 要求 |
|--------|------|
| Python 版本 | ≥ 3.11 |
| 行长度 | 最大 100 字符 |
| Lint 工具 | ruff |
| Lint 规则 | E / F / I / N / W |
| 忽略规则 | E501（行长度由 ruff formatter 处理） |
| 类型注解 | 所有公开函数必须添加类型注解 |
| 文档字符串 | 使用 Google 风格 docstring |
| 导入顺序 | isort 自动排序（标准库 → 第三方 → 项目内部） |

### Pydantic Schema 惯例

- 所有运行时数据结构使用 Pydantic BaseModel 定义
- 字段使用明确的类型注解和 default 值
- 复杂嵌套字段单独定义 model

### 文件组织

- 每个模块一个明确职责
- 不要把所有逻辑塞进 driver
- 感知、导航、ROS2 各自独立分层

---

## 3.6 实现边界

### 绝对禁止的跨界行为

| 组件 | 绝不能知道 |
|------|-----------|
| **RolloutTarget** | Policy 推理、Skill 逻辑、上层 Agent |
| **SkillRuntime** | Target 内部实现细节 |
| **TargetAdapter** | Policy 推理、Target 内部状态 |
| **WatchdogSupervisor** | 具体怎么执行 step |
| **Base 层** | 任何场景模块的 import |

### 设计护栏

1. **Base 层不 import 任何场景模块**
2. **每新增场景 = ~100 行 BaseRolloutTarget 子类**
3. **三个场景并行不阻塞**
4. **真实机器人最终安全裁决必须留在本地控制机**（不在云端 Agent 侧做最终 stop 决定）

### 安全边界（真机场景）

```
Sensor → ObservationProvider → PolicyServer → ActionChunk
  → ChunkBuffer (本地) → SoftBlend → SafetyGuard (本地) → MotorCommand
```

云端 Agent 只生成意图层 session spec，本地 Runtime 层执行并做最终 safety check。

---

## 3.7 测试规范

### 四层验证体系

| 层级 | 内容 | 命令 |
|------|------|------|
| 1. 纯 Python 单测 | 接口、配置、注册、解析逻辑 | `pytest tests/` |
| 2. Runtime contract/preflight | target/skill/adapter/bridge 兼容性 | runtime protocol tests |
| 3. 远程服务验收 | 真实 target/policy server 连接 | LIBERO TargetWS + pi0.5 policy server |
| 4. Agent 全链路联调 | Agent → SESSIONS → WatchdogSupervisor → SessionRunner → artifacts/ENVIRONMENT | `paos agent` |

### 关键测试文件

| 测试文件 | 覆盖主题 |
|---------|---------|
| `tests/runtime/test_runtime_protocol_alignment.py` | runtime 协议、adapter/bridge 注册 |
| `tests/runtime/test_supervisor_single_session.py` | WatchdogSupervisor session 状态流 |
| `tests/runtime/test_libero_remote_target.py` | LIBERO target proxy / adapter / preflight |
| `tests/runtime/test_openpi_adapter_schema.py` | OpenPI policy adapter schema |
| `tests/runtime/test_lerobot_pi0_server.py` | pi0 / pi0.5 policy loader |
| `tests/test_commands.py` | CLI 命令 |

### 最小测试命令

```bash
# 全量
pytest tests/

# 单模块
pytest tests/test_hal_external_plugins.py
```

### 真机/插件验证顺序

```
protocol 单测 → preflight → 远程 target/policy server 验收 → Agent 全链路验证
```

---

## 3.8 贡献与提交规则

### PR 流程

1. Fork 仓库并创建 feature 分支
2. 编写代码 + 测试 + 文档
3. 确保 `pytest tests/` 全部通过
4. 确保 `ruff check .` 无错误
5. 提交 PR，描述清楚改动内容和动机

### Commit 规范

- 使用语义化提交信息：`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`
- 一个 commit 做一件事
- 不要在 commit 中包含 secrets（`.env`、credentials 等）

### 文档维护分层

| 文档层 | 目标读者 | 变更触发条件 |
|--------|---------|-------------|
| README | 所有人 | 重大特性变更 |
| 框架介绍 | 所有人 | 架构演进、新特性、Demo 更新 |
| 用户手册 | 使用者 | 命令变更、配置结构变化、新场景支持 |
| 开发者手册 | 开发者 | API 变更、新模块、流程变化 |

### 何时拆出独立文档

同时满足以下两个条件应拆出独立文档：
- 超过"快速说明"范围，需要背景+部署+排障+示例+FAQ
- 有自己稳定的读者群（如插件作者、ROS2 开发者、运维人员）

---

## 3.9 附录

### 模块路径速查表

| 功能 | 路径 |
|------|------|
| Runtime Watchdog | `PhyAgentOS/runtime/watchdog/` |
| Session Runner | `PhyAgentOS/runtime/sessions/` |
| Target Runtime | `PhyAgentOS/runtime/targets/` |
| LIBERO TargetWS | `PhyAgentOS/runtime/targets/remote/libero/` |
| Skill Runtime | `PhyAgentOS/runtime/skillruntime/` |
| Target/Policy Adapter | `PhyAgentOS/runtime/adapters/` |
| OpenPI Policy Client/Server | `PhyAgentOS/runtime/policy/openpi/` |
| Agent Loop | `PhyAgentOS/agent/loop.py` |
| Agent Context | `PhyAgentOS/agent/context.py` |
| Agent Skill 系统 | `PhyAgentOS/agent/skills.py` |
| 配置 Schema | `PhyAgentOS/config/schema.py` |
| CLI 入口 | `PhyAgentOS/cli/commands.py` |
| 测试套件 | `tests/` |

---

## 后续阅读

- [Part 1: 框架介绍](../01-framework-introduction.md) — 设计理念、架构、路线图
- [Part 2: 用户手册](../02-user-manual.md) — 快速开始、场景配置、排障指南

> **外部插件参考**：ReKep 真机插件 [GitHub](https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin) 是最佳的外部插件实现参考。
