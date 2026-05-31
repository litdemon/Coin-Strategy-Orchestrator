from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import Field

from strategy.base import StrategyBase
from strategy.models import Signal, SignalType, StrategyConfig, StrategyContext, StrategyType


class TrailingStopConfig(StrategyConfig):
    name: str = "trailing_stop"
    type: StrategyType = StrategyType.SELL
    entry_price: Decimal = Field(default=Decimal("0"))
    trail_percent: Decimal = Field(default=Decimal("0.05"))


class TrailingStopStrategy(StrategyBase):
    """
    Closes the pocket when price drops more than trail_percent below
    the highest observed price since entry.
    """

    ConfigModel = TrailingStopConfig

    def __init__(self, context: StrategyContext, config: TrailingStopConfig):
        super().__init__(context, config)
        self.highest_price: Decimal = config.entry_price
        self.display = f"Trail {config.trail_percent * 100:.1f}%"

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        price = Decimal(str(current_price))
        if price > self.highest_price:
            self.highest_price = price

        trail_percent = self.config.trail_percent
        stop_price = self.highest_price * (1 - trail_percent)
        self.display = f"High:{self.highest_price:.0f} Stop:{stop_price:.0f}"

        if price < stop_price:
            return Signal(
                type=SignalType.CLOSE_POCKET,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                price=price,
                reason=f"trail stop hit: {price} < {stop_price:.0f}",
            )
        return None

    def get_state(self) -> Dict[str, Any]:
        return {
            "highest_price": str(self.highest_price),
            "entry_price": str(self.config.entry_price),
            "trail_percent": str(self.config.trail_percent),
        }

    def restore_state(self, state: Dict[str, Any]):
        self.highest_price = Decimal(state.get("highest_price", str(self.config.entry_price)))
