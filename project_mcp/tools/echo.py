from project_mcp.base import Tool

class EchoTool(Tool):
    def execute(self, message: str) -> str:
        """Echo back the message"""
        return f"Echo: {message}"
