
from decimal import Decimal
from typing import Optional, Dict, Any, Type
from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType, StrategyType

class DefaultStrategyConfig(StrategyConfig):
    name: str = "default"
    type: StrategyType = StrategyType.SELL
    entry_price: Decimal
    
    # Trailing Stop
    trail_percent: Optional[Decimal] = None
    activation_percent: Optional[Decimal] = None
    
    # Stop Loss
    stop_loss_percent: Optional[Decimal] = None
    
    # Take Profit
    take_profit_percent: Optional[Decimal] = None
    take_profit_partial: bool = False
    take_profit_ratio: Decimal = Decimal("0.5")

    class Config:
        arbitrary_types_allowed = True


class DefaultStrategy(StrategyBase):
    """
    Default Strategy combining Trailing Stop, Stop Loss, and Take Profit.
    Priority: Stop Loss > Take Profit > Trailing Stop
    """
    ConfigModel = DefaultStrategyConfig

    def __init__(self, context: StrategyContext, config: DefaultStrategyConfig):
        super().__init__(context, config)
        self.config: DefaultStrategyConfig = config
        
        # State
        self.highest_price: Optional[Decimal] = None
        self.stop_price: Optional[Decimal] = None
        self.activated: bool = False # For Trailing Stop
        self.tp_triggered: bool = False
        
        # Initial Stop Loss calculation (static)
        self.sl_price: Optional[Decimal] = None
        if self.config.stop_loss_percent:
             self.sl_price = self.config.entry_price * (Decimal("1") - self.config.stop_loss_percent)

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        # 1. Stop Loss Check
        if self.sl_price and current_price <= self.sl_price:
            return self.emit_signal(Signal(
                type=SignalType.CLOSE_POCKET,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                reason=f"Stop Loss triggered at {current_price}",
                data={"stop_price": self.sl_price}
            ))

        # 2. Take Profit Check
        if self.config.take_profit_percent and not self.tp_triggered:
            profit_percent = (current_price - self.config.entry_price) / self.config.entry_price
            if profit_percent >= self.config.take_profit_percent:
                self.tp_triggered = True
                signal_type = SignalType.PARTIAL_CLOSE if self.config.take_profit_partial else SignalType.CLOSE_POCKET
                data = {"price": current_price}
                if self.config.take_profit_partial:
                    data["close_ratio"] = self.config.take_profit_ratio

                return self.emit_signal(Signal(
                    type=signal_type,
                    strategy_id=self.context.strategy_id,
                    ticker=self.context.ticker,
                    reason=f"Take Profit at {profit_percent:.2%}",
                    data=data
                ))

        # 3. Trailing Stop Logic
        if self.config.trail_percent:
             # Update highest price
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price
                
                # Check Activation
                if self.config.activation_percent:
                    profit_percent = (current_price - self.config.entry_price) / self.config.entry_price
                    if not self.activated and profit_percent >= self.config.activation_percent:
                        self.activated = True
                else:
                    self.activated = True # Always active if no activation percent
                
                # Update Stop Price
                if self.activated:
                    self.stop_price = self.highest_price * (Decimal("1") - self.config.trail_percent)

            # Update Display
            self._update_display()

            # Check Stop Condition
            if self.activated and self.stop_price and current_price <= self.stop_price:
                return self.emit_signal(Signal(
                    type=SignalType.CLOSE_POCKET,
                    strategy_id=self.context.strategy_id,
                    ticker=self.context.ticker,
                    reason=f"Trailing Stop triggered at {current_price}",
                    data={
                        "pocket_id": self.context.pocket_id,
                        "stop_price": self.stop_price, 
                        "highest_price": self.highest_price
                    }
                ))

        return None

    def _update_display(self):
        parts = []
        if self.sl_price:
            parts.append(f"SL:{self.sl_price:.0f}")
        if self.config.take_profit_percent and not self.tp_triggered:
             tp_price = self.config.entry_price * (1 + self.config.take_profit_percent)
             parts.append(f"TP:{tp_price:.0f}")
        
        if self.config.trail_percent:
            if self.stop_price:
                parts.append(f"TS:{self.stop_price:.0f}")
            elif self.highest_price:
                 parts.append(f"High:{self.highest_price:.0f}")
            else:
                 parts.append("TS:Init")
        
        new_display = " ".join(parts)
        if self.display != new_display:
            self.display = new_display
            self.is_updated = True

    def get_state(self) -> Dict[str, Any]:
        return {
            "highest_price": str(self.highest_price) if self.highest_price else None,
            "stop_price": str(self.stop_price) if self.stop_price else None,
            "activated": self.activated,
            "tp_triggered": self.tp_triggered
        }

    def restore_state(self, state: Dict[str, Any]):
        self.highest_price = Decimal(state["highest_price"]) if state.get("highest_price") else None
        self.stop_price = Decimal(state["stop_price"]) if state.get("stop_price") else None
        self.activated = state.get("activated", False)
        self.tp_triggered = state.get("tp_triggered", False)
