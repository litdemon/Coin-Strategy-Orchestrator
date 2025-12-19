from project_mcp.base import Prompt

class ReviewPrompt(Prompt):
    def get(self, code: str) -> str:
        """Create a prompt for code review."""
        return f"Please review the following code and identify potential bugs and improvements:\n\n{code}"
