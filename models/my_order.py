from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

class MyOrder(BaseModel):
    type: str  # "myOrder"
    code: str
    uuid: str
    ask_bid: str  # "BID", "ASK"
    order_type: str  # "limit", etc.
    state: str  # "wait", "done", "cancel"
    trade_uuid: Optional[str] = None
    price: Decimal
    avg_price: Decimal
    volume: Decimal
    remaining_volume: Decimal
    executed_volume: Decimal
    trades_count: int
    reserved_fee: Decimal
    remaining_fee: Decimal
    paid_fee: Decimal
    locked: Decimal
    executed_funds: Decimal
    time_in_force: Optional[str] = None
    trade_fee: Optional[Decimal] = None
    is_maker: Optional[bool] = None
    identifier: Optional[str] = None
    smp_type: Optional[str] = None
    prevented_volume: Decimal
    prevented_locked: Decimal
    trade_timestamp: Optional[int] = None
    order_timestamp: int
    timestamp: int
    stream_type: str

    class Config:
        frozen = False
