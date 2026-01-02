from project_mcp.base import Prompt

class StrategyManagementPrompt(Prompt):
    def identifier(self) -> str:
        return "manage_strategy_help"

    def get(self, arguments: dict) -> str:
        return """
        Use the 'manage_strategy' tool to create, apply, or delete trading strategies.
        
        Available Actions:
        1. create: Create a new strategy instance.
           - ticker: (Required) Target coin ticker (e.g., KRW-BTC)
           - type: (Required) Strategy Type (e.g., "default", "volume_spike", "anomaly_detection", "dl_anomaly_detection")
           - config: (Optional) Configuration dictionary overrides.
           - pocket_id: (Optional) Associate with existing pocket.
           
        2. delete: Stop and archive a strategy.
           - strategy_id: (Required) ID of the strategy.
           
        3. list: List all active strategies.
        
        Example:
        {
            "action": "create",
            "params": {
                "ticker": "KRW-BTC",
                "type": "anomaly_detection",
                "config": {"period": 60, "z_score_threshold": 2.5}
            }
        }
        """
