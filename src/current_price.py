from decimal import Decimal
from typing import List, Tuple
from tools.candle import Candle

class CurrentPrice:
    def __init__(self):
        self.candles = {}
        self.previous_line = ""

    def update(self, code: str, price: Decimal):
        # Ensure price is Decimal
        d_price = Decimal(str(price)) if not isinstance(price, Decimal) else price
        
        if code not in self.candles:
            self.candles[code] = Candle(code, d_price)
        else:
            self.candles[code].update(d_price)

    def get(self, code: str) -> Decimal:
        if code not in self.candles:
            return Decimal(0)
        return self.candles[code].current_price()
    
    def is_updated(self, code: str) -> bool:
        if code not in self.candles:
            return False
        return self.candles[code].is_updated()
    
    def get_all(self) -> List[Tuple[str, Decimal]]:
        # Return (code, latest_price) to maintain compatibility
        return [(code, candle.current_price()) for code, candle in self.candles.items()]
    
    def print_all(self):
        line = ""
        # Sort or fixed order might be better, but dict iteration fine for now
        # Format: [CODE: PRICE CANDLE]
        
        for code, candle in self.candles.items():
            candle_str = candle.render(width=15)
            line += f"[{code}: {candle.current_price():.0f} {candle_str}] "
        
        # Clear line padding
        padding = max(0, 160 - len(line)) # arbitrary wide buffer
        
        if self.previous_line != line:
            self.previous_line = line
            # \r to overwrite line
            # Need to handle terminal width if too long, but simple for now
            # ANSI codes count in len(line) but don't show, so visual length is shorter.
            # Just print raw.
            print(f"\r{line}", end="")
            
        return

