import sys
import os
from decimal import Decimal
import unittest

sys.path.append(os.getcwd())
from tools.candle import Candle

class TestCandleTypes(unittest.TestCase):
    def test_mixed_types(self):
        # Initialize with Decimal
        c = Candle("KRW-BTC", Decimal("1000"))
        
        # Update with float (should be handled by callers or robust Candle)
        # Note: In our architecture, callers (CurrentPrice) convert to Decimal.
        # But Candle.get_pos also defends against it.
        # Let's test Candle.render with float values forced into it (simulating bad state)
        # or testing CurrentPrice behavior.
        
        # Scenario 1: Candle has mixed types internally (worst case)
        c.low = Decimal("900")
        c.high = Decimal("1100")
        c.open = Decimal("1000")
        c.close = 1050.0 # Float
        
        try:
            render_output = c.render(width=20)
            print(f"Render Output (Mixed): {render_output}")
        except TypeError as e:
            self.fail(f"Candle.render raised TypeError with mixed types: {e}")

    def test_get_pos_defense(self):
        c = Candle("KRW-BTC", Decimal("1000"))
        c.low = Decimal("900")
        c.high = Decimal("1100")
        
        # Directly call get_pos via render logic simulation
        # The crash was: pos = int((price - self.low) ...)
        # passed price was float
        
        try:
            c.close = 1050.5 # float
            # render calls get_pos(min(open, close))
            # min(Decimal, float) -> can be float
            c.render()
        except TypeError as e:
            self.fail(f"Candle.render failed with float close price: {e}")

if __name__ == '__main__':
    unittest.main()
