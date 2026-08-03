# PhyAgentOS

PhyAgentOS 是一个只保留 Forge 执行入口的 Agent 框架。Agent 规划高层动作，Forge Adapter 调用 Gateway 1.0.0，采集执行前后证据，并在向用户报告任务成功前进行系统级语义验证。

[English](README.md) · [Forge 接入说明](docs/forge/README.md) · [用户手册](docs/zh/02-user-manual.md) · [开发手册](docs/zh/03-developer-manual.md)

## 架构

```text
用户 / 消息渠道
      │
      ▼
Agent Planner ── Forge 工具 ──► ForgeSessionOrchestrator
                                      │
                   ┌──────────────────┼──────────────────┐
                   ▼                  ▼                  ▼
             ForgeAdapter       SQLite 事件日志     ForgeTaskVerifier
                   │                  │                  │
                   ▼                  ▼                  ▼
          Forge Gateway 1.0.0     公共契约          verdict / recovery
                   │
                   ▼
             Forge + Dora
```

Gateway 的 `succeeded` 只表示动作执行事实。在 `enforce` 和 `recovery` 模式下，任务是否成功由 Verifier 判定。

## 安装与配置

```bash
git clone https://github.com/HKUDS/PhyAgentOS.git
cd PhyAgentOS
pip install -e .
paos onboard
```

在 `~/.PhyAgentOS/config.json` 配置模型 Provider 和唯一 Forge endpoint：

```json
{
  "agents": {
    "verification": {
      "serviceEnabled": true,
      "evidenceRetention": "failed",
      "maxReplansPerEpisode": 2
    }
  },
  "forge": {
    "enabled": true,
    "baseUrl": "http://127.0.0.1:9001",
    "apiVersion": "paos-forge-gateway-mvp-plus.v1",
    "executionTimeoutS": 300,
    "evidence": {
      "requiredImageSources": ["front"],
      "captureTimeoutS": 5,
      "postCaptureTimeoutS": 5,
      "maxArtifactBytes": 8388608,
      "associationQuality": "best_effort"
    }
  }
}
```

```bash
paos agent
paos gateway
```

## Forge 工具

- `forge_execute_task`：异步提交高层动作，由系统生成全新 session/command ID。
- `forge_get_session`：读取任务、执行事实、证据、判定和恢复状态。
- `forge_cancel_session`：取消未终结执行或恢复。
- `forge_get_context`：读取实时 capabilities、readiness 和 context。
- `forge_reset`：在没有活动任务时显式复位 Gateway。
- `verify_forge_session`：使用保留证据显式复核，不修改 Execution Record 或任务终态。
- `create_replanned_forge_session`：为 `awaiting_replan` parent 原子创建全新 child。

验证模式为 `off`、`audit`、`enforce` 和 `recovery`。所有非 `off` 任务必须声明 goal 和至少一项 success criterion。

## 持久化

编排状态和事件日志位于 `<workspace>/.paos/forge/orchestrator.sqlite3`，证据及公共契约 artifact 位于 `<workspace>/artifacts/forge/<session_id>/`。系统在 POST 前持久化 dispatch attempt，重启后不会盲目重复执行动作。

`EMBODIED.md`、`ENVIRONMENT.md` 和 SceneGraph 继续作为知识上下文存在，但不再承担执行队列职责。

## 开发验证

```bash
pip install -e '.[dev]'
pytest
ruff check PhyAgentOS tests
python -m compileall -q PhyAgentOS tests
```

详细契约见 [Forge 接入说明](docs/forge/README.md)，历史设计报告保留在 `plan/`。
