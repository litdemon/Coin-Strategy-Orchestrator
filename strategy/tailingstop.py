

from strategy.base import StrategyBase, Signal, SignalType, StrategyConfig
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from models.position import Position


class TrailingStopConfig(StrategyConfig):
    strategy_type: str = "trailing_stop"
    trail_percent: float  # 추적 퍼센트 (0.05 = 5%)
    activation_percent: Optional[float] = None  # 활성화 조건


class TrailingStopStrategy(StrategyBase):
    """트레일링 스탑 전략"""
    
    def __init__(self, position_id: str, config: TrailingStopConfig):
        super().__init__(position_id, config)
        self.highest_price: Optional[float] = None
        self.stop_price: Optional[float] = None
        self.activated: bool = False
    
    def update(self, current_price: float, position: 'Position') -> Optional[Signal]:
        config: TrailingStopConfig = self.config
        
        # 최고가 업데이트
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
            
            # 활성화 조건 체크
            if config.activation_percent:
                profit_percent = (current_price - position.entry_price) / position.entry_price
                if not self.activated and profit_percent >= config.activation_percent:
                    self.activated = True
            else:
                self.activated = True
            
            # 스탑 가격 업데이트
            if self.activated:
                self.stop_price = self.highest_price * (1 - config.trail_percent)
        
        # 스탑 조건 체크
        if self.activated and self.stop_price and current_price <= self.stop_price:
            return self.emit_signal(Signal(
                type=SignalType.CLOSE,
                position_id=self.position_id,
                reason=f"Trailing stop triggered at {current_price}",
                data={"stop_price": self.stop_price, "highest_price": self.highest_price}
            ))
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_type": "trailing_stop",
            "position_id": self.position_id,
            "config": self.config.model_dump(),
            "state": {
                "highest_price": self.highest_price,
                "stop_price": self.stop_price,
                "activated": self.activated
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrailingStopStrategy':
        config = TrailingStopConfig(**data["config"])
        strategy = cls(data["position_id"], config)
        
        # 상태 복원
        state = data.get("state", {})
        strategy.highest_price = state.get("highest_price")
        strategy.stop_price = state.get("stop_price")
        strategy.activated = state.get("activated", False)
        
        return strategy


class TakeProfitConfig(StrategyConfig):
    strategy_type: str = "take_profit"
    target_percent: float  # 목표 수익률
    partial: bool = False  # 부분 청산 여부
    partial_ratio: float = 0.5  # 부분 청산 비율


class TakeProfitStrategy(StrategyBase):
    """이익 실현 전략"""
    
    def __init__(self, position_id: str, config: TakeProfitConfig):
        super().__init__(position_id, config)
        self.triggered = False
    
    def update(self, current_price: float, position: 'Position') -> Optional[Signal]:
        if self.triggered:
            return None
        
        config: TakeProfitConfig = self.config
        profit_percent = (current_price - position.entry_price) / position.entry_price
        
        if profit_percent >= config.target_percent:
            self.triggered = True
            
            if config.partial:
                return self.emit_signal(Signal(
                    type=SignalType.PARTIAL_CLOSE,
                    position_id=self.position_id,
                    reason=f"Take profit at {profit_percent:.2%}",
                    data={"close_ratio": config.partial_ratio, "price": current_price}
                ))
            else:
                return self.emit_signal(Signal(
                    type=SignalType.CLOSE,
                    position_id=self.position_id,
                    reason=f"Take profit at {profit_percent:.2%}",
                    data={"price": current_price}
                ))
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_type": "take_profit",
            "position_id": self.position_id,
            "config": self.config.model_dump(),
            "state": {"triggered": self.triggered}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TakeProfitStrategy':
        config = TakeProfitConfig(**data["config"])
        strategy = cls(data["position_id"], config)
        strategy.triggered = data.get("state", {}).get("triggered", False)
        return strategy


class StopLossConfig(StrategyConfig):
    strategy_type: str = "stop_loss"
    stop_percent: float  # 손절 퍼센트


class StopLossStrategy(StrategyBase):
    """손절 전략"""
    
    def __init__(self, position_id: str, config: StopLossConfig):
        super().__init__(position_id, config)
        self.stop_price: Optional[float] = None
    
    def update(self, current_price: float, position: 'Position') -> Optional[Signal]:
        config: StopLossConfig = self.config
        
        if self.stop_price is None:
            self.stop_price = position.entry_price * (1 - config.stop_percent)
        
        if current_price <= self.stop_price:
            return self.emit_signal(Signal(
                type=SignalType.CLOSE,
                position_id=self.position_id,
                reason=f"Stop loss triggered at {current_price}",
                data={"stop_price": self.stop_price}
            ))
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_type": "stop_loss",
            "position_id": self.position_id,
            "config": self.config.model_dump(),
            "state": {"stop_price": self.stop_price}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StopLossStrategy':
        config = StopLossConfig(**data["config"])
        strategy = cls(data["position_id"], config)
        strategy.stop_price = data.get("state", {}).get("stop_price")
        return strategy
