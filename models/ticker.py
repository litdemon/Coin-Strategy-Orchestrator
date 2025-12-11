from pydantic import BaseModel
from typing import Optional

class TickerMsg(BaseModel):
    type: str  # "ticker"
    code: str
    opening_price: float
    high_price: float
    low_price: float
    trade_price: float
    prev_closing_price: float
    acc_trade_price: float
    change: str  # "RISE", "FALL", "EVEN"
    change_price: float
    signed_change_price: float
    change_rate: float
    signed_change_rate: float
    ask_bid: str  # "ASK", "BID"
    trade_volume: float
    acc_trade_volume: float
    trade_date: str  # "YYYYMMDD"
    trade_time: str  # "HHMMSS"
    trade_timestamp: int
    acc_ask_volume: float
    acc_bid_volume: float
    highest_52_week_price: float
    highest_52_week_date: str
    lowest_52_week_price: float
    lowest_52_week_date: str
    market_state: str
    is_trading_suspended: bool
    delisting_date: Optional[str] = None
    market_warning: str
    timestamp: int
    acc_trade_price_24h: float
    acc_trade_volume_24h: float
    stream_type: str

    class Config:
        frozen = False
