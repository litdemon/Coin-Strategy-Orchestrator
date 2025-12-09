
from typing import List, Tuple
from src.candle import Candle

class CurrentPrice:
    def __init__(self):
        self.candles = {}
        self.previous_line= ""

    def update(self, code: str, price: float):
        if code not in self.candles:
             self.candles[code] = Candle(code, price)
        else:
             self.candles[code].update(price)

    def get(self, code: str) -> float:
        if code in self.candles:
            return self.candles[code].close
        return 0.0
    
    def is_updated(self, code: str) -> bool:
        return code in self.candles
    
    def get_all(self) -> List[Tuple[str, float]]:
        # Return (code, latest_price) to maintain compatibility
        return [(code, candle.close) for code, candle in self.candles.items()]
    
    def print_all(self):
        line = ""
        # Sort or fixed order might be better, but dict iteration fine for now
        # Format: [CODE: PRICE CANDLE]
        
        for code, candle in self.candles.items():
            candle_str = candle.render(width=15)
            line += f"[{code}: {candle.close:.0f} {candle_str}] "
        
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

