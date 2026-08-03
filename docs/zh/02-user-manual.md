# 用户手册

## 配置与启动

执行 `paos onboard`，配置模型 Provider，并按根目录 README 启用 `forge`。endpoint 必须是 Forge Gateway 1.0.0，API 必须为 `paos-forge-gateway-mvp-plus.v1`。

使用 `paos agent` 交互，使用 `paos agent -m "..."` 执行单条请求，或使用 `paos gateway` 启动消息渠道。单消息若提交 Forge 任务，进程会等待整个 root lineage 终结。

## 描述任务

每次提交对应一个高层 Gateway action。Agent 需要构造动作描述、action type、inputs 和验证契约。所有非 `off` 模式必须给出 goal、至少一项 success criterion，以及必要的 constraints。

提交立即返回，完成和恢复通过 system event 唤醒 Agent。可随时使用 `forge_get_session` 查询持久化状态。

## 验证模式

- `off`：只关心 Gateway 命令是否完成。
- `audit`：记录验证结果，但不改变执行派生终态，也不恢复。
- `enforce`：缺证、不可判定或验证服务错误均失败关闭。
- `recovery`：在 `replan_required` 时允许 Planner 规划一个全新动作。

## 运维

- `forge_get_context` 查看实时 Gateway 能力和状态。
- `forge_cancel_session` 按 PAOS session ID 取消。
- `forge_reset` 只允许在没有活动 lineage 时调用。
- `verify_forge_session` 可复核终态任务，但不会改变原终态和 Execution Record。

## 故障排查

- API/support 校验失败：确认 endpoint 是受支持的 Gateway 1.0.0。
- `FORGE_EXECUTION_STATE_LOST`：PAOS 已记录派发，但 Gateway 丢失对应 session；系统不会重发动作。
- after 证据缺失：检查 `/ws/images`、source ID、capture timeout 和 frame sequence。
- verifier 不可用：非 `off` 任务会被拒绝或失败关闭，请配置有效 Provider/Service。
- busy：另一个 root lineage 仍占用串行执行槽，先查询或取消。

系统不会自动删除用户已有工作区内容。旧版本遗留的执行协议文件可在备份后人工清理；当前 PAOS 不再读取或生成它们。
