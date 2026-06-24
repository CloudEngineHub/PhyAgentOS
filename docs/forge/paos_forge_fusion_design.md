# PAOS-Forge 融合设计文档

本文档已拆分为四份独立设计文档，便于分别评审和维护：

1. [PAOS-Forge 融合总体设计](paos_forge_overall_design.md)
2. [Forge Gateway MVP+ 详细设计](forge_gateway_mvp_plus_design.md)
3. [PAOS / Gateway / Forge 三方接口协议附录](paos_gateway_forge_protocols.md)
4. [Forge Gateway Action Manifest 组织设计](forge_gateway_action_manifest_design.md)

当前实现以 Forge 内置 Gateway 为控制面，使用 `/agent/*` API、`forge_msgs.PolicyCommand`、`forge_msgs.PolicyCommandStatus`、`./actions/{robot_id}/{policy_id}.md` action manifest、JSONL event log 和 `runtime_context.json` snapshot 形成闭环。后续更新请优先修改对应拆分文档。
