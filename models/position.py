import uuid
import time
import logging
import sqlite3
import os

from pydantic import BaseModel, Field
from typing import Optional, Any, List

class PositionBase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str
    entry_price: float
    volume: float # = budget
    config: Optional[Any] = None
    entry_time: float = Field(default_factory=time.time)
    
    # Fields refactored from Rot
    order_id: Optional[str] = None
    highest_price: Optional[float] = None
    status: str = "active" # active, closed

    close_price: Optional[float] = None
    close_time: Optional[float] = None

    class Config:
        arbitrary_types_allowed = True

