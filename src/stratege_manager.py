import sys
import os
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.base import StrategyBase, Signal, SignalType, StrategyConfig
from typing import Optional, Dict, Any, List
from models.position import PositionBase
from strategy.tailingstop import TrailingStopStrategy, TakeProfitStrategy, StopLossStrategy
from strategy.tailingstop import TrailingStopConfig, TakeProfitConfig, StopLossConfig


# ============= Strategy Factory =============

class StrategyFactory:
    """Strategy 생성 및 복원을 위한 팩토리"""
    
    _strategies = {
        "trailing_stop": TrailingStopStrategy,
        "take_profit": TakeProfitStrategy,
        "stop_loss": StopLossStrategy,
    }
    
    _config_map = {
        "trailing_stop": TrailingStopConfig,
        "take_profit": TakeProfitConfig,
        "stop_loss": StopLossConfig,
    }

    @classmethod
    def create(cls, strategy_type: str, position_id: str, config: Dict[str, Any]) -> StrategyBase:
        """새 Strategy 생성"""
        if strategy_type not in cls._strategies:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        strategy_class = cls._strategies[strategy_type]
        config_class = cls._config_map.get(strategy_type)
        
        if not config_class:
             # Fallback if config class not mapped (should not happen for known types)
             raise ValueError(f"Config class not found for {strategy_type}")

        config_obj = config_class(**config)
        return strategy_class(position_id, config_obj)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StrategyBase:
        """저장된 데이터에서 Strategy 복원"""
        strategy_type = data["strategy_type"]
        if strategy_type not in cls._strategies:
            raise ValueError(f"Unknown strategy type: {strategy_type}")
        
        return cls._strategies[strategy_type].from_dict(data)
    
    @classmethod
    def register(cls, strategy_type: str, strategy_class: type, config_class: type = None):
        """새로운 Strategy 등록"""
        cls._strategies[strategy_type] = strategy_class
        if config_class:
            cls._config_map[strategy_type] = config_class


class StrategyManager:
    """Position의 Strategy들을 관리"""
    
    def __init__(self, position: PositionBase):
        self.position = position
        self.strategies: List[StrategyBase] = []
        self._load_strategies()
    
    def _load_strategies(self):
        """Position에서 Strategy 복원"""
        if self.position.strategies_data:
            for data in self.position.strategies_data:
                strategy = StrategyFactory.from_dict(data)
                self.strategies.append(strategy)
    
    def add_strategy(self, strategy: StrategyBase):
        """Strategy 추가"""
        self.strategies.append(strategy)
        self._save_strategies()
    
    def remove_strategy(self, strategy_type: str):
        """Strategy 제거"""
        self.strategies = [s for s in self.strategies if s.config.strategy_type != strategy_type]
        self._save_strategies()
    
    def update(self, current_price: float) -> List[Signal]:
        """모든 Strategy 업데이트"""
        signals = []
        for strategy in self.strategies:
            signal = strategy.update(current_price, self.position)
            if signal:
                signals.append(signal)
        
        # 상태 변경 시 저장
        if signals:
            self._save_strategies()
        
        return signals
    
    def _save_strategies(self):
        """Strategy 상태를 Position에 저장"""
        self.position.strategies_data = [s.to_dict() for s in self.strategies]
    
    def get_strategy(self, strategy_type: str) -> Optional[StrategyBase]:
        """특정 타입의 Strategy 조회"""
        for strategy in self.strategies:
            if strategy.config.strategy_type == strategy_type:
                return strategy
        return None
