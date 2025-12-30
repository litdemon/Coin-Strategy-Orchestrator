from __future__ import annotations

import re
from typing import Any, Dict

from project_mcp.base import Tool
from project_mcp.tools.context import get_execution_context
from project_mcp.tools.registry import CommandToolRegistry


class CommandRouterTool(Tool):
    _uuid_pattern = re.compile(r"[a-fA-F0-9-]{6,36}")

    def __init__(self) -> None:
        self.registered_tools = CommandToolRegistry.get_registry()

    def execute(self, topic: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        action = data.get("action")
        if not action:
            raise ValueError("action is required")

        uuid = self._extract_uuid(topic)
        context.dashboard.log(f"Command Received: {action}")

        tool = self.registered_tools.get(action)
        if not tool:
            raise ValueError(f"Unknown action: {action}")

        try:
            response = tool.execute(uuid=uuid, data=data)
            return response or {}
        except Exception as exc:  # parity with legacy behavior
            context.dashboard.log(f"Command failed: {exc}")
            raise

    @classmethod
    def _extract_uuid(cls, topic: str) -> str:
        match = cls._uuid_pattern.search(topic)
        if not match:
            raise ValueError(f"Topic '{topic}' missing command uuid")
        return match.group(0)
