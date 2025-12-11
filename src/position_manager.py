import sqlite3
import json
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from typing import Optional, List, Dict, Any, Callable
from models.position import PositionBase
from strategy.base import Signal
import pyupbit
import logging
from tools.db_interface import DBInterface

logger = logging.getLogger(__name__)

class Position(PositionBase, DBInterface):

    class Config:
        arbitrary_types_allowed = True
    
    @property
    def is_closed(self) -> bool:
        return self.status == "closed"

class PositionManager:
    def __init__(self, db_path: str = "account.db"):
        self.db_path = db_path
        Position.init_db(self.db_path)
        self.positions: Dict[str, Position] = { p.id: p for p in Position.load_all(self.db_path) }

    def create_position(self, ticker: str, entry_price: float, volume: float):
        """
        Handles filled orders to create new positions.
        """
        
        pos = Position(ticker=ticker, entry_price=entry_price, volume=volume)    
        self.positions[pos.id] = pos
        pos.save(self.db_path)
        logger.info(f"[PositionManager] Created Position from Order: {pos.ticker}")
        return pos

    def get_positions(self, ticker:str, only_active:bool = True) -> List[Position]:
        if only_active:
            return [p for p in self.positions.values() if p.ticker == ticker and not p.is_closed]
        return [p for p in self.positions.values() if p.ticker == ticker]
    
    def get_position(self, pid:str) -> Optional[Position]:
        return self.positions.get(pid)