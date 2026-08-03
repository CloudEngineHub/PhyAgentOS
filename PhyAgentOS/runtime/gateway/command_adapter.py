"""Agent command adapter for direct Forge Gateway runtime commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PhyAgentOS.runtime.gateway.client import ForgeGatewayClient
from PhyAgentOS.runtime.state_io.markdown_yaml import read_yaml_block


class ForgeGatewayCommandAdapter:
    """Small Agent-facing adapter for commands that are not action sessions.

    Action execution uses SESSIONS.md and the verification-aware ForgeAdapter.
    Runtime-level commands such as scene reset use this separate adapter so they
    are not misrepresented as `/agent/sessions` task actions.
    """

    def __init__(self, client: ForgeGatewayClient):
        self.client = client

    @classmethod
    def from_workspace(
        cls,
        workspace: str | Path,
        *,
        target_id: str = "forge_gateway",
        timeout_s: float = 10.0,
    ) -> "ForgeGatewayCommandAdapter":
        endpoint = resolve_gateway_endpoint(Path(workspace), target_id=target_id)
        return cls(ForgeGatewayClient(endpoint, timeout_s=timeout_s))

    def reset_runtime(self, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.reset_runtime(inputs or {})


def resolve_gateway_endpoint(workspace: Path, *, target_id: str = "forge_gateway") -> str:
    targets_path = workspace.expanduser() / "TARGETS.md"
    document = read_yaml_block(targets_path)
    targets = document.get("targets")
    if not isinstance(targets, list):
        raise ValueError(f"{targets_path} must contain a targets list")

    candidate_ids = [target_id]
    if target_id == "forge_gateway":
        # Existing workspaces created before the generic target rename may still
        # use this legacy id. Keep reset usable without forcing users to rewrite
        # their runtime workspace immediately.
        candidate_ids.append("forge_gateway_piper_sim")

    found_disabled: str | None = None
    for target in targets:
        if not isinstance(target, dict) or target.get("id") not in candidate_ids:
            continue
        if target.get("enabled") is not True:
            found_disabled = str(target.get("id"))
            continue
        runtime = target.get("runtime") if isinstance(target.get("runtime"), dict) else {}
        endpoint = runtime.get("target_endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError(f"target {target.get('id')!r} does not define runtime.target_endpoint")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError(f"target {target.get('id')!r} endpoint must be HTTP(S): {endpoint}")
        return endpoint

    if found_disabled is not None:
        raise ValueError(f"target {found_disabled!r} is not enabled in {targets_path}")
    raise ValueError(f"target {target_id!r} not found in {targets_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send direct Agent commands to Forge Gateway")
    parser.add_argument("command", choices=["reset"], help="Command to execute")
    parser.add_argument("--workspace", required=True, help="Runtime workspace containing TARGETS.md")
    parser.add_argument("--target-id", default="forge_gateway", help="Gateway target id in TARGETS.md")
    parser.add_argument("--reason", default="paos-agent", help="Reason attached to reset inputs")
    args = parser.parse_args()

    adapter = ForgeGatewayCommandAdapter.from_workspace(args.workspace, target_id=args.target_id)
    if args.command == "reset":
        response = adapter.reset_runtime({"reason": args.reason, "source": "paos-agent"})
    else:
        raise AssertionError(f"unsupported command: {args.command}")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
