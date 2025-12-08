from pydantic import BaseModel
from typing import Optional

class Trade(BaseModel):
    type: str  # "trade"
    code: str
    timestamp: int
    trade_date: str
    trade_time: str
    trade_timestamp: int
    trade_price: float
    trade_volume: float
    ask_bid: str  # "ASK", "BID"
    prev_closing_price: float
    change: str  # "RISE", "FALL", "EVEN"
    change_price: float
    sequential_id: int
    best_ask_price: float
    best_ask_size: float
    best_bid_price: float
    best_bid_size: float
    stream_type: str

    class Config:
        frozen = False
