
import unittest
import os
import sys
from unittest.mock import MagicMock
from decimal import Decimal

sys.path.append(os.getcwd())

from src.position_manager import PositionManager, Position
from strategy.models import Signal, SignalType

class TestPositionManager(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_position.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        self.manager = PositionManager(db_path=self.test_db)
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_on_order_fill_creates_position(self):
        """Test that a filled Buy order creates a position."""
        order_info = {
            'code': 'KRW-BTC',
            'ask_bid': 'bid',
            'state': 'done',
            'volume': 0.1,
            'price': 50000000.0
        }
        self.manager.on_order_fill(order_info)
        
        positions = self.manager.get_positions('KRW-BTC')
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        self.assertEqual(pos.ticker, 'KRW-BTC')
        self.assertEqual(pos.volume, Decimal("0.1"))
        self.assertEqual(pos.entry_price, Decimal("50000000.0"))
        self.assertFalse(pos.is_closed)

    def test_on_order_fill_closes_position(self):
        """Test that a filled Sell order closes a position."""
        # 1. Create Position
        self.manager.create_position(ticker='KRW-BTC', entry_price=Decimal("50000000"), volume=Decimal("0.1"))
        pos = self.manager.get_positions('KRW-BTC')[0]
        
        # 2. Sell Order Filled
        order_info = {
            'code': 'KRW-BTC',
            'ask_bid': 'ask',
            'state': 'done',
            'volume': 0.1,
            'price': 60000000.0,
            'uuid': 'some-uuid' # Normally linked via trade match, but simplified logic might close FIFO
        }
        # Note: current PositionManager logic for closing needs review. 
        # Does it match by order UUID or just reduce volume?
        # The existing code (reviewed previously) seemed to iterate active positions and close them if side matches.
        # Let's inspect src/position_manager.py logic if test fails, but for now assuming standard FIFO or direct mapping.
        
        self.manager.on_order_fill(order_info)
        
        # Reload
        positions = self.manager.get_positions('KRW-BTC', only_active=False)
        self.assertEqual(len(positions), 1)
        pos = positions[0]
        # Logic might differ: does it mark is_closed? or reduce volume?
        # Assuming simple model: selling everything closes the position.
        self.assertTrue(pos.is_closed)
        self.assertEqual(pos.close_price, Decimal("60000000.0"))

if __name__ == "__main__":
    unittest.main()
