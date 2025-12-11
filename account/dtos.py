from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal
from typing import Optional
from datetime import datetime

class AssetDTO(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    currency: str
    balance: Decimal
    locked: Decimal
    avg_buy_price: Decimal
    avg_buy_price_modified: bool
    unit_currency: str

class OrderDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    uuid: str
    side: str  # ask, bid
    ord_type: str  # limit, market
    price: Optional[Decimal] = None
    state: str  # wait, done, cancel
    market: str
    created_at: datetime
    volume: Optional[Decimal] = None
    remaining_volume: Optional[Decimal] = None
    reserved_fee: Decimal = Decimal("0")
    remaining_fee: Decimal = Decimal("0")
    paid_fee: Decimal = Decimal("0")
    locked: Decimal = Decimal("0")
    executed_volume: Decimal = Decimal("0")
    trades_count: int = 0
