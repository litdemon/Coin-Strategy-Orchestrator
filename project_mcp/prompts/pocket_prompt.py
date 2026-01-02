from project_mcp.base import Prompt

class PocketManagementPrompt(Prompt):
    def identifier(self) -> str:
        return "manage_pocket_help"

    def get(self, arguments: dict) -> str:
        return """
        Use the 'manage_pocket' tool to manage trade pockets (positions).
        
        Available Actions:
        1. create: (Experimental) Manually register a pocket.
           - ticker: (Required)
           - volume: (Required)
           
        2. close: Signal to close a pocket (Sell).
           - pocket_id: (Required)
           - reason: (Optional) Reason for closing.
           
        3. list: View active pockets.
           - state: (Optional) Filter by state (OPEN, CLOSED).
        
        Example:
        {
            "action": "close",
            "params": {
                "pocket_id": "uuid-string",
                "reason": "Manual intervention via AI Agent"
            }
        }
        """
