from pydantic import BaseModel
from typing import Optional

class MyOrder(BaseModel):
    type: str  # "myOrder"
    code: str
    uuid: str
    ask_bid: str  # "BID", "ASK"
    order_type: str  # "limit", etc.
    state: str  # "wait", "done", "cancel"
    trade_uuid: Optional[str] = None
    price: float
    avg_price: float
    volume: float
    remaining_volume: float
    executed_volume: float
    trades_count: int
    reserved_fee: float
    remaining_fee: float
    paid_fee: float
    locked: float
    executed_funds: float
    time_in_force: Optional[str] = None
    trade_fee: Optional[float] = None
    is_maker: Optional[bool] = None
    identifier: Optional[str] = None
    smp_type: Optional[str] = None
    prevented_volume: float
    prevented_locked: float
    trade_timestamp: Optional[int] = None
    order_timestamp: int
    timestamp: int
    stream_type: str

    class Config:
        frozen = False
