from typing import Any, Dict, Optional, List
from decimal import Decimal
import logging
from project_mcp.base import Tool
from project_mcp.tools.context import get_execution_context
from strategy.models import StrategyConfig, StrategyType

logger = logging.getLogger(__name__)

class StrategyTool(Tool):
    def identifier(self) -> str:
        return "manage_strategy"

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manage trading strategies.
        
        Args:
            action: One of 'create', 'delete', 'list'.
            params: Parameters for the action.
                - create: { 'ticker': str, 'type': str, 'config': dict, 'pocket_id': optional[str] }
                - delete: { 'strategy_id': str }
                - list: {}
        """
        ctx = get_execution_context()
        if not ctx:
            return {"error": "Execution context not available"}
        
        try:
            if action == 'create':
                return self._create_strategy(ctx, params)
            elif action == 'delete':
                return self._delete_strategy(ctx, params)
            elif action == 'list':
                return self._list_strategies(ctx)
            else:
                return {"error": f"Unknown action: {action}"}
        except Exception as e:
            logger.error(f"StrategyTool Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}

    def _create_strategy(self, ctx, params: Dict[str, Any]) -> Dict[str, Any]:
        ticker = params.get('ticker')
        strategy_type = params.get('type')
        config_dict = params.get('config', {})
        pocket_id = params.get('pocket_id')
        
        if not ticker or not strategy_type:
            return {"error": "ticker and type are required for create"}

        # Construct basic config based on type? 
        # StrategyManager.create_strategy expects a Config object usually, or dict?
        # Let's check StrategyManager.create_strategy signature. 
        # It takes (ticker, strategy_type, config: dict, pocket_id).
        
        strategy_id = ctx.strategy_manager.create_strategy(
            ticker=ticker,
            strategy_type=strategy_type,
            config=config_dict,
            pocket_id=pocket_id
        )
        
        return {"result": "success", "strategy_id": strategy_id, "message": f"Strategy {strategy_type} created for {ticker}"}

    def _delete_strategy(self, ctx, params: Dict[str, Any]) -> Dict[str, Any]:
        strategy_id = params.get('strategy_id')
        if not strategy_id:
            return {"error": "strategy_id required for delete"}
            
        ctx.strategy_manager.stop_strategy(strategy_id)
        # Archive?
        ctx.strategy_manager.archive_strategy(strategy_id)
        
        return {"result": "success", "message": f"Strategy {strategy_id} deleted"}

    def _list_strategies(self, ctx) -> Dict[str, Any]:
        strategies = []
        for sid, strategy in ctx.strategy_manager.strategies.items():
            strategies.append({
                "id": sid,
                "name": strategy.config.name,
                "ticker": strategy.context.ticker,
                "pocket_id": strategy.context.pocket_id,
                "active": True # If in manager, it's active
            })
        return {"strategies": strategies}
