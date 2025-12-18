
import os
import sys
import contextlib
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import time
import logging
import sqlite3
import pyupbit
import uuid
from decimal import Decimal

# Add project root to sys.path


from typing import Optional, List, Dict, Any, Callable
from models.pocket import PocketBase
from strategy.base import Signal
from tools.db_interface import DBInterface
from abc import ABC, abstractmethod
from enum import Enum

logger = logging.getLogger(__name__)

class PocketStateType(str, Enum):
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed" # Explicit close
    PARTIAL_CLOSE = "partial_close"


class Pocket(PocketBase, DBInterface):

    class Config:
        arbitrary_types_allowed = True
    
    @property
    def is_closed(self) -> bool:
        return self.status == PocketStateType.CLOSED

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
        
        # Migration: Ensure close_order_id exists
        try:
            with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("ALTER TABLE pockets ADD COLUMN close_order_id TEXT")
                conn.commit()
                logger.info("Migrated DB: Added close_order_id to pockets")
        except sqlite3.OperationalError:
            # Column likely already exists
            pass
        except Exception as e:
            logger.error(f"Migration failed: {e}")

        self.pockets = { p.id: p for p in Pocket.load_all(self.db_path) if not p.is_closed }
        if self.observer:
            for pos in self.pockets.values():
                self.observer.on_pocket_loaded(pos)

    def create_pocket(self, ticker: str, entry_price: Decimal, volume: Decimal):
        """
        Handles filled orders to create new pockets.
        """
        pocket = Pocket(ticker=ticker, entry_price=entry_price, volume=volume)    
        self.pockets[pocket.id] = pocket
        pocket.save(self.db_path)
        
        if self.observer:
            self.observer.on_pocket_created(pocket)
        
        logger.debug(f"[PocketManager] Created Pocket from Order: {pocket.ticker}")
        return pocket

    def delete_pocket(self, pocket_id: str):
        pocket = self.pockets.get(pocket_id)
        if pocket:
            pocket.delete(self.db_path)
            del self.pockets[pocket_id]
            if self.observer:
                self.observer.on_pocket_deleted(pocket)
        else:
            logger.debug(f"[PocketManager] Pocket {pocket_id} not found")

    def close_pocket(self, pocket_id: str):
        pocket = self.pockets.get(pocket_id)
        if pocket and pocket.status == PocketStateType.ACTIVE:
            pocket.status = PocketStateType.CLOSING
            pocket.save(self.db_path)
            
            if self.observer:
                self.observer.on_pocket_updated(pocket)
        else:
            logger.warning(f"[PocketManager] Pocket {pocket_id} not found or not active")

    def closed_pocket(self, pocket_id: str, closed_price: Decimal=Decimal(0)):
        pocket = self.pockets.get(pocket_id)
        # Allow closing from ACTIVE (heuristic/manual) or CLOSING (2-step)
        if pocket and pocket.status in [PocketStateType.ACTIVE, PocketStateType.CLOSING]:
            pocket.close_price = closed_price
            pocket.close_time = time.time()
            pocket.status = PocketStateType.CLOSED
            pocket.save(self.db_path)

            if self.observer:
                self.observer.on_pocket_updated(pocket)
            return pocket
        else:
            logger.warning(f"[PocketManager] Pocket {pocket_id} not found or not active/closing")
        return None

    def close_pockets_by_ticker(self, ticker: str, price: Decimal, volume: Decimal):
        """Close pockets for a ticker based on sell volume (Lowest Entry Price first)."""
        # Finds active pockets for ticker
        targets = self.get_pockets(ticker, only_active=True)
        # Sort by entry_price ascending (Lowest First)
        targets.sort(key=lambda p: p.entry_price)
        
        remaining_sell_vol = volume
        
        for pocket in targets:
            if remaining_sell_vol <= 0:
                break
            
            if remaining_sell_vol >= pocket.volume:
                # Full Close - Immediate because order is already done
                self.closed_pocket(pocket.id, price)
                remaining_sell_vol -= pocket.volume
            else:
                # Partial Close
                # 1. Create a "closed" copy for the sold portion
                closed_vol = remaining_sell_vol
                
                # We replicate the pocket for the closed portion
                # Note: We need to handle ID. New pocket gets new ID? Or we keep ID for active?
                # Usually we keep ID for active path to avoid disrupting strategies tracking it.
                # So we create a NEW pocket for the history/closed part.
                
                # But wait, we need to create a new instance.
                # Since Pocket is Pydantic, we can copy.
                from copy import deepcopy
                closed_pocket = pocket.model_copy()
                closed_pocket.id = str(uuid.uuid4()) # New ID for the closed chunk
                closed_pocket.volume = closed_vol
                closed_pocket.status = PocketStateType.CLOSED
                closed_pocket.close_price = price
                closed_pocket.close_time = time.time()
                
                # Update Active Pocket
                pocket.volume -= closed_vol
                pocket.save(self.db_path)
                
                # Save Closed Pocket
                # We need to add it to self.pockets?
                # If we want to track history, yes.
                self.pockets[closed_pocket.id] = closed_pocket
                closed_pocket.save(self.db_path)
                
                if self.observer:
                    self.observer.on_pocket_updated(pocket) # Volume changed
                    self.observer.on_pocket_created(closed_pocket) # New closed pocket created (or should it be 'closed' event?)
                    # Actually, for the system, it's a split.
                    
                remaining_sell_vol = 0
                logger.info(f"[PocketManager] Partial Close: {pocket.ticker} - Active: {pocket.volume}, Closed: {closed_vol}")

        logger.info(f"[PocketManager] Closed pockets process finished for {ticker}")

    def get_pockets(self, ticker:str, only_active:bool = True) -> List[Pocket]:
        if only_active:
            return [p for p in self.pockets.values() if p.ticker == ticker and not p.is_closed]
        return [p for p in self.pockets.values() if p.ticker == ticker]
    
    def get_pocket(self, pid:str) -> Optional[Pocket]:
        return self.pockets.get(pid)

    def get_pocket_by_order_id(self, order_id: str) -> Optional[Pocket]:
        """Find active pocket associated with a close order ID."""
        for pocket in self.pockets.values():
            if pocket.close_order_id == order_id:
                return pocket
        return None


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