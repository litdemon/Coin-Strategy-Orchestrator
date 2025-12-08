from pydantic import BaseModel, Field
from typing import Optional

class OrderInfo(BaseModel):
    uuid: str
    side: str  # ask, bid
    ord_type: str  # limit, price, market
    price: Optional[float] = None
    state: str  # wait, done, cancel
    market: str
    created_at: str
    volume: Optional[float] = None
    remaining_volume: Optional[float] = None
    reserved_fee: float
    remaining_fee: float
    paid_fee: float
    locked: float
    executed_volume: float
    trades_count: int

    class Config:
        # Pydantic will attempt to cast strings to floats/ints
        frozen = False
