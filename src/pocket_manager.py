
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import time
import logging
import sqlite3
import pyupbit
from decimal import Decimal

# Add project root to sys.path


from typing import Optional, List, Dict, Any, Callable
from models.pocket import PocketBase
from strategy.base import Signal
from tools.db_interface import DBInterface
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class Pocket(PocketBase, DBInterface):

    class Config:
        arbitrary_types_allowed = True
    
    @property
    def is_closed(self) -> bool:
        return self.status == "closed"

class PocketObserver(ABC):
    @abstractmethod
    def on_pocket_loaded(self, pocket: Pocket):
        pass

    @abstractmethod
    def on_pocket_created(self, pocket: Pocket):
        pass

    @abstractmethod
    def on_pocket_updated(self, pocket: Pocket):
        pass

    @abstractmethod
    def on_pocket_deleted(self, pocket: Pocket):
        pass


class PocketManager:
    def __init__(self, db_path: str = "account.db", observer: PocketObserver = None):
        self.db_path = db_path
        self.observer = observer
        self.pockets = {}

    def init(self):
        Pocket.init_db(self.db_path)

        self.pockets = { p.id: p for p in Pocket.load_all(self.db_path) if not p.is_closed }
        if self.observer:
            for pos in self.pockets.values():
                self.observer.on_pocket_loaded(pos)

    def create_pocket(self, ticker: str, entry_price: float, volume: float):
        """
        Handles filled orders to create new pockets.
        """
        pocket = Pocket(ticker=ticker, entry_price=entry_price, volume=volume)    
        self.pockets[pocket.id] = pocket
        pocket.save(self.db_path)
        
        if self.observer:
            self.observer.on_pocket_created(pocket)
        
        logger.info(f"[PocketManager] Created Pocket from Order: {pocket.ticker}")
        return pocket

    def close_pocket(self, pocket_id: str, current_price: Decimal):
        pocket = self.pockets.get(pocket_id)
        pocket.status = "closed"
        pocket.close_price = current_price
        pocket.close_time = time.time()
        pocket.save(self.db_path)
        
        if self.observer:
            self.observer.on_pocket_updated(pocket)

    def get_pockets(self, ticker:str, only_active:bool = True) -> List[Pocket]:
        if only_active:
            return [p for p in self.pockets.values() if p.ticker == ticker and not p.is_closed]
        return [p for p in self.pockets.values() if p.ticker == ticker]
    
    def get_pocket(self, pid:str) -> Optional[Pocket]:
        return self.pockets.get(pid)


    def archive_pocket(self, pocket_id: str):
        """Archive a pocket and remove from memory."""
        pocket = self.pockets.get(pocket_id)
        if pocket:
            try:
                pocket.archive(self.db_path) 
                self.observer.on_pocket_deleted(pocket)
                del self.pockets[pocket_id]
                logger.info(f"[PocketManager] Archived Pocket {pocket_id}")
            except Exception as e:
                logger.error(f"[PocketManager] Failed to archive pocket {pocket_id}: {e}")
        else:
            logger.warning(f"[PocketManager] Archive requested for unknown pocket {pocket_id}")