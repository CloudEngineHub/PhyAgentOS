# PhyAgentOS 用户手册

> 面向使用者、集成者与演示操作者的运行手册。覆盖单机模式、Fleet 多机器人模式、各场景配置与排障指南。

---

## 目录

- [2.1 手册定位](#21-手册定位)
- [2.2 系统工作原理](#22-系统工作原理)
- [2.3 安装与环境准备](#23-安装与环境准备)
- [2.4 5 分钟快速开始](#24-5-分钟快速开始)
- [2.5 配置详解](#25-配置详解)
- [2.6 场景使用指南](#26-场景使用指南)
  - [2.6.1 仿真场景](#261-仿真场景)
  - [2.6.2 真机机械臂（Franka Research 3）](#262-真机机械臂franka-research-3)
  - [2.6.3 移动机器人（Go2）](#263-移动机器人go2)
  - [2.6.4 远程底盘（XLeRobot）](#264-远程底盘xlerobot)
  - [2.6.5 ReKep 真机插件](#265-rekep-真机插件)
  - [2.6.6 Fleet 多机器人协同](#266-fleet-多机器人协同)
- [2.7 运行时文件说明](#27-运行时文件说明)
- [2.8 常见交互示例](#28-常见交互示例)
- [2.10 常见问题排查](#210-常见问题排查)

---

## 2.1 手册定位

### 适合谁

- 希望快速跑通 PhyAgentOS 的首次使用者
- 需要用命令行操作 Agent 的集成使用者
- 需要启动仿真、Go2、远程底盘或真实机器人插件的演示操作者
- 需要理解运行时工作区文件如何变化的调试人员

### 不适合谁

如果你要进行二次开发、编写驱动、开发插件或研究系统内部架构，请阅读 [Part 3: API 开发者手册](../03-developer-manual.md)。

---

## 2.2 系统工作原理

### 2.2.1 双轨结构

PhyAgentOS 是一个显式解耦的双轨运行架构：

- **Track A（Agent / 大脑）**：负责理解用户输入、规划动作、调用工具、Critic 校验。通过 `paos agent` 或 `paos gateway` 启动。
- **Track B（Runtime / 执行层）**：负责读取指令、驱动硬件、执行动作、回写状态。通过 `python -m PhyAgentOS.runtime.watchdog` 启动。

两者之间的共享状态通过工作区中的 Markdown 文件表达，而不是跨层直接 Python 调用。

### 2.2.2 单机模式与 Fleet 模式

| 模式 | 工作区 | 适用场景 |
|------|--------|---------|
| **单机模式（single）** | `~/.PhyAgentOS/workspace` | 单个机器人或仿真快速验证 |
| **Fleet 模式（fleet）** | 共享 + per-robot 工作区 | 异构多机器人协同 |

### 2.2.3 一次典型运行的完整闭环

1. 运行 `paos onboard` 初始化配置与工作区
2. 启动 Watchdog，安装 `EMBODIED.md`（机器人能力声明）
3. 启动 `paos agent` 或 `paos gateway`
4. 用户输入自然语言任务
5. Agent 读取 `ENVIRONMENT.md` 等工作区文件进行规划
6. Critic 结合 `EMBODIED.md` 校验动作是否安全可行
7. 校验通过的动作被写入 `ACTION.md` 或 `SESSIONS.md`
8. Watchdog 读取并解析，调用驱动执行动作
9. Watchdog 将最新状态回写到 `ENVIRONMENT.md`

---

## 2.3 安装与环境准备

### 基础要求

- Python 3.11 或更高版本
- Git
- 可访问的 LLM 提供方 API 或兼容服务
- 仿真场景可选：`pybullet`、Isaac Sim
- 桥接/前端可选：Node.js 18+

### 克隆与安装

```bash
git clone https://github.com/PhyAgentOS/PhyAgentOS.git
cd PhyAgentOS
pip install -e .             # Python ≥ 3.11
pip install -e ".[dev]"      # 开发依赖
```

### 安装后你会得到

CLI 入口 `paos` 来自项目的 Python 包入口：

- `paos onboard` — 初始化工作区
- `paos agent` — 启动交互式 Agent
- `paos agent -m "..."` — 单轮消息调用
- `paos gateway` — 启动长期在线网关

---

## 2.4 5 分钟快速开始

### 第 1 步：安装

```bash
git clone https://github.com/PhyAgentOS/PhyAgentOS.git && cd PhyAgentOS
pip install -e .
```

### 第 2 步：初始化工作区

```bash
paos onboard
```

该命令会：创建/刷新 `~/.PhyAgentOS/config.json`、准备默认工作区、同步模板文件。

### 第 3 步：启动 Runtime（Track B）

打开终端 A：

```bash
python -m PhyAgentOS.runtime.watchdog
```

默认使用内置仿真驱动，零硬件即可跑通全链路。

### 第 4 步：启动 Agent（Track A）

打开终端 B：

```bash
paos agent
```

进入交互模式后，直接输入自然语言任务，例如：

```text
看看桌面上有什么物体。
```

### 无硬件验证管道

```bash
python scripts/init_runtime_workspace.py --workspace /tmp/paos_runtime_smoke
python scripts/run_runtime_watchdog.py --workspace /tmp/paos_runtime_smoke --once
# → session 标记 succeeded，结果写入 artifacts/
```

---

## 2.5 配置详解

### 最小配置

最小可用配置至少需要：

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

配置位置：`~/.PhyAgentOS/config.json`

### 关键配置域

| 配置域 | 用途 |
|--------|------|
| `agents.defaults` | 默认模型、工作区路径 |
| `providers` | LLM 提供方 API Key 与地址 |
| `gateway` | 网关服务配置 |
| `tools` | 工具启用/禁用 |
| `embodiments` | 具身配置（single / fleet 模式） |

### Fleet 模式最小配置

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

### 工作区路径

| 模式 | 路径 |
|------|------|
| 单机模式 | `~/.PhyAgentOS/workspace` |
| Fleet 共享工作区 | `~/.PhyAgentOS/workspaces/shared` |
| Fleet 机器人工作区 | `~/.PhyAgentOS/workspaces/<robot_id>` |

> 每次修改配置后建议重新执行 `paos onboard`，它会刷新模板并补充新字段。

---

## 2.6 场景使用指南

### 2.6.1 仿真场景

内置仿真驱动 `simulation` 是最快验证全链路的起点。

```bash
# 终端 1：启动仿真 Watchdog
python -m PhyAgentOS.runtime.watchdog

# 终端 2：启动 Agent
paos agent
```

**Isaac Sim 高保真仿真（PIPER + Go2 复合操作）**：

```bash
# GUI 模式（需要本地 X 显示）
python hal/hal_watchdog.py --gui --interval 0.05 \
  --driver pipergo2_manipulation \
  --driver-config examples/pipergo2_manipulation_driver.json

# VNC 模式（远程服务器/容器，通过浏览器访问）
python hal/hal_watchdog.py --vnc --interval 0.05 \
  --driver pipergo2_manipulation \
  --driver-config examples/pipergo2_manipulation_driver.json
# 浏览器打开 http://<host>:31315/vnc.html
```

然后通过 Agent 发送命令：

```bash
paos agent -m "open simulation"
paos agent -m "go to desk"
paos agent -m "pick up the red cube and return to the starting position"
```

> `--gui` 和 `--vnc` 互斥。不加任一参数则运行 headless 模式。

---

### 2.6.2 真机机械臂（Franka Research 3）

#### 网络架构

```
WorkStation PC → Control Box (Shop Floor: 172.16.0.x) → Robot Arm
```

#### 首次设置

1. 网线连接 PC ↔ Control Box（Shop Floor 接口）
2. PC 有线网络 IP 设为 `172.16.0.x`（如 `172.16.0.1`）
3. 在 Control Box Desk 界面激活 FCI
4. 安装后端驱动

#### 后端安装

```bash
# pylibfranka（官方 Python 绑定）
pip install pylibfranka

# franky-control（备选高层库，更宽松兼容性）
pip install git+https://github.com/TimSchneider42/franky.git
```

#### 驱动选择

| 驱动名 | 说明 | 适用场景 |
|:-------|:-----|:---------|
| `franka_research3` | 原始 pylibfranka 驱动 | 精确控制或实时 1kHz |
| `franka_multi` | 多后端协商驱动 | 自动选择可用后端 |

#### 启动方式

```bash
# 多后端自动协商（推荐）
python hal/hal_watchdog.py --driver franka_multi

# 原始 pylibfranka 驱动
python hal/hal_watchdog.py --driver franka_research3

# 自定义配置
python hal/hal_watchdog.py \
  --driver franka_multi \
  --driver-config examples/franka_research3.driver.json
```

#### 支持的动作

`move_to`（笛卡尔位置）、`move_joints`（关节位置）、`grasp`、`move_gripper`、`stop` 等。

#### 实时控制模式

设置 `realtime_mode: true` 启用 1 kHz 实时控制（需安装实时内核）。

> 安装前请确认库版本与机器人系统版本兼容。

---

### 2.6.3 移动机器人（Go2）

```bash
python hal/hal_watchdog.py \
  --driver go2_edu \
  --driver-config examples/go2_driver_config.json
```

驱动配置 JSON 透传给 Go2 驱动，用于远程 ROS2、视频、状态流和运动后端初始化。

---

### 2.6.4 远程底盘（XLeRobot）

```bash
python hal/hal_watchdog.py \
  --driver xlerobot_2wheels_remote \
  --driver-config examples/xlerobot_2wheels_remote.driver.json
```

配置示例中包含 ZMQ 通信参数、远程主机地址等。

---

### 2.6.5 ReKep 真机插件

`rekep_real` 通过外部插件仓库接入：

```bash
# 部署插件
python scripts/deploy_rekep_real_plugin.py \
  --repo-url https://github.com/baiyu858/PhyAgentOS-rekep-real-plugin.git

# 启动
python hal/hal_watchdog.py --driver rekep_real
```

---

### 2.6.6 Fleet 多机器人协同

#### 何时使用

- 让一个 Agent 面向多个机器人实例协同规划
- 将共享环境与机器人私有动作队列分开维护
- 明确每台机器人的独立 `EMBODIED.md` 与 `ACTION.md`

#### 启动顺序

1. 配置 `embodiments.mode = "fleet"`
2. 运行 `paos onboard`
3. 为每个机器人实例启动一个 Watchdog
4. 启动一个 `paos agent`

```bash
# 机器人 1
python hal/hal_watchdog.py \
  --robot-id go2_edu_001 \
  --driver-config examples/go2_driver_config.json

# 机器人 2
python hal/hal_watchdog.py \
  --robot-id xlerobot_lab_001 \
  --driver-config examples/xlerobot_2wheels_remote.driver.json

# 统一 Agent
paos agent
```

#### Fleet 模式文件布局

| 文件 | 位置 | 用途 |
|------|------|------|
| `ENVIRONMENT.md` | shared/ | 全局环境状态 |
| `ROBOTS.md` | shared/ | 机器人目录摘要 |
| `TASK.md` | shared/ | 多步任务状态 |
| `ORCHESTRATOR.md` | shared/ | 全局编排状态 |
| `EMBODIED.md` | per-robot/ | 单机器人运行时能力声明 |
| `ACTION.md` | per-robot/ | 单机器人动作队列 |

---

## 2.7 运行时文件说明

| 文件 | 位置 | 作用 |
|------|------|------|
| `ACTION.md` | 单机或 per-robot 工作区 | 待执行动作队列（JSON 格式） |
| `EMBODIED.md` | 单机或 per-robot 工作区 | 当前机器人能力、约束与连接声明 |
| `ENVIRONMENT.md` | 单机或 shared 工作区 | 当前环境、对象、地图、机器人状态 |
| `LESSONS.md` | 单机或 shared 工作区 | Critic 拒绝动作后的失败经验记录 |
| `TASK.md` | 单机或 shared 工作区 | 多步任务拆解状态 |
| `SESSIONS.md` | 单机或 shared 工作区 | 执行会话队列（新版协议） |
| `TARGETS.md` | shared 工作区 | 目标（机器人/仿真）注册索引 |
| `ORCHESTRATOR.md` | shared 工作区 | 编排层状态 |
| `ROBOTS.md` | Fleet shared 工作区 | 机器人实例目录摘要 |

---

## 2.8 常见交互示例

### 环境查询

```text
看看当前环境里有什么物体。
```

验证点：Agent 是否能读取 `ENVIRONMENT.md`，环境状态是否已被 Watchdog 正确写回。

### 机械臂抓取任务

```text
把桌上的红色苹果拿起来，放到托盘里。
```

验证点：目标物体是否存在于环境状态、机器人 profile 是否声明了对应动作、Watchdog 是否成功执行并清空动作队列。

### 移动机器人导航

```text
移动到冰箱附近并停下。
```

验证点：场景图中是否存在目标语义位置、当前移动机器人是否支持导航动作。

### Fleet 多机器人协同

```text
让 Go2 先去门口巡检，再让机械臂把桌上的包裹抓起来准备交接。
```

验证点：Agent 是否识别多个机器人实例、动作是否分发到正确机器人、`ROBOTS.md` 是否正确更新状态。

### Isaac Sim 环境操控

```bash
paos agent -m "open simulation"
paos agent -m "go to desk"
paos agent -m "pick up the red cube and return to the starting position"
```

### VLA 模型抓取

```bash
paos agent -m "deploy a VLA to pick up the red cube"
```

可通过修改 `examples/pipergo2_manipulation_driver.json` 中的 `vla` 块配置自己的 VLA checkpoint。

---

## 2.9 常见问题排查

### 提示没有 API Key

**现象**：启动 Agent 后报没有 API key。

**排查**：
1. 检查 `~/.PhyAgentOS/config.json` 是否配置了 `providers.<name>.api_key`
2. 确认 `agents.defaults.model` 与对应 provider 配套
3. 确保 API Key 格式正确，无多余空格

### Watchdog 启动后没有 EMBODIED.md

**现象**：Critic 提示找不到 `EMBODIED.md`。

**排查**：
1. 确认已执行 `paos onboard`
2. 确认 Watchdog 已成功启动
3. 确认所选 driver 的 profile 文件存在且可读取
4. Fleet 模式下确认查看的是目标机器人的工作区

### ACTION.md 有内容但动作没执行

**排查**：
1. 确认对应 Watchdog 仍在运行
2. 检查 `ACTION.md` 中 JSON 代码块格式是否完整
3. 查看 Watchdog 终端日志是否出现驱动报错
4. 检查 `driver-config` 是否缺失关键参数

### 动作被 Critic 拒绝

**排查**：
1. 查看 `LESSONS.md` 中的失败原因
2. 检查目标动作是否在 `EMBODIED.md` 的 Supported Actions 中声明
3. 检查 `ENVIRONMENT.md` 中是否存在对应目标物体、地图信息或机器人连接状态
4. 检查动作参数（坐标、关节角等）是否在物理约束范围内

### Fleet 模式下任务没有派发到正确机器人

**排查**：
1. 检查配置中的 `robot_id`、`driver`、`workspace` 是否匹配
2. 确认 Watchdog 是通过 `--robot-id` 启动
3. 检查共享工作区的 `ROBOTS.md` 是否已正确生成
4. 确认任务语义里明确了目标机器人

### 找不到 rekep_real 驱动

**排查**：
1. 确认已经执行插件部署脚本 `python scripts/deploy_rekep_real_plugin.py`
2. 确认插件仓库已注册到本地插件目录 `~/.PhyAgentOS/plugins/`
3. 重启 Watchdog 使插件加载生效

### Isaac Sim 启动失败

**排查**：
1. 确认 Isaac Sim 已正确安装
2. 检查 `pipergo2_manipulation_driver.json` 中 `isaac_env` 块的路径配置
3. `--vnc` 模式下查看首次启动的 re-exec 日志
4. 确认 `LD_LIBRARY_PATH` 已正确设置（VNC 模式会自动处理）

---

## 后续阅读

- [Part 1: 框架介绍](../01-framework-introduction.md) — 设计理念、架构、路线图
- [Part 3: API 开发者手册](../03-developer-manual.md) — 接口文档、二次开发、代码风格

> **下一步**：如果需要开发新驱动或接入新硬件，进入 [API 开发者手册](../03-developer-manual.md)。
