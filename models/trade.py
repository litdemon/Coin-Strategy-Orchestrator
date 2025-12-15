from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

class Trade(BaseModel):
    type: str  # "trade"
    code: str
    timestamp: int
    trade_date: str
    trade_time: str
    trade_timestamp: int
    trade_price: Decimal
    trade_volume: Decimal
    ask_bid: str  # "ASK", "BID"
    prev_closing_price: Decimal
    change: str  # "RISE", "FALL", "EVEN"
    change_price: Decimal
    sequential_id: int
    best_ask_price: Decimal
    best_ask_size: Decimal
    best_bid_price: Decimal
    best_bid_size: Decimal
    stream_type: str

    class Config:
        frozen = False
