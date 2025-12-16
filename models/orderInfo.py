from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional

class OrderInfo(BaseModel):
    uuid: str
    side: str  # ask, bid
    ord_type: str  # limit, price, market
    price: Optional[Decimal] = None
    state: str  # wait, done, cancel
    market: str
    created_at: str
    volume: Optional[Decimal] = None
    remaining_volume: Optional[Decimal] = None
    reserved_fee: Decimal
    remaining_fee: Decimal
    paid_fee: Decimal
    locked: Decimal
    executed_volume: Decimal
    trades_count: int

    class Config:
        # Pydantic will attempt to cast strings to floats/ints
        frozen = False
