# 开发手册

## 模块

- `PhyAgentOS/forge/client.py`：异步 Gateway HTTP API。
- `PhyAgentOS/forge/observation.py`：异步、有界的图像与状态采集。
- `PhyAgentOS/forge/evidence.py`：校验并写入 artifact 和公共 Evidence Bundle。
- `PhyAgentOS/forge/adapter.py`：单个 Gateway action 生命周期，不判断任务成功。
- `PhyAgentOS/forge/store.py`：事务化 SQLite 状态与事件日志。
- `PhyAgentOS/forge/orchestrator.py`：执行、验证、恢复、重启与通知。
- `PhyAgentOS/verification/contracts.py`：版本化、动作无关的公共契约。
- `PhyAgentOS/agent/session_verifier.py`：Forge Verifier 进程、调用和 retention。
- `PhyAgentOS/agent/tools/forge.py`：Agent Forge 工具。

## 不变量

- session/command ID 仅由系统生成。
- 一个 store 同时只有一个未终结 root lineage。
- POST 前持久化 dispatch intent，已尝试派发的动作永不自动重发。
- Gateway 终态必须同时匹配 session、command、request 和 action identity。
- Adapter 完成后 Execution Record 不可被 Verifier 或显式复核覆盖。
- Verifier prompt 与 Recovery Request 不得依赖具体 action type。
- parent `replanned` 与 child 创建在同一 SQLite 事务中完成。

## 增加动作

动作应在 Forge Gateway 中声明。PAOS 通过 capabilities 发现动作并传递通用 inputs。不要增加动作专用 verifier 开关；通过 task criteria 和 evidence policy 表达成功语义。

## 测试

Forge 测试覆盖公共契约、配置、状态机与并发、Gateway identity、观测边界、四种验证模式、恢复与重启。默认使用 fake client/adapter；可选黑盒测试通过 `FORGE_GATEWAY_URL` 连接 Gateway，且不得修改其源码或配置。

```bash
pytest
ruff check PhyAgentOS tests
python -m compileall -q PhyAgentOS tests
```

仓库守卫忽略 `plan/` 下的历史报告，并阻止已删除执行体系的 import、协议模板或入口重新进入活动代码。
