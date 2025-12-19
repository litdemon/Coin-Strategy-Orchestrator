from project_mcp.base import Tool

class AddTool(Tool):
    def execute(self, a: float, b: float) -> float:
        """Add two numbers"""
        return a + b
