# PhyAgentOS × Minecraft — TODO List

---

## 1. 浏览器 3D 观察视角

**目标**：在浏览器中实时查看 bot 第一人称 3D 视角。

**方案**：
- **A. prismarine-viewer（官方）**：mineflayer 官方第一人称 3D viewer，已集成到 bridge_server.js（spawn 后加载）。需要在 Windows 上安装 Visual Studio Build Tools 编译 `canvas` 原生模块，或等 `canvas` 发布 Win11 24H2 (10.0.26200) 预编译二进制。
- **B. Web Viewer（纯前端）**：Three.js 轮询 bridge `/state` API 渲染 3D 俯视地图。不依赖原生模块，跨平台，但非第一人称视角。已实现过一版（viewer.html），需要优化：纹理贴图、第一人称切换、实体动画。
- **C. 屏幕截图流**：PowerShell 截图 → HTTP MJPEG 流 → 浏览器显示实际游戏画面。已尝试过 PowerShell 方案（`_screen.ps1`），变量转义问题未完全解决。

**当前状态**：已从 bridge 移除，待后续选择方案实现。

---

## 2. 复杂任务 Agent 闭环

详见 [2_agent_loop.md](2_agent_loop.md)。

**目标**：Agent 读取 ENVIRONMENT.md 感知 bot 状态，逐步规划并执行复杂多步任务。当前仅支持开环 `paos minecraft say`（LLM 盲生成全量动作列表）。

需要：
- Watchdog 持续写入 ENVIRONMENT.md
- Agent 读取 ENVIRONMENT.md 逐步调用 `execute_robot_action`
- EMBODIED.md 包含 Minecraft 动作约束

---

## 3. action 验证与错误恢复

**目标**：每个动作执行后验证效果，失败时自动重试或调整策略。

**示例**：
- `collect oak_log 5` 执行后检查 inventory 是否增加
- `move` 执行后检查位置是否接近目标
- `look yaw=180` 执行后检查朝向是否正确

**当前状态**：SkillRuntime 直接执行，不校验结果。

---

## 4. 性能优化

- bridge `/state` 缓存（避免每 1s 全量扫描 nearby_blocks）
- `paos minecraft listen` 轮询间隔自适应
- LLM 调用去重（重复指令不重新生成）

---

## 5. 跨版本兼容

- 确认 mineflayer 支持 Minecraft 1.21.x
- 适配不同 ngrok 认证方式

---

## 6. Minecraft Benchmark 评测

**目标**：接上 Minecraft benchmark，量化评估 Agent 的能力。

**参考**：MineDojo、MineRL、Voyager 等已有 benchmark，可定义 PhyAgentOS 专属评测指标：
- 任务完成率（采集 N 个方块、合成 M 个物品）
- 探索效率（单位时间内访问的新区块数）
- 生存能力（存活时间、生命值管理）
- 指令理解准确率（自然语言 → 动作的匹配度）

**实现**：编写评测脚本，批量运行标准化任务并收集指标。

---

## 7. 长期记忆（Hermes 机制）

**目标**：整合类似 Hermes 的长期记忆机制，Agent 可从历史经验中总结规律。

**场景**：
- 之前在这个区域挖过铁矿石 → 下次找到同类型地形直接前往
- 合成配方失败过 → 记住正确配方不再重复错误
- 某个 NPC 交易过 → 记住交易内容

**实现方向**：
- 写入 LESSONS.md（框架已有）
- 向量检索（embedding 相似任务经验）
- 成功/失败经验分类存储

---

## 8. 闭环自主调整规划（自进化）

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
