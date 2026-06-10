# PhyAgentOS × Minecraft — TODO List

---

## 1. 浏览器 3D 观察视角

**目标**：在浏览器中实时查看 bot 第一人称 3D 视角。

**方案**：
- **A. prismarine-viewer（官方）**：mineflayer 官方第一人称 3D viewer。需要在 Windows 上安装 Visual Studio Build Tools 编译 `canvas` 原生模块，或等 `canvas` 发布 Win11 24H2 (10.0.26200) 预编译二进制。
- **B. Web Viewer（纯前端）**：Three.js 轮询 bridge `/state` API 渲染 3D 俯视地图。不依赖原生模块，跨平台，但非第一人称视角。
- **C. 屏幕截图流**：PowerShell 截图 → HTTP MJPEG 流 → 浏览器显示实际游戏画面。

**当前状态**：已从 bridge 移除，待后续选择方案实现。

---

## 2. 复杂任务 Agent 闭环 ✅ 已完成

通过 `paos agent --workspace workspaces/minecraft` 实现，全链路贯通：

```
Agent 写 SESSIONS.md → WatchdogSupervisor 轮询 → Preflight 校验
→ SessionRunner 执行 → MinecraftSkillRuntime.run_builtin_loop()
→ SafetyClampBridge 透传 dict action → HTTP POST /action → mineflayer
→ 结果回写 ENVIRONMENT.md + LESSONS.md
→ Agent 读 ENVIRONMENT.md 验证 → 继续/重试
```

详见 [2_agent_loop.md](2_agent_loop.md)。

---

## 3. action 验证与错误恢复 ✅ 已完成

`MinecraftSkillRuntime.run_builtin_loop()` 在每个 action 执行后通过 `target_handle.action_chunk()` 返回值中的 `ok` 字段校验结果，失败时记录 `error_message`。Agent 在后续迭代中读取 LESSONS.md 获取失败原因并调整策略。

---

## 4. 动态环境下的动作编排调整

**问题**：当前 `perception_queries` 是 Agent 一次性预生成的全量动作序列。Minecraft 世界是动态的——方块被其他玩家挖掉、实体移动、昼夜变化、路径被阻挡——预生成的后续动作可能在执行时已经失效。

**当前状态**：
- 单步失败时，`MinecraftSkillRuntime.run_builtin_loop()` 记录 `error_message` 并终止 session，Agent 可通过 LESSONS.md + ENVIRONMENT.md 反思后重新规划
- 但 `move` 路径中途被堵、`collect` 目标方块被他人采走等场景，当前没有中途注入新动作的机制

**方向**：

| 方案 | 说明 | 复杂度 |
|------|------|--------|
| **A. 小 session 拆分** | Agent 只规划 1-3 步短 session，每步执行完由 Agent 读 ENVIRONMENT.md 验证后再写下一段 | 低（Agent 行为调整，不改代码） |
| **B. 条件动作** | `perception_queries` 支持 `if_fail: {type: ..., params: {...}}` 回退动作 | 中（需改 skill runtime 解析逻辑） |
| **C. 运行时回调** | skill runtime 在执行中途写 `ENVIRONMENT.md`，Agent 在心跳中检测到异常后追加 session | 中（利用已有 HEARTBEAT.md 机制） |
| **D. 探索基元** | 为“面朝方向走 10 步扫描周围方块”、“回到上一位置”等探索动作提供标准模板 | 低（Agent 自行组合） |

**推荐路径**：先走方案 A（Agent 端行为优化，零代码改动），验证效果后再考虑方案 B（fallback 动作）或 C（异步中断）。

---

## 5. 性能优化

- bridge `/state` 缓存（避免每 1s 全量扫描 nearby_blocks）
- LLM 调用去重（重复指令不重新生成）

---

## 6. 跨版本兼容

- 确认 mineflayer 支持 Minecraft 1.21.x
- 适配不同 ngrok 认证方式

---

## 7. Minecraft Benchmark 评测

**目标**：接上 Minecraft benchmark，量化评估 Agent 的能力。

**参考**：MineDojo、MineRL、Voyager 等已有 benchmark，可定义 PhyAgentOS 专属评测指标：
- 任务完成率（采集 N 个方块、合成 M 个物品）
- 探索效率（单位时间内访问的新区块数）
- 生存能力（存活时间、生命值管理）
- 指令理解准确率（自然语言 → 动作的匹配度）

**实现**：编写评测脚本，批量运行标准化任务并收集指标。

---

## 8. 长期记忆（Hermes 机制）

**目标**：整合类似 Hermes 的长期记忆机制，Agent 可从历史经验中总结规律。

**场景**：
- 之前在这个区域挖过铁矿石 → 下次找到同类型地形直接前往
- 合成配方失败过 → 记住正确配方不再重复错误
- 某个 NPC 交易过 → 记住交易内容

**实现方向**：
- LESSONS.md 经验库（框架已有，WatchdogSupervisor 的 ResultWriter 自动写入）
- 向量检索（embedding 相似任务经验）
- 成功/失败经验分类存储

---

## 9. 闭环自主调整规划（自进化）

**目标**：Agent 在闭环中自主调整计划，失败后不依赖人工介入。

**流程**：
```
观察 → 规划 → 执行 → 验证
  ↑                        ↓
  └── 失败时：分析原因 → 修正计划 → 重试
                    ↓
              总结经验 → 写入 LESSONS.md → 下次不重复
```

**实现**：
- Agent loop 中加入 failure reflection 步骤
- Critic 不只在动作前校验，也在动作后对照 ENVIRONMENT.md 校验
- 多次失败后自动降级（如 collect 失败 → 改用 dig 逐块挖掘）
