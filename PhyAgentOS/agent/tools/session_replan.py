"""Atomic Agent recovery tool."""

from __future__ import annotations

import json
from typing import Any

from PhyAgentOS.agent.tools.base import Tool
from PhyAgentOS.runtime.watchdog.registry import SessionRegistry


class CreateReplannedSessionTool(Tool):
    def __init__(self, registry: SessionRegistry) -> None:
        self.registry = registry

    @property
    def name(self) -> str:
        return "create_replanned_session"

    @property
    def description(self) -> str:
        return (
            "Atomically create a fresh child session for a parent in awaiting_replan. "
            "Submit a newly planned task description and the complete runtime hints; old Gateway "
            "command IDs are always discarded."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "parent_session_id": {"type": "string", "minLength": 1},
                "task_description": {"type": "string", "minLength": 1},
                "runtime_hints": {
                    "type": "object",
                    "description": (
                        "Complete SessionRuntimeHints object, including a newly planned gateway_action "
                        "when the target uses Forge. Do not include command_id."
                    ),
                    "properties": {
                        "perception_queries": {"type": "array", "items": {"type": "object"}},
                        "force_environment_refresh": {"type": "boolean"},
                        "preferred_replan_every_steps": {"type": "integer"},
                        "gateway_action": {"type": "object"},
                    },
                    "required": [
                        "perception_queries",
                        "force_environment_refresh",
                        "preferred_replan_every_steps",
                        "gateway_action",
                    ],
                },
            },
            "required": ["parent_session_id", "task_description", "runtime_hints"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        parent_session_id: str,
        task_description: str,
        runtime_hints: dict[str, Any],
    ) -> str:
        child = self.registry.create_replanned_session(
            parent_session_id,
            task_description=task_description,
            runtime_hints=runtime_hints,
        )
        return json.dumps(
            {
                "ok": True,
                "parent_session_id": parent_session_id,
                "child_session_id": child.session_id,
                "status": child.status.value,
            },
            ensure_ascii=False,
        )
