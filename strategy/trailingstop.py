
from decimal import Decimal
from typing import Optional, Dict, Any, Type
from strategy.base import StrategyBase
from strategy.models import StrategyContext, StrategyConfig, Signal, SignalType

class TrailingStopConfig(StrategyConfig):
    strategy_type: str = "trailing_stop"
    trail_percent: Decimal  # 0.05 = 5%
    activation_percent: Optional[Decimal] = None
    entry_price: Decimal # Required to calculate profit for activation

    class Config:
        arbitrary_types_allowed = True


class TrailingStopStrategy(StrategyBase):
    """Trailing Stop Strategy Implementation."""
    
    # Class attribute to help Manager identify config model
    ConfigModel = TrailingStopConfig

    def __init__(self, context: StrategyContext, config: TrailingStopConfig):
        super().__init__(context, config)
        self.config: TrailingStopConfig = config # Type hinting
        
        # State
        self.highest_price: Optional[Decimal] = None
        self.stop_price: Optional[Decimal] = None
        self.activated: bool = False

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        # Update highest price
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
            
            # Check Activation
            if self.config.activation_percent:
                profit_percent = (current_price - self.config.entry_price) / self.config.entry_price
                if not self.activated and profit_percent >= self.config.activation_percent:
                    self.activated = True
            else:
                self.activated = True
            
            # Update Stop Price
            if self.activated:
                self.stop_price = self.highest_price * (Decimal("1") - self.config.trail_percent)

        # Check Stop Condition
        if self.activated and self.stop_price and current_price <= self.stop_price:
            return self.emit_signal(Signal(
                type=SignalType.CLOSE_POSITION,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                reason=f"Trailing stop triggered at {current_price}",
                data={
                    "stop_price": self.stop_price, 
                    "highest_price": self.highest_price
                }
            ))
        
        return None

    def get_state(self) -> Dict[str, Any]:
        return {
            "highest_price": str(self.highest_price) if self.highest_price else None,
            "stop_price": str(self.stop_price) if self.stop_price else None,
            "activated": self.activated
        }

    def restore_state(self, state: Dict[str, Any]):
        self.highest_price = Decimal(state["highest_price"]) if state.get("highest_price") else None
        self.stop_price = Decimal(state["stop_price"]) if state.get("stop_price") else None
        self.activated = state.get("activated", False)


class TakeProfitConfig(StrategyConfig):
    strategy_type: str = "take_profit"
    entry_price: Decimal
    target_percent: Decimal
    partial: bool = False
    partial_ratio: Decimal = Decimal("0.5")

    class Config:
        arbitrary_types_allowed = True

class TakeProfitStrategy(StrategyBase):
    ConfigModel = TakeProfitConfig

    def __init__(self, context: StrategyContext, config: TakeProfitConfig):
        super().__init__(context, config)
        self.config: TakeProfitConfig = config
        self.triggered = False

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        if self.triggered:
            return None
            
        profit_percent = (current_price - self.config.entry_price) / self.config.entry_price
        
        if profit_percent >= self.config.target_percent:
            self.triggered = True
            
            signal_type = SignalType.PARTIAL_CLOSE if self.config.partial else SignalType.CLOSE_POSITION
            data = {"price": current_price}
            if self.config.partial:
                data["close_ratio"] = self.config.partial_ratio
                
            return self.emit_signal(Signal(
                type=signal_type,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                reason=f"Take profit at {profit_percent:.2%}",
                data=data
            ))
            
        return None

    def get_state(self) -> Dict[str, Any]:
        return {"triggered": self.triggered}

    def restore_state(self, state: Dict[str, Any]):
        self.triggered = state.get("triggered", False)

class StopLossConfig(StrategyConfig):
    strategy_type: str = "stop_loss"
    entry_price: Decimal
    stop_percent: Decimal

    class Config:
        arbitrary_types_allowed = True

class StopLossStrategy(StrategyBase):
    ConfigModel = StopLossConfig

    def __init__(self, context: StrategyContext, config: StopLossConfig):
        super().__init__(context, config)
        self.config: StopLossConfig = config
        self.stop_price: Optional[Decimal] = None

    def on_tick(self, current_price: Decimal) -> Optional[Signal]:
        if self.stop_price is None:
            self.stop_price = self.config.entry_price * (Decimal("1") - self.config.stop_percent)
            
        if current_price <= self.stop_price:
            return self.emit_signal(Signal(
                type=SignalType.CLOSE_POSITION,
                strategy_id=self.context.strategy_id,
                ticker=self.context.ticker,
                reason=f"Stop loss triggered at {current_price}",
                data={"stop_price": self.stop_price}
            ))
        return None

    def get_state(self) -> Dict[str, Any]:
        return {"stop_price": str(self.stop_price) if self.stop_price else None}

    def restore_state(self, state: Dict[str, Any]):
        self.stop_price = Decimal(state["stop_price"]) if state.get("stop_price") else None
