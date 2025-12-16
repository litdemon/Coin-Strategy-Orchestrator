from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

class TickerMsg(BaseModel):
    type: str  # "ticker"
    code: str
    opening_price: Decimal
    high_price: Decimal
    low_price: Decimal
    trade_price: Decimal
    prev_closing_price: Decimal
    acc_trade_price: Decimal
    change: str  # "RISE", "FALL", "EVEN"
    change_price: Decimal
    signed_change_price: Decimal
    change_rate: Decimal
    signed_change_rate: Decimal
    ask_bid: str  # "ASK", "BID"
    trade_volume: Decimal
    acc_trade_volume: Decimal
    trade_date: str  # "YYYYMMDD"
    trade_time: str  # "HHMMSS"
    trade_timestamp: int
    acc_ask_volume: Decimal
    acc_bid_volume: Decimal
    highest_52_week_price: Decimal
    highest_52_week_date: str
    lowest_52_week_price: Decimal
    lowest_52_week_date: str
    market_state: str
    is_trading_suspended: bool
    delisting_date: Optional[str] = None
    market_warning: str
    timestamp: int
    acc_trade_price_24h: Decimal
    acc_trade_volume_24h: Decimal
    stream_type: str

    class Config:
        frozen = False
