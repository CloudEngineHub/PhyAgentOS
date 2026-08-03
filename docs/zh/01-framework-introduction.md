# 框架介绍

PhyAgentOS 将对话规划与机器人执行解耦：Agent 和技能负责推理与用户交互；`ForgeSessionOrchestrator` 是唯一机器人执行编排器；Forge Gateway 1.0.0 负责仿真或真机动作；`ForgeTaskVerifier` 根据持久化证据判定系统级任务标准。

公共边界由 `ForgeTaskRequest`、`ForgeSessionRecord`、`TaskVerificationContract`、`ExecutionRecord`、`EvidenceBundle`、`VerificationVerdict` 和 `RecoveryRequest` 构成，所有模型均与具体动作无关。

系统刻意区分三个事实：Gateway 是否完成动作命令、PAOS 在动作前后观察到什么，以及任务成功标准是否真正满足。

Embodiment、`EMBODIED.md`、`ENVIRONMENT.md` 和 SceneGraph 继续作为知识面存在，但不负责派发动作。

继续阅读[用户手册](02-user-manual.md)、[开发手册](03-developer-manual.md)或 [Forge 契约](../forge/README.md)。
