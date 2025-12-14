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
import time
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
        self.positions: Dict[str, Position] = { p.id: p for p in Position.load_all(self.db_path) if not p.is_closed }

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

    def on_order_fill(self, order_info: dict):
        """
        Handle order fill events (both buy and sell).
        """
        ticker = order_info.get('code')
        side = order_info.get('ask_bid') # 'bid' or 'ask'
        state = order_info.get('state')
        
        # Ensure we have price and volume. 
        # Upbit socket might send 'price' or 'trade_price'? 
        # main.py extracts 'price' and 'volume'.
        price = order_info.get('price', 0.0)
        volume = order_info.get('volume', 0.0)

        if state != 'done':
            return

        if side == 'bid':
            # Buy order filled -> Create Position
            if price > 0 and volume > 0:
                 self.create_position(ticker, price, volume)

        elif side == 'ask':
            # Sell order filled -> Close Position
            # Strategy: Find active position for this ticker and close it.
            # Assuming FIFO for now if multiple positions exist.
            active_positions = self.get_positions(ticker, only_active=True)
            if active_positions:
                # Close the first one
                # TODO: In future, match exact volume or order ID if possible.
                pos = active_positions[0]
                pos.status = "closed"
                pos.close_price = price
                pos.close_time = time.time()
                pos.save(self.db_path)
                
                # Update local cache
                self.positions[pos.id] = pos
                logger.info(f"[PositionManager] Closed Position {pos.id} for {ticker}")