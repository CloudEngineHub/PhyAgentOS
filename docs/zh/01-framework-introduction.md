# PhyAgentOS 框架介绍

> 面向所有人的项目概述：设计理念、技术架构、当前进展、路线图、TODO 清单与 Demo 展示。

---

## 目录

- [1.1 项目概述](#11-项目概述)
- [1.2 设计理念](#12-设计理念)
- [1.3 技术架构](#13-技术架构)
- [1.4 核心特性](#14-核心特性)
- [1.5 当前进展](#15-当前进展)
- [1.6 架构演进路线](#16-架构演进路线)
- [1.7 未来开发方向](#17-未来开发方向)
- [1.8 具体 TODO 清单](#18-具体-todo-清单)
- [1.9 Demo 展示](#19-demo-展示)
- [1.10 项目结构](#110-项目结构)

---

## 1.1 项目概述

**PhyAgentOS**（Physical Agent Operating System，物理智能体操作系统）是一个基于 Agentic 工作流的自进化具身智能框架。由**中山大学 HCP 实验室**与**鹏城实验室**联合开发，基于 [nanobot](https://github.com/HKUDS/nanobot) 轻量级 Agent 框架构建。

### 核心价值

传统"大模型直连硬件"方案高度耦合——换一个机器人就要重写整个执行链路。PhyAgentOS 通过 **认知-物理解耦** 彻底改变了这一点：

- **一套代码，任意硬件**：新增机器人只需实现一个 Target Adapter（约 100 行），调度层零改动
- **三道安全防线**：Critic 校验 → Strict Preflight → Target 端 SafetyGuard，真机场景不可绕过
- **全程可审计**：状态、动作、感知结果以 Markdown + YAML 落盘，每一步可追溯复现
- **零摩擦迁移**：同一套 Session 协议在仿真、真机两类 Target 上无差别运行

### 关键数据

| 指标 | 数值 |
|------|------|
| 框架版本 | v0.2.1 |
| Python 要求 | ≥ 3.11 |
| License | MIT |
| HAL 驱动 | 10+ |
| 机器人 Profile | 9 个 |
| Channel 集成 | 14 个 |
| 内置 Skill | 13 个 |
| 测试文件 | 49 个 |

### 关联资源

- **GitHub**: [https://github.com/PhyAgentOS/PhyAgentOS](https://github.com/PhyAgentOS/PhyAgentOS)
- **项目网站**: [https://phy-agent-os.net/](https://phy-agent-os.net/)
- **ReKep 真机插件**: [https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin](https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin)
- **Unitree G1 语音插件**: [https://github.com/shawnmsw28/PhyAgentOS-unitree-g1-voice-plugin](https://github.com/shawnmsw28/PhyAgentOS-unitree-g1-voice-plugin)

---

## 1.2 设计理念

### 1.2.1 万物皆 Markdown（State-as-a-File）

PhyAgentOS 将一切运行时状态以 Markdown 文件形式暴露在本地工作区中。Track A（大脑）和 Track B（执行层）之间不通过 Python 函数调用通信，而是通过读写共享的 Markdown 文件交换信息。

```
Track A (Agent)          工作区文件           Track B (Runtime)
    │                                            │
    ├── 读取 ENVIRONMENT.md ─────────────→ 写回状态
    │                                            │
    ├── 写入 SESSIONS.md ─────────────────→ 消费执行
    │                                            │
    ├── 读取 LESSONS.md ←────────────────── 回写经验
```

这带来了三个关键收益：
- **彻底解耦**：Agent 和 Runtime 可以是独立进程、独立机器、独立语言
- **极度透明**：任何时候都可以打开 Markdown 文件查看当前系统状态
- **天然可审计**：所有历史状态以文件形式保存，可追溯、可复现

### 1.2.2 认知-物理解耦（Dual-Track）

系统分为两条完全独立的轨道：

| 轨道 | 职责 | 入口 |
|------|------|------|
| **Track A（认知层）** | 理解用户意图、规划动作、校验安全、管理记忆 | `paos agent` / `paos gateway` |
| **Track B（执行层）** | session 级执行监督、target/policy 调用、artifact 与环境状态写回 | 随 `paos agent` / `paos gateway` 自动启动 |

两轨道之间通过文件协议边界严格隔离。Track A 不知道电机型号，Track B 不知道 LLM Prompt。

### 1.2.3 Session-Centered Runtime

新架构将硬件抽象从"驱动中心"升级为"会话中心"：

- **旧模型（Driver-Centered）**：observe / execute / profile / safety 耦合在单个 Driver 类中
- **新模型（Session-Centered）**：RolloutTarget（负责执行对象）+ SkillRuntime（负责执行策略）+ TargetAdapter（负责数据变换）三段解耦

同一套 Session 协议可以在 debug / simulation / real_robot 三类 Target 上无差别运行。

### 1.2.4 双场景互补

两个并行场景共用 Base Runtime 内核，各自独立演进：

- **Sim（MuJoCo + ManiSkill）**：Benchmark 评测 + 批量经验挖掘
- **Real（移动抓取 + 语音）**：真实交互数据 → 改善 Sim 仿真保真度

---

## 1.3 技术架构

### 1.3.1 整体架构

```
                    ┌─────────────────────────────┐
                    │     认知层（Track A）         │
                    │  Planner / Critic / Memory   │
                    │     → 写 SESSIONS.md         │
                    └──────────────┬──────────────┘
                                   │ 文件协议边界
                    ┌──────────────┴──────────────┐
                    │     Base Runtime（共用）     │
                    │  WatchdogSupervisor          │
                    │  SessionRegistry             │
                    │  LESSONS.md 经验库           │
                    │  Critic 校验框架              │
                    └──────┬──────┬──────┬────────┘
                           │      │      │
                           │      │      │
                           ▼      ▼      ▼ 
               ┌──────────────┐ ┌──────────────┐
               │ 场景 1: Sim  │ │ 场景 2: Real │
               │ MuJoCo+      │ │ 移动抓取+    │
               │ ManiSkill    │ │ 语音交互     │
               │ 自进化        │ │ 活人感       │
               └──────────────┘ └──────────────┘
```

### 1.3.2 Runtime 执行链路

```
WatchdogSupervisor
  → SessionScheduler（读取 SESSIONS.md）
    → SessionRunner（绑定 Target + Skill）
      → SkillRuntime（执行策略循环）
        → TargetSessionHandle（驱动 Target.step()）
          → 写回 ENVIRONMENT.md / LESSONS.md
```

### 1.3.3 三段解耦：Adapter + Bridge

```
Agent 产生动作意图
  → TargetAdapter（将意图翻译为目标可执行动作）
    → PolicyAdapter（将观测翻译为策略可消费格式）
      → ActionBridge（桥接策略输出到目标输入）
```

`AdapterPlan` 自动编排适配步骤，消灭 target × skill 的组合爆炸问题。

### 1.3.4 核心接口

三个场景唯一的接入点是 `BaseRolloutTarget`：

```python
class BaseRolloutTarget(ABC):
    def build(self) -> None: ...          # 初始化环境
    def reset(self, session_ctx: dict) -> dict: ...  # 重置→返回初始观测
    def observe(self) -> dict: ...        # 获取当前观测
    def step(self, action) -> dict: ...   # 执行一步
    def close(self) -> None: ...          # 释放资源
    def get_state(self) -> dict: ...      # 运行态（供 ENVIRONMENT.md 回写）
```

WatchdogSupervisor 不需要知道 Target 是仿真还是真机。

### 1.3.5 解耦边界

| 组件 | 可以知道 | 绝不能知道 |
|------|---------|-----------|
| **RolloutTarget** | 自己怎么 build/reset/step | Policy 推理、Skill 逻辑、上层 Agent |
| **SkillRuntime** | 怎么调用 target 和 policy_client | target 内部实现 |
| **TargetAdapter** | 怎么做数据变换 | Policy 推理、target 内部状态 |
| **WatchdogSupervisor** | 怎么管理状态机、路由 | 具体怎么执行 step |

---

## 1.4 核心特性

| 特性 | 说明 |
|------|------|
| **Session-Centered Runtime** | `WatchdogSupervisor` → `SessionRunner` → `SkillRuntime` → `TargetSessionHandle` 执行链路 |
| **Target-Configured** | `debug` / `simulation` / `real_robot` 三类 Target，`TARGETS.md` 统一注册 |
| **Adapter + Bridge** | `TargetAdapter` + `PolicyAdapter` + `ActionBridge` 三段解耦，自动编排 |
| **双轨 Skill Runtime** | `PolicySkillRuntime` 维护策略闭环 + `BuiltinSkillRuntime` 管理 Agent 交互闭环 |
| **Strict Preflight** | 10 项前置校验（target / sensor / perception / contract / tool），不合格直接拒绝 |
| **文件协议矩阵** | `TARGETS.md` · `SKILLRUNTIME.md` · `SESSIONS.md` · `ENVIRONMENT.md` · `LESSONS.md` |
| **多层安全** | Critic 校验 → Preflight 契约检查 → Target 端 SafetyGuard → Operator Override |
| **Fleet 模式** | 多机器人协同，shared + per-robot 工作区，优先级串行调度 |
| **感知插件体系** | `SensorConfig` / `PerceptionConfig` YAML + `EnvironmentWriter` 可审计写回 |
| **外部插件机制** | 通过 `PhyAgentOS_plugin.toml` 动态加载第三方驱动，无需修改核心代码 |

---

## 1.5 当前进展

### 版本历程

| 版本 | 日期 | 里程碑 |
|:-----|:-----|:-------|
| v0.1.0 | 2026-04-29 | Hackathon 基线：插件化 HAL，ReKep / SAM3 真机抓取与 VLN 全链路 |
| v0.1.1 | 2026-05-18 | Session-Centered Runtime MVP：`DummySimTarget` + `DummyAdapter` + `DummyClient` 串行链路 |
| v0.1.2 | 2026-05-20 | 感知插件体系：`SensorConfig` / `PerceptionConfig` YAML + `EnvironmentWriter` 可审计写回 |
| v0.1.3 | 2026-05-25 | `PolicySkillRuntime` / `BuiltinSkillRuntime` 边界严格分离 |
| v0.2.1 | 2026-05-29 | LIBERO benchmark 远程 target server 就绪 |

### 已达成能力

- 10+ HAL 驱动实现（仿真、Franka、Go2、XLeRobot、PIPER+Go2 复合等）
- 9 个机器人 Profile（simulation、franka、go2_edu、xlerobot 等）
- 14 个 Channel 集成（Telegram、Discord、Slack、飞书、钉钉等）
- 13 个内置 Skill（agent-mode、clawhub、cron、github、image 等）
- 内置仿真支持（PyBullet 物理仿真 + Isaac Sim 高保真仿真）
- Fleet 多机器人协同模式
- 感知管线（GeometryPipeline + SegmentationPipeline + FusionPipeline）
- 语义导航（SemanticNavigationTool，语义目标 → 物理坐标）
- 外部插件动态加载机制

---

## 1.6 架构演进路线

### 当前架构（Session-Centered Runtime）

当前 Track B 以 session 为中心：`WatchdogSupervisor` 监督 session 状态流，`SessionRunner` 负责 target lifecycle，`TargetSessionHandle` 是 policy/builtin skill 访问 target 的唯一执行面。Track A 与 Track B 通过 `TARGETS.md`、`SKILLRUNTIME.md`、`SESSIONS.md`、`ENVIRONMENT.md` 等文件协议通信。

### Legacy HAL 兼容

旧版 Driver-Centered HAL 仍保留给部分历史 driver 和真机插件流程。当前 runtime 的正式执行入口已经迁移到 session schema：

| 旧模块 | 新模块 | 说明 |
|--------|--------|------|
| `BaseDriver` | `RolloutTarget` + `SkillRuntime` + `TargetAdapter` | 拆分为三个一级对象 |
| `hal_watchdog.py` | `WatchdogSupervisor` | 从动作轮询器升级为执行会话监督器 |
| 单动作队列 | `SESSIONS.md` | Session schema 是当前执行队列 |
| 机器人专用索引 | `TARGETS.md` | 统一 sim / real target registry |
| 导航/ReKep 作为驱动内功能 | `SkillRuntime`（BuiltinAlgorithmSkillRuntime） | 提升为一级 skill runtime |
| 仿真驱动 | `SimTarget` | 提升为一级 rollout target |

### 开发顺序：Base 先行，三场景并行

```
Phase 0: Base MVP（1-2 周）
  → Schema + State I/O + Watchdog + Dummy 闭环

Phase 1: 双场景并行（各 1-2 周，互不阻塞）
  ├── 场景 1: MuJoCo + ManiSkill 仿真
  └── 场景 2: 真机移动抓取 + 语音

Phase 2: 深度演进
  → Policy Server / LIBERO / RoboCasa / Hybrid Skill
```

> **设计护栏**：Base 层不 import 任何场景模块；每新增一个场景 = ~100 行 `BaseRolloutTarget` 子类；三个场景并行不阻塞。

---

## 1.7 未来开发方向

### 路线图阶段

| 阶段 | 聚焦 | 关键目标 |
|------|------|---------|
| **Phase 1**（当前） | 桌面闭环与 Markdown 协议 | 单机器人开发闭环，Markdown 协议通信 |
| **Phase 2** | 多本体协同与多模态记忆 | 多异构机器人协调、丰富记忆体系 |
| **Phase 3** | 约束求解与高阶异构协同 | 复杂约束满足、高级编排 |

### 短期重点（1-2 月）

1. **Base Runtime 完型**
   - Session 状态机健全：pending → claimed → running → succeeded / failed / timed_out
   - Goal Graph + Session Compiler
   - Fallback chain 机制

2. **Perception 深化**
   - 相机/LiDAR 接入标准化
   - 分割模型依赖管理
   - 场景图构建与写回协议完善

### 中期方向（3-6 月）

- **场景 2：MuJoCo + ManiSkill 仿真**（原场景 1B）
  - ManiSkillTarget 实现
  - BenchmarkHarness 自动化评测
  - 自进化经验闭环（LESSONS.md 自动积累）

- **场景 3：真机移动抓取 + 语音**（原场景 1C）
  - CompositeTarget 多机器人组合
  - SafetyGuard 本地安全裁决
  - Action Chunk 缓冲机制（chunk_size=8, 软融合）

- **Policy Server 标准化**
  - WebSocket + msgpack 通信协议
  - Policy Backend 统一抽象
  - 仿真/真机统一 client API

### 长期愿景

1. **任意硬件**：插件架构支持任何 Python 可控设备
2. **任意任务**：从简单抓取到长程操作
3. **任意规模**：从桌面机械臂到工业 Fleet
4. **自进化**：LESSONS.md + SKILLS.md 持续改进闭环
5. **安全透明**：Markdown 协议使所有状态可检查
6. **开放生态**：社区插件、benchmark、集成

---

## 1.8 具体 TODO 清单

### Base Runtime（Phase 0）

- [ ] Pydantic Session Schema 定义（session_id, goal, target, skill, params, status）
- [ ] State I/O 层：SESSIONS.md / TARGETS.md / ENVIRONMENT.md 读写工具
- [ ] WatchdogSupervisor 核心状态机（pending → claimed → running → succeeded/failed）
- [ ] SessionRegistry 注册表与生命周期管理
- [ ] HealthMonitor（policy server / robot / simulator / session 健康监控）
- [ ] ResultWriter 统一回写模块
- [ ] FailureEscalator（retry / reset / cancel / notify / safety stop）
- [ ] DummySimTarget + DummyAdapter + DummyClient 闭环验收

### 场景 1：MuJoCo + ManiSkill 仿真（Phase 1A）

- [ ] ManiSkillTarget 实现（build / observe / step, RGBD + proprioception）
- [ ] BenchmarkHarness 评测框架（run_benchmark → BenchmarkResult）
- [ ] 批量 rollout 并行执行
- [ ] 自动 LESSONS.md 经验积累
- [ ] Benchmark score 追踪与可视化

### 场景 2：真机移动抓取 + 语音（Phase 1B）

- [ ] CompositeTarget 接口定义（多机器人组合）
- [ ] SafetyGuard 本地安全裁决器
- [ ] Action Chunk 缓冲与 soft blend
- [ ] VoiceChannel 接口（初期只留接口）
- [ ] 与 Go2 + Franka 真机 dry-run 验证

### 后续深度演进

- [ ] OpenPI Policy Server 接入
- [ ] LIBERO / RoboCasa benchmark 集成
- [ ] Goal Graph + Session Compiler
- [ ] Hybrid Skill（Nav → VLA → ReKep 混合链路）
- [ ] 小智 ESP32 IoT 设备接入
- [ ] 幻尔系列教育机器人驱动
- [ ] 跨机器人经验共享（Fleet 间 LESSONS.md 共享）

---

## 1.9 Demo 展示

### 已验证的演示场景

| 演示 | 机器人 | 能力 |
|------|--------|------|
| 一键部署 | AgileX PIPER | 无代码机械臂部署 |
| XLeRobot 双臂 | XLeRobot | 底盘移动 + 双臂运动 |
| SAM3 语义抓取 | AgileX PIPER | 自然语言驱动语义抓取 |
| ReKep 约束抓取 | Dobot Nova 2 | 自然语言驱动约束抓取 |
| Franka 问答+抓取 | Franka Research 3 | 实时对话 + NL 驱动抓取 |
| Go2 语义导航 | Unitree Go2 | 语义目标导航（"去门口巡检"） |
| Isaac Sim 复合操作 | PIPER + Go2 | 无代码 Isaac Sim 环境操控 |

### 支持设备一览

| 类型 | 型号 | 状态 | 备注 |
|------|------|------|------|
| 桌面机械臂 | 松灵 PIPER | 🟢 已验证 | ReKep & SAM3 全链路 |
| 复合协作 | PIPER + Unitree Go2 | 🟡 部分支持 | locomotion 适配中 |
| 桌面机械臂 | 越疆 Dobot Nova 2 | 🟢 已验证 | ReKep 部署已验证 |
| 四足机器人 | Unitree Go2 | 🟡 部分支持 | 移动 + 语义导航 |
| 双臂控制 | XLeRobot | 🟢 已验证 | 双臂抓取已实现 |
| IoT 设备 | 小智 ESP32 | 🟡 部分支持 | 语音对话交互 |
| 工业机器人 | Franka Research 3 | 🟢 已验证 | 视觉推理 + 抓取 |
| 教育机器人 | 幻尔系列 | 🔴 未适配 | 待开发驱动插件 |
| 通用环境 | 内置仿真器 | 🟢 已验证 | 基于磁盘映射的轻量仿真 |

### 启动示例

**本地 Agent + Runtime workspace**：
```bash
paos onboard
paos agent
```

当 config 启用 runtime 时，`paos agent` / `paos gateway` 会自动创建 runtime workspace 并启动 session watchdog。
Agent 根据 agent context 与 runtime 协议文件规划；执行前读取 `TARGETS.md` 与 `SKILLRUNTIME.md`，并向 `SESSIONS.md` 追加待执行 session。

**真实 LIBERO benchmark + pi0.5 policy**：
```bash
# LIBERO benchmark TargetWS 机器
MUJOCO_GL=egl PYTHONWARNINGS=ignore \
conda run -n liberopi python PhyAgentOS/runtime/targets/remote/libero/server.py \
  --host 0.0.0.0 --port 9002

# pi0.5 policy 机器
conda run -n lerobot-pi python -m PhyAgentOS.runtime.policy.openpi.lerobot_pi0_server \
  --model-dir /path/to/pi05/checkpoint --host 0.0.0.0 --port 8000

# Agent 侧
paos agent -m "运行已配置的 LIBERO benchmark 任务"
```

**Isaac Sim 高保真仿真**：
```bash
python hal/hal_watchdog.py --gui --interval 0.05 \
  --driver pipergo2_manipulation \
  --driver-config examples/pipergo2_manipulation_driver.json
paos agent -m "open simulation"
paos agent -m "go to desk"
paos agent -m "pick up the red cube and return to the starting position"
```

---

## 1.10 项目结构

```
PhyAgentOS/
│
├── PhyAgentOS/agent/          # Track A ─ Planner / Critic / Memory
│   ├── loop.py                #   主 Agent 循环
│   ├── context.py             #   上下文窗口构建
│   ├── memory.py              #   短期/长期记忆系统
│   ├── skills.py              #   Skill 加载与执行
│   ├── subagent.py            #   子 Agent 生成
│   ├── tools/                 #   内置工具（文件、Shell、EmbodiedAction 等）
│   ├── cli/                   #   CLI 入口：paos onboard / agent / gateway
│   ├── providers/             #   LLM Provider 适配层
│   ├── channels/              #   14+ 消息平台集成
│   └── config/                #   Pydantic 配置模型
│
├── PhyAgentOS/runtime/        # Track B ─ 执行平面
│   ├── watchdog/              #   WatchdogSupervisor
│   ├── sessions/              #   SessionRunner / TargetSessionHandle
│   ├── targets/               #   RolloutTarget (debug·sim·real)
│   │   └── remote/libero/     #   LIBERO benchmark TargetWS server + proxy
│   ├── skillruntime/          #   PolicySkillRuntime / BuiltinSkillRuntime
│   ├── adapters/              #   TargetAdapter / PolicyAdapter / Bridge
│   │   ├── libero/            #   LIBERO target adapter
│   │   └── openpi/            #   OpenPI policy adapters
│   ├── policy/openpi/         #   OpenPI client + LeRobot pi0-family server
│   ├── perception/            #   感知运行时 / EnvironmentWriter
│   ├── preflight/             #   RuntimeCompatibilityPreflight
│   └── schemas/               #   Pydantic Schema
│
├── PhyAgentOS/skills/         # 内置 Skills（13 个）
│
├── hal/                       # 旧版 HAL（遗留，逐步废弃）
│   ├── hal_watchdog.py        #   旧版 Watchdog 入口
│   ├── base_driver.py         #   BaseDriver 抽象基类
│   ├── drivers/               #   内置驱动实现（10+）
│   ├── profiles/              #   机器人 Profile（9 个）
│   ├── navigation/            #   导航栈
│   ├── perception/            #   感知服务
│   ├── ros2/                  #   ROS2 桥接
│   ├── simulation/            #   仿真场景
│   └── plugins.py             #   外部插件注册
│
├── bridge/                    # TypeScript 桥接层
├── configs/runtime/           # Sensor / Perception / Contract YAML
├── scripts/                   # 部署脚本
├── examples/                  # 驱动配置示例（14 个）
├── tests/                     # pytest 测试套件（49 个文件）
└── docs/                      # 旧版文档（参考用）
```

---

## 后续阅读

- [Part 2: 用户手册](../02-user-manual.md) — 快速开始、场景配置、排障指南
- [Part 3: API 开发者手册](../03-developer-manual.md) — 接口文档、二次开发、代码风格

> **下一步**：如果你只想知道如何使用系统，直接进入 [用户手册](../02-user-manual.md)。
