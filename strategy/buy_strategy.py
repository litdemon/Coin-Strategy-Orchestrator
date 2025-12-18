from decimal import Decimal
from typing import Optional, Dict, Any, Type
import time
from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType

class BuyStrategyConfig(StrategyConfig):
    strategy_type: str = "buy_strategy"
    buy_amount: Decimal
    execution_interval: int = 60 # seconds
    
    class Config:
        arbitrary_types_allowed = True

class BuyStrategy(StrategyBase):
    """
    Simple Buy Strategy that executes periodically or based on conditions.
    This creates new positions (Pocket-less strategy).
    """
    ConfigModel = BuyStrategyConfig

    def __init__(self, context: StrategyContext, config: BuyStrategyConfig):
        super().__init__(context, config)
        self.config: BuyStrategyConfig = config
        self.last_execution_time: float = 0

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        # Buy strategy might ignore ticks if it's purely time-based
        # Or it could check price thresholds here.
        return None

    def on_schedule(self):
        """Called by Manager's schedule loop."""
        current_time = time.time()
        
        # Check if enough time has passed (redundant if Manager handles it, but safe)
        if current_time - self.last_execution_time >= self.config.execution_interval:
            self.last_execution_time = current_time
            
            # Emit Buy Signal
            return self.emit_signal(Signal(
                type=SignalType.BUY,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                amount=self.config.buy_amount,
                reason="Scheduled Buy Execution"
            ))

    def get_state(self) -> Dict[str, Any]:
        return {
            "last_execution_time": self.last_execution_time
        }

    def restore_state(self, state: Dict[str, Any]):
        self.last_execution_time = state.get("last_execution_time", 0)
