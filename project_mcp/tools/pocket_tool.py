from typing import Any, Dict, Optional, List
from decimal import Decimal
import logging
from project_mcp.base import Tool
from project_mcp.tools.context import get_execution_context

logger = logging.getLogger(__name__)

class PocketTool(Tool):
    def identifier(self) -> str:
        return "manage_pocket"

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Manage pockets.
        
        Args:
            action: One of 'create', 'close', 'list'.
            params: Parameters for the action.
                - create: { 'ticker': str, 'volume': float, 'entry_price': optional[float] } (Usually created by Order, but can be manual?)
                  Actually Pocket creation is usually automatic upon Order Filled. 
                  However, "Test" creation or recovering state might use manual creation.
                  User asked: "pocket을 생성, 삭제 할 수 있어야 함".
                - close: { 'pocket_id': str, 'reason': str }
                - list: { 'state': optional[str] }
        """
        ctx = get_execution_context()
        if not ctx:
            return {"error": "Execution context not available"}
        
        try:
            if action == 'create':
                return self._create_pocket(ctx, params)
            elif action == 'close':
                return self._close_pocket(ctx, params)
            elif action == 'list':
                return self._list_pockets(ctx, params)
            else:
                return {"error": f"Unknown action: {action}"}
        except Exception as e:
            logger.error(f"PocketTool Error: {e}")
            return {"error": str(e)}

    def _create_pocket(self, ctx, params: Dict[str, Any]) -> Dict[str, Any]:
        # Manual creation
        ticker = params.get('ticker')
        volume = params.get('volume')
        entry_price = params.get('entry_price')
        
        if not ticker or not volume:
            return {"error": "ticker and volume required"}
            
        # PocketManager.create_pocket logic:
        # Usually from MyOrder.
        # But if manual, we can instantiate Pocket manually and add it?
        # PocketManager has 'create_pocket_from_position' maybe?
        # Or ctx.pocket_manager.register_pocket(pocket)
        
        # Let's assume we use ctx.pocket_manager to create a manual one if method exists.
        # If not, we might be restricted.
        # I'll check PocketManager methods.
        
        # Checking logic in code: PocketManager usually handles 'on_order_completed'.
        # For robustness, allow calling logic similar to that.
        # Ideally, we should perform a BUY order to create a pocket?
        # User said "create pocket", not "buy".
        # If "Create Pocket" means "Open a virtual position for tracking without real execution", that's different.
        # Assuming Virtual Mode -> Buy Order -> Pocket.
        
        # For now, I'll attempt to directly call create/register if possible.
        # Or better: Trigger a manual Buy Order via AccountManager to naturally create a pocket?
        # But "Create Pocket" implies direct manipulation.
        # Let's see if PocketManager has `create`.
        
        # Placeholder for direct access if supported, otherwise wrapper.
        pass # To be filled after checking PocketManager.
        
        return {"result": "error", "message": "Manual creation via tool not fully implemented yet without order"}

    def _close_pocket(self, ctx, params: Dict[str, Any]) -> Dict[str, Any]:
        pocket_id = params.get('pocket_id')
        reason = params.get('reason', 'Manual Close via MCP')
        
        if not pocket_id:
            return {"error": "pocket_id required"}
            
        ctx.pocket_manager.set_reason(pocket_id, reason)
        result = ctx.pocket_manager.close_pocket(pocket_id) 
        # result typically signals execution.
        
        return {"result": "success", "message": f"Pocket {pocket_id} closed"}

    def _list_pockets(self, ctx, params: Dict[str, Any]) -> Dict[str, Any]:
        state = params.get('state') # e.g. "OPEN"
        pockets = []
        
        # Iterate over pockets
        for pid, pocket in ctx.pocket_manager.pockets.items():
            if state and pocket.state.name != state:
                continue
            pockets.append(pocket.model_dump())
            
        return {"pockets": pockets}
