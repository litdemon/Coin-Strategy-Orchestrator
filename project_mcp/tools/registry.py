from __future__ import annotations

from typing import Dict

from project_mcp.base import Tool


class CommandToolRegistry:
    _registry: Dict[str, Tool] = {}

    @classmethod
    def register(cls, action: str, tool: Tool) -> None:
        cls._registry[action] = tool

    @classmethod
    def get_registry(cls) -> Dict[str, Tool]:
        return cls._registry
