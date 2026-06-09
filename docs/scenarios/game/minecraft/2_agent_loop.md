# PhyAgentOS × Minecraft — Agent 闭环

> 承接 [1_hello.md](1_hello.md)。当前开环模式（LLM 盲生成全量动作）无法处理需要环境感知的任务。本文描述目标架构——多轮观察-推理-交互闭环。

---

## 一、为什么需要闭环

当前 `paos minecraft say "采集5个橡木"` 的流程：

```
用户 → LLM → [{collect: {block_type: "oak_log", count: 5}}] → 执行
                ↑ LLM 不知道哪里有橡木
                ↑ LLM 不知道 bot 的背包
                ↑ LLM 不知道采集是否成功
```

闭环应该做到：

```
观察 ENVIRONMENT.md → 知道附近有 oak_log 在 (10,64,5)
  → 决策: move forward=3 → 执行 → 验证: bot 到达了
  → 观察: 前方就是橡木 → 决策: collect oak_log 5
  → 执行 → 验证: inventory 中 oak_log += 5
  → 决策: move target=player → 执行 → 完成
```

---

## 二、目标架构

```
Agent (paos agent)                        Watchdog
──────────────────                        ────────
读 ENVIRONMENT.md                         轮询 ACTION.md
  → 看到: pos=(-37,63,-94),                  → POST /action
    blocks=[oak_log at (10,64,5)],           → observe()
    inventory=[]                             → 写 ENVIRONMENT.md
  → 决策: collect oak_log 5                          ↓
  → 写 ACTION.md                        Agent 读新 ENVIRONMENT.md
  → 读 ENVIRONMENT.md                        → 验证结果
  → 决策: move target=player                  → 继续...
  → ...
```

**关键组件**：

| 组件 | 说明 |
|------|------|
| ENVIRONMENT.md | watchdog 写入——bot 位置/朝向/血量/附近方块/实体/背包/玩家/最近动作 |
| ACTION.md | Agent 写入——待执行的动作队列 |
| EMBODIED.md | Agent 读入——合法动作约束（Critic 校验） |
| Watchdog | 轮询 ACTION.md → 执行 → 写 ENVIRONMENT.md |
| Agent (planner) | 读 ENVIRONMENT.md → LLM 决策 → 写 ACTION.md |
| Agent (critic) | 对照 EMBODIED.md 校验动作合法性 |

---

## 三、可解锁的能力

闭环完成后，以下当前无法实现的任务变得可行：

### 方块操作

```bash
paos agent "挖掉面前的橡木"
paos agent "在面前放一个工作台"
```
Agent 从 ENVIRONMENT.md 读到面前方块坐标，直接生成精确 `dig`/`place`。

### 复杂采集

```bash
paos agent "收集5个橡木然后过来合成工作台"
```
Agent 观察 → 找橡木 → 移动 → 采集 → 确认数量 → 移动 → 合成 → 确认。

### 背包管理

```bash
paos agent "切到石镐，挖掉铁矿石，再把火把切出来"
```
Agent 读 inventory → select_slot → dig → 验证 → select_slot。

### 探索与导航

```bash
paos agent "探索周边，找到村庄"
paos agent "绕过障碍物走到坐标 100 64 200"
```
逐步观察 nearby_blocks → 规划路径 → 移动 → 验证。

### 自进化

失败→分析原因→修正计划→重试→记录 LESSONS.md。

---

## 四、实现方案

**方案 A：恢复 watchdog 机制**（之前已实现过一版，后因过度复杂化删除了）

1. 恢复 `minecraft_action_runner.py`（精简版——仅轮询 ACTION.md + 执行 + 写 ENVIRONMENT.md，不加额外复杂度）
2. Agent 通过 `execute_robot_action` 工具单步写入 ACTION.md
3. watchdog 执行后写入 ENVIRONMENT.md，Agent 读回状态

**方案 B：直接在 Agent 循环内嵌 Target 调用**

1. Agent 循环中直接调用 `MinecraftTarget.step()`
2. 不需要中间文件协议
3. 更简单但耦合度更高

**推荐方案 A**——与 PhyAgentOS 文件协议一致，支持多 Target 扩展。

---

## 五、验证任务

闭环完成后，逐条验证以下场景：

### 环境感知移动

- [ ] bot 在障碍物前 → Agent 观察到障碍 → 绕行
- [ ] bot 在悬崖边 → Agent 观察到 → 不前进

### 采集验证

- [ ] "采集5个橡木" → Agent 确认到了 5 个才停止
- [ ] 附近无橡木 → Agent 探索搜索 → 找到再采

### 错误恢复

- [ ] collect 失败 → Agent 读错误 → 换策略（如改用 dig）
- [ ] move 超时 → Agent 重试或绕行

### 多步复杂任务

- [ ] "采集橡木，合成工作台，放在面前"
- [ ] "探索找到村庄，找村民交易"

---

## 六、相关文件

| 文件 | 说明 |
|------|------|
| `1_hello.md` | 当前可用动作（开环模式） |
| `0_start.md` | 部署文档 |
| `todo_list.md` | 完整 TODO 列表 |
| `bridge_server.js` | mineflayer bridge |
