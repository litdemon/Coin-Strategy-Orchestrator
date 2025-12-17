import uuid
import time
import logging
import sqlite3
import os

from pydantic import BaseModel, Field
from typing import Optional, Any, List
from decimal import Decimal

class PocketBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str
    volume: Decimal # = budget
    entry_price: Decimal
    entry_time: float = Field(default_factory=time.time)
    config: Optional[Any] = None
    
    # Fields refactored from Rot
    order_id: Optional[str] = None
    highest_price: Optional[Decimal] = None
    status: str = "active" # active, closed

    close_price: Optional[Decimal] = None
    close_time: Optional[float] = None

    class Config:
        arbitrary_types_allowed = True

