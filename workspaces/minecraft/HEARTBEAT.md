# Heartbeat Tasks

This file is checked every 30 minutes by your PhyAgentOS agent.
Add tasks below that you want the agent to work on periodically.

If this file has no tasks (only headers and comments), the agent will skip the heartbeat.

## Active Tasks

<!-- Add your periodic tasks below this line -->

- [ ] Read ENVIRONMENT.md and check if any objects have changed state. If something notable happened (e.g., an object fell, moved, or disappeared), proactively report to the user.
- [ ] Read ACTION.md — if it is non-empty and has been pending for more than 5 minutes, warn the user that the hardware watchdog may not be running.
- [ ] **安全检查**：检查 Minecraft bot 的健康状态（health check），如果生命值低于 10 或附近有敌对实体，立即采取行动（远离或击杀）并通知用户。

## Completed

<!-- Move completed tasks here or delete them -->

