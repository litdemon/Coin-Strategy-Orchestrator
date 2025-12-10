import sqlite3
import json
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from typing import Optional, List, Dict, Any, Callable
from models.position import Position
from src.stratege_manager import StrategyManager, StrategyFactory
from strategy.base import Signal
import pyupbit
import logging
from tools.db_interface import DBInterface

logger = logging.getLogger(__name__)

class PositionEx(Position, DBInterface):
    
    # Strategy 직렬화된 데이터 저장
    strategies_data: Optional[List[Dict[str, Any]]] = None
    
    # Strategy Manager (DB에 저장되지 않음)
    _strategy_manager: Optional[StrategyManager] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    @property
    def strategy_manager(self) -> StrategyManager:
        """Strategy Manager 접근 (lazy initialization)"""
        if self._strategy_manager is None:
            self._strategy_manager = StrategyManager(self)
            self._strategy_manager.load_strategies()
        return self._strategy_manager
    
    def add_strategy(self, strategy_type: str, config: Dict[str, Any]):
        """Strategy 추가 편의 메서드"""
        strategy = StrategyFactory.create(strategy_type, self.id, config)
        self.strategy_manager.add_strategy(strategy)
    
    def update_price(self, current_price: float) -> List[Signal]:
        """가격 업데이트 및 Signal 반환"""
        # 최고가 업데이트
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
        
        # Strategy 업데이트
        return self.strategy_manager.update(current_price)
    
    @property
    def is_closed(self) -> bool:
        return self.status == "closed"

class PositionObserver(ABC):
    @abstractmethod
    def on_position_updated(self, position: PositionEx, signals: List[Signal]):
        pass

class PositionManager:
    def __init__(self, db_path: str = "account.db"):
        self.db_path = db_path
        self.positions: List[PositionEx] = PositionEx.load_all(self.db_path)

    def create_if_not_exists(self, ticker, entry_price, volume):
        """
        Initializes positions based on current balance and active tickers.
        """
        default_rate = 0.25  # 25%
        # self.positions 에 없는 것만 추가
        # Check if active position exists for this ticker
        if ticker in [pos.ticker for pos in self.get_active_positions()]:
            return

        if volume * entry_price < 5000: # Min order amount check roughly
            return

        pos = self.default_position(ticker, entry_price, volume)
        logger.info(f"[PositionManager] Auto-added Position: {pos.ticker} {pos.volume * pos.entry_price:,.0f} with TrailingStop")

    def default_position(self, ticker: str, entry_price: float, volume: float):
        """
        Handles filled orders to create new positions.
        """
        
        pos = PositionEx(ticker=ticker, entry_price=entry_price, volume=volume)    
        pos.add_strategy("trailing_stop", {
                "trail_percent": 0.05,        # 5% trailing
                "activation_percent": 0.01    # Activate after 1% profit
            })
        self.positions.append(pos)
        pos.save(self.db_path)
        logger.info(f"[PositionManager] Created Position from Order: {pos.ticker}")
        return pos
    
    def update_all(self, current_prices: Dict[str, float]) -> bool:
        """
        Updates all active positions with current price and triggers strategy checks.
        Returns True if any position triggered a signal (asking for UI update).
        """
        updated = False
        for pos in self.positions:
            if pos.status == "closed":
                continue
            # Get current price
            current_price = current_prices.get(pos.ticker)
            if current_price == 0:
                continue

            # Update position price and check mechanisms
            signals = pos.update_price(current_price)
            if signals:
                self.on_position_updated(pos, signals)
                updated = True
        return updated

    def get_active_positions(self) -> List[PositionEx]:
        return [p for p in self.positions if not p.is_closed]