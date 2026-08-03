"""Explicit Agent tool for applying or reviewing a semantic verification."""

from __future__ import annotations

import json
from typing import Any

from PhyAgentOS.agent.tools.base import Tool


class VerifySessionTool(Tool):
    def __init__(self, verifier) -> None:
        self.verifier = verifier

    @property
    def name(self) -> str:
        return "verify_session"

    @property
    def description(self) -> str:
        return (
            "Run semantic verification for a completed runtime session. Pending verification "
            "is applied to task state; terminal sessions are reviewed without changing their state."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Exact PAOS session ID from SESSIONS.md.",
                }
            },
            "required": ["session_id"],
            "additionalProperties": False,
        }

    async def execute(self, session_id: str) -> str:
        outcome = await self.verifier.verify_session(session_id, source="tool")
        return json.dumps(outcome, ensure_ascii=False)
