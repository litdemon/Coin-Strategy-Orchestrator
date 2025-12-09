


class Candle:
    def __init__(self, code: str, price: float):
        self.code = code
        self.open = price
        self.high = price
        self.low = price
        self.close = price

    def update(self, price: float):
        self.close = price
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price

    def reset(self, price: float):
        self.open = price
        self.high = price
        self.low = price
        self.close = price

    def render(self, width: int = 20) -> str:
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
            return f"{self.low/self.open:.1f}%[{color_code}{bar}{reset_code}]{self.high/self.open:.1f}%"

        # Map prices to positions
        # [0 ... width-1]
        
        # Body range
        body_min = min(self.open, self.close)
        body_max = max(self.open, self.close)
        
        # Avoid division by zero (already handled, but safe logic) or tiny range issues
        # Use relative positions
        
        low_idx = 0
        high_idx = width - 1
        
        def get_pos(price):
            if total_range == 0: return 0
            pos = int((price - self.low) / total_range * (width - 1))
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
