# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Scheduled Reminders

Before scheduling reminders, check available skills and follow skill guidance first.
Use the built-in `cron` tool to create/list/remove jobs (do not call `PhyAgentOS cron` via `exec`).
Get USER_ID and CHANNEL from the current session (e.g., `8281248569` and `telegram` from `telegram:8281248569`).

**Do NOT just write reminders to MEMORY.md** — that won't trigger actual notifications.

## Heartbeat Tasks

`HEARTBEAT.md` is checked on the configured heartbeat interval. Use file tools to manage periodic tasks:

- **Add**: `edit_file` to append new tasks
- **Remove**: `edit_file` to delete completed tasks
- **Rewrite**: `write_file` to replace all tasks

When the user asks for a recurring/periodic task, update `HEARTBEAT.md` instead of creating a one-time cron reminder.

## Runtime Sessions (Minecraft / Simulation / Robot)

When the user asks to execute a task on an available runtime target (e.g. Minecraft, simulation, real robot), follow the `RUNTIME.md` protocol:

1. Read `TARGETS.md` to see available targets (targets with `enabled: true` and `target_kind: game/simulation/real_robot`).
2. Read `SKILLS.md` to see skills supported by the target.
3. Read `ENVIRONMENT.md` for the latest target state.
4. Read `SESSIONS.md` to see existing sessions, then use `write_file` to rewrite it with your new session appended. Do NOT use `edit_file` — SESSIONS.md is structured YAML and `edit_file` will corrupt the formatting.

**Minecraft workflow** (when `target_kind: game` target is available):
- The session watchdog (WatchdogSupervisor) is running automatically — you do NOT need to start it.
- Write a session to SESSIONS.md with `target_ref: target://minecraft_java_env`, `skill_ref: skill://minecraft_navigate`.
- Use `runtime_hints.perception_queries` to specify the exact action sequence.
- After writing, wait for the watchdog to execute (watch ENVIRONMENT.md for updates).
- Read `LESSONS.md` to learn from past successes and failures.

**Simulation/robot workflow** (when `target_kind: simulation` or `real_robot` target is available):
- For PiperGo2 manipulation sim: ensure HAL watchdog is running (`python hal/hal_watchdog.py --gui --driver pipergo2_manipulation --driver-config ...`).
- Use `execute_robot_action` to dispatch actions to ACTION.md.
