import unittest
import sys
import os
import shutil
import time
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.position_manager import PositionManager, Position

class TestPositionClosing(unittest.TestCase):
    def setUp(self):
        # Use a temporary DB for testing
        self.test_db = "test_position_closing.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        self.manager = PositionManager(db_path=self.test_db)

    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_buy_creates_position(self):
        order_info = {
            'code': 'KRW-BTC',
            'ask_bid': 'bid',
            'state': 'done',
            'price': 50000000.0,
            'volume': 0.01
        }
        self.manager.on_order_fill(order_info)
        
        positions = self.manager.get_positions('KRW-BTC', only_active=True)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].entry_price, 50000000.0)
        self.assertEqual(positions[0].status, 'active')

    def test_sell_closes_position(self):
        # 1. Create Position first (simulating buy)
        self.manager.create_position('KRW-ETH', 2000000.0, 1.0)
        
        positions = self.manager.get_positions('KRW-ETH', only_active=True)
        self.assertEqual(len(positions), 1)
        
        # 2. Simulate Sell Order
        sell_order = {
            'code': 'KRW-ETH',
            'ask_bid': 'ask',
            'state': 'done',
            'price': 2500000.0,
            'volume': 1.0
        }
        self.manager.on_order_fill(sell_order)
        
        # 3. Verify Position is Closed
        active_positions = self.manager.get_positions('KRW-ETH', only_active=True)
        self.assertEqual(len(active_positions), 0)
        
        all_positions = self.manager.get_positions('KRW-ETH', only_active=False)
        self.assertEqual(len(all_positions), 1)
        self.assertEqual(all_positions[0].status, 'closed')
        self.assertEqual(all_positions[0].close_price, 2500000.0)

if __name__ == '__main__':
    unittest.main()
