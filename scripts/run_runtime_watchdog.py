#!/usr/bin/env python
"""Run the PhyAgentOS runtime v2 watchdog supervisor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PhyAgentOS.runtime.watchdog.supervisor import WatchdogSupervisor

REQUIRED_RUNTIME_FILES = ("TARGETS.md", "SKILLRUNTIME.md", "SESSIONS.md")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PhyAgentOS runtime v2 watchdog")
    parser.add_argument("--workspace", required=True, help="Workspace containing TARGETS/SKILLRUNTIME/SESSIONS.md")
    parser.add_argument(
        "--environment-workspace",
        help="Agent/shared workspace where perception writes ENVIRONMENT.md. Defaults to --workspace.",
    )
    parser.add_argument("--once", action="store_true", help="Run one polling pass and exit")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser()
    missing = [name for name in REQUIRED_RUNTIME_FILES if not (workspace / name).exists()]
    if missing:
        print(
            "Runtime workspace is missing required files: "
            + ", ".join(missing)
            + "\nInitialize it first:\n"
            + f"  python scripts/init_runtime_workspace.py --workspace {workspace}",
            file=sys.stderr,
        )
        return 2

    supervisor = WatchdogSupervisor(workspace, environment_workspace=args.environment_workspace)
    if args.once:
        return 0 if supervisor.run_once() else 1

    while True:
        supervisor.run_once()


if __name__ == "__main__":
    raise SystemExit(main())
