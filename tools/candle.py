import pandas as pd
from typing import List
from decimal import Decimal

class Candle:
    def __init__(self, code: str, price: Decimal):
        self.code = code
        price = Decimal(str(price))
        self.open = price
        self.high = price
        self.low = price
        self.close = price
        self.prev = price

    def update(self, price: Decimal):
        price = Decimal(str(price))
        self.prev = self.close
        self.close = price
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        
    def is_updated(self):
        return self.close != self.prev

    def reset(self, ohlcv: pd.DataFrame):
        self.open = Decimal(str(ohlcv['open'].iloc[-1]))
        self.high = Decimal(str(ohlcv['high'].iloc[-1]))
        self.low = Decimal(str(ohlcv['low'].iloc[-1]))
        self.close = Decimal(str(ohlcv['close'].iloc[-1]))

    def current_price(self) ->Decimal:
        return self.close

    def render(self, width: int = 20) -> str:
        if self.open == 0:
            return "Wait..."

        # Determine color
        is_up = self.close >= self.open
        # ANSI Colors: Red (31), Blue (34), Reset (0)
        color_code = "\033[31m" if is_up else "\033[34m"
        reset_code = "\033[0m"

        # Calculate range
        total_range = self.high - self.low
        if total_range == 0:
            # Flat line
            bar = "-" * width
            if self.open != 0:
                low_pct = (self.low/self.open - 1) * 100
                high_pct = (self.high/self.open - 1) * 100
                return f"{low_pct:.1f}%[{color_code}{bar}{reset_code}]{high_pct:.1f}%"
            else:
                return f"0.0%[{color_code}{bar}{reset_code}]0.0%"

        # Map prices to positions
        # [0 ... width-1]
        
        # Body range
        body_min = min(self.open, self.close)
        body_max = max(self.open, self.close)
        
        # Avoid division by zero (already handled, but safe logic) or tiny range issues
        # Use relative positions
        
        low_idx = 0
        high_idx = width - 1
        
        def get_pos(price: Decimal):
            if total_range == 0: return 0
            # Ensure price is Decimal
            d_price = Decimal(str(price)) if not isinstance(price, Decimal) else price
            pos = int((d_price - self.low) / total_range * (width - 1))
            return max(0, min(width - 1, pos))

        body_start = get_pos(body_min)
        body_end = get_pos(body_max)
        
        chars = ["-"] * width
        
        # Fill body
        for i in range(body_start, body_end + 1):
            chars[i] = "◙"
            
        bar_str = "".join(chars)
        low_percent = ((self.low-self.open)/self.open)*100
        high_percent = ((self.high-self.open)/self.open)*100
        return f"{low_percent:.2f}%[{color_code}{bar_str}{reset_code}]{high_percent:.2f}%"
