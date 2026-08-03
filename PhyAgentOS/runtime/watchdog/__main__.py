"""Entry point for `python -m PhyAgentOS.runtime.watchdog`."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PhyAgentOS.runtime.watchdog.supervisor import WatchdogSupervisor

DEFAULT_WORKSPACE = Path(os.path.expanduser("~/.PhyAgentOS/workspace"))


def main() -> int:
    parser = argparse.ArgumentParser(description="PhyAgentOS Runtime Watchdog Supervisor")
    parser.add_argument(
        "--workspace",
        default=str(DEFAULT_WORKSPACE),
        help=f"Workspace path (default: {DEFAULT_WORKSPACE})",
    )
    parser.add_argument(
        "--environment-workspace",
        help="Agent/shared workspace for ENVIRONMENT.md (default: same as --workspace)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one polling pass and exit",
    )
    parser.add_argument(
        "--verification-service-enabled",
        action="store_true",
        help=(
            "Allow non-off sessions to enter awaiting_verification. The Agent-owned "
            "verifier must be running separately."
        ),
    )
    parser.add_argument(
        "--verification-timeout-s",
        type=float,
        default=210.0,
        help="Fail stale awaiting/verifying sessions after this many seconds.",
    )
    args = parser.parse_args()

    supervisor = WatchdogSupervisor(
        args.workspace,
        environment_workspace=args.environment_workspace,
        verification_service_enabled=args.verification_service_enabled,
        verification_timeout_s=args.verification_timeout_s,
    )

    if args.once:
        return 0 if supervisor.run_once() else 1

    while True:
        supervisor.run_once()


if __name__ == "__main__":
    raise SystemExit(main())
