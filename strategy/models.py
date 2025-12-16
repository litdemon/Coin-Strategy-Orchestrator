from enum import Enum
from typing import Dict, Any, Optional
from decimal import Decimal
import time
import uuid
from pydantic import BaseModel, Field

class StrategyStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    UPDATE_STOP = "update_stop"
    CLOSE_POSITION = "close_position" # Explicit close
    PARTIAL_CLOSE = "partial_close"

class Signal(BaseModel):
    """Signal emitted by a strategy to request action."""
    type: SignalType
    strategy_id: str
    ticker: str
    amount: Optional[Decimal] = None # For buy/sell (volume or price depending on context, usually info only for manager)
    price: Optional[Decimal] = None # For limit orders
    reason: str
    data: Optional[Dict[str, Any]] = None # Extra metadata
    timestamp: float = Field(default_factory=time.time)

class StrategyConfig(BaseModel):
    """Base configuration for a strategy."""
    strategy_type: str
    execution_interval: Optional[int] = None # Seconds. If set, on_schedule is called.
    
    class Config:
        extra = "allow"

class StrategyDTO(BaseModel):
    """Data Transfer Object for persisting Strategy state."""
    strategy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    ticker: str
    budget: Decimal
    position_id: Optional[str] = None # Optional link to a specific position
    status: StrategyStatus = StrategyStatus.ACTIVE
    config: Dict[str, Any]
    state: Dict[str, Any]
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            Decimal: lambda v: str(v)
        }

class StrategyContext(BaseModel):
    """Context passed to the strategy execution environment."""
    strategy_id: str
    ticker: str
    budget: Decimal
    position_id: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
