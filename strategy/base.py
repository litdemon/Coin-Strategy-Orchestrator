from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from strategy.models import StrategyContext, StrategyConfig, Signal

class StrategyBase(ABC):
    """Abstract Base Class for all trading strategies."""
    
    
    def __init__(self, context: StrategyContext, config: StrategyConfig):
        self.context = context
        self.config = config
        self.signals: list[Signal] = []
        self.display: str = "Nothing"
        self.is_updated: bool = False

    @abstractmethod
    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        """
        Called when price updates.
        Should return a Signal if an action is required, or None.
        """
        pass

    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """
        Return the current state of the strategy as a dictionary.
        This will be saved to the database.
        """
        pass

    @abstractmethod
    def restore_state(self, state: Dict[str, Any]):
        """
        Restore the strategy state from a dictionary.
        """
        pass

    def on_schedule(self):
        """
        Called when the execution interval is reached.
        Strategies can implement this for time-based logic.
        """
        pass

    def on_orderbook(self, orderbook: Dict[str, Any]) -> Optional[Signal]:
        """
        Called when orderbook updates.
        Should return a Signal if an action is required, or None.
        """
        pass

    def summary(self):
        return {
            'strategy_id': self.context.strategy_id,
            'name': self.config.name,
            'type': self.config.type,
            'status': 'ACTIVE',
            'config': self.config.model_dump(),
            'pocket_id': self.context.pocket_id,
            'ticker': self.context.ticker,
            'display': self.display
        }

    def emit_signal(self, signal: Signal) -> Signal:
        """Helper to emit a signal."""
        # Enforce strategy_id and ticker consistency
        signal.strategy_id = self.context.strategy_id
        signal.ticker = self.context.ticker
        self.signals.append(signal)
        return signal
