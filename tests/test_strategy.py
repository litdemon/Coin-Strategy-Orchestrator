
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.append(os.getcwd())

from strategy.trailingstop import TrailingStopStrategy, TrailingStopConfig
from strategy.models import StrategyContext, Signal, SignalType

class TestStrategy(unittest.TestCase):
    def test_trailing_stop_logic(self):
        """Test TrailingStopStrategy signal generation."""
        # 1. Setup
        context = StrategyContext(strategy_id="test", ticker="KRW-BTC", budget=Decimal("100000"), pocket_id="pos1")
        config = TrailingStopConfig(entry_price=Decimal("100"), trail_percent=Decimal("0.05")) # 5% trail
        
        strategy = TrailingStopStrategy(context=context, config=config)
        
        # 2. Price Rising
        # Entry 100. High 100. Trail Stop 95.
        
        # Price -> 110 (New High). Trail Stop -> 110 * 0.95 = 104.5
        signal = strategy.on_tick(Decimal("110"))
        self.assertIsNone(signal) # No signal yet
        self.assertEqual(strategy.highest_price, Decimal("110"))
        
        # Price -> 120 (New High). Trail Stop -> 120 * 0.95 = 114.0
        strategy.on_tick(Decimal("120"))
        self.assertEqual(strategy.highest_price, Decimal("120"))
        
        # Price -> 115 (Dip, but > 114). No signal.
        signal = strategy.on_tick(Decimal("115"))
        self.assertIsNone(signal)
        
        # Price -> 113 (Drop below 114). CLOSE signal.
        signal = strategy.on_tick(Decimal("113"))
        self.assertIsNotNone(signal)
        self.assertEqual(signal.type, SignalType.CLOSE_POCKET)
        self.assertEqual(signal.ticker, "KRW-BTC")
        print("[PASS] Trailing Stop triggered correctly at 113 (High 120, Stop 114)")

if __name__ == "__main__":
    unittest.main()
