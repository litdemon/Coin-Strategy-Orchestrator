from typing import Any, Dict, Optional, List
from decimal import Decimal, InvalidOperation
import logging
from project_mcp.base import Tool
from project_mcp.tools.context import get_execution_context
from strategy.models import StrategyConfig, StrategyType

logger = logging.getLogger(__name__)

VALID_STRATEGY_NAMES = [
    "default", "scalping_strategy", "volume_spike_strategy",
    "anomaly_detection", "dl_anomaly_detection", "trailing_stop",
]

class StrategyTool(Tool):
    def identifier(self) -> str:
        return "manage_strategy"

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manage trading strategies.

        Args:
            action: One of 'create', 'delete', 'list'.
            params: Parameters for the action.
                - create: {
                    'name': str,           # strategy impl name (e.g. "scalping_strategy")
                    'ticker': str,         # e.g. "KRW-BTC"
                    'type': str,           # "buy" or "sell"
                    'budget': str|number,  # KRW budget amount
                    'config': dict,        # optional extra config
                    'pocket_id': str,      # optional
                  }
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
                return {"error": f"Unknown action: {action}. Valid actions: create, delete, list"}
        except Exception as e:
            logger.error(f"StrategyTool Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}

    def _create_strategy(self, ctx, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get('name', 'scalping_strategy')
        ticker = params.get('ticker')
        strategy_type_str = params.get('type', 'buy')
        budget_raw = params.get('budget', '0')
        config_dict = params.get('config', {})
        pocket_id = params.get('pocket_id')

        if not ticker:
            return {"error": "'ticker' is required for create (e.g. 'KRW-BTC')"}
        if name not in VALID_STRATEGY_NAMES:
            return {"error": f"Unknown strategy name '{name}'. Valid names: {VALID_STRATEGY_NAMES}"}

        try:
            budget = Decimal(str(budget_raw))
        except InvalidOperation:
            return {"error": f"Invalid budget value: {budget_raw!r}"}
        if budget <= 0:
            return {"error": "'budget' must be a positive number (KRW amount)"}

        try:
            strategy_type = StrategyType(strategy_type_str.lower())
        except ValueError:
            return {"error": f"Invalid type '{strategy_type_str}'. Valid values: 'buy', 'sell'"}

        # Merge mandatory config fields
        merged_config = {"name": name, "type": strategy_type.value, **config_dict}

        strategy_id = ctx.strategy_manager.create_strategy(
            name=name,
            type=strategy_type,
            ticker=ticker,
            budget=budget,
            config=merged_config,
            pocket_id=pocket_id,
        )

        return {
            "result": "success",
            "strategy_id": strategy_id,
            "message": f"Strategy '{name}' ({strategy_type.value}) created for {ticker}",
        }

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
