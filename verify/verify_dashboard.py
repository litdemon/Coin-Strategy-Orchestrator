import unittest
import os
import sys
import threading
import queue
from unittest.mock import MagicMock, patch
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard import Dashboard, LogWidget, TickerWidget, PocketWidget, StrategyWidget

# Suppress logging during tests
logging.basicConfig(level=logging.CRITICAL)

class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.dashboard = Dashboard()
        # Mock sys.stdout to prevent clutter
        self.mock_stdout = MagicMock()
        
    def process_queue(self):
        """Helper to process all items in the dashboard queue synchronously using _process_item."""
        while not self.dashboard.queue.empty():
            try:
                item = self.dashboard.queue.get_nowait()
                self.dashboard._process_item(item)
            except queue.Empty:
                break

    def test_log_update(self):
        print("\n[Test] Generic Log Update")
        msg = "Test Generic Log"
        self.dashboard.update({'type': 'log', 'message': msg})
        
        self.process_queue()
        
        self.assertIn('log', self.dashboard.registry)
        log_widget = self.dashboard.registry['log']
        self.assertIn(msg, log_widget.logs)
        print(" -> Log updated via generic method")

    def test_balance_update(self):
        print("\n[Test] Generic Balance (Ticker) Update")
        balance_data = {
            'currency': 'BTC',
            'balance': 2.0,
            'avg_buy_price': 60000000
        }
        self.dashboard.update(balance_data)
        
        self.process_queue()
        
        self.assertIn("KRW-BTC", self.dashboard.registry)
        widget = self.dashboard.registry["KRW-BTC"]
        self.assertIsInstance(widget, TickerWidget)
        self.assertEqual(widget.amount, 2.0)
        self.assertEqual(widget.avg_buy_price, 60000000)
        print(" -> TickerWidget created/updated from balance dump")

    def test_ticker_price_update(self):
        print("\n[Test] Generic Ticker Price Update")
        # Ensure widget exists first (usually via balance, but can be auto-created by ticker update too?)
        # My implementation of _create_widget allows creation if id not found.
        # But _process_item needs to identify it. 
        # Ticker update from websocket: {'code': 'KRW-ETH', 'trade_price': ...}
        
        ticker_data = {'code': 'KRW-ETH', 'type': 'ticker', 'trade_price': 3500000}
        self.dashboard.update(ticker_data)
        self.process_queue()
        
        self.assertIn("KRW-ETH", self.dashboard.registry)
        widget = self.dashboard.registry["KRW-ETH"]
        self.assertEqual(widget.candle.close, 3500000)
        print(" -> TickerWidget created/updated from ticker dump")

    def test_position_update(self):
        print("\n[Test] Generic Pocket Update")
        # Pocket dump typically: {id, ticker, entry_price, volume, ...}
        pos_data = {
            'id': 'pos-uuid-1234',
            'ticker': 'KRW-XRP', # or XRP, my code expects ticker to handle it
            'entry_price': 600,
            'volume': 500
        }
        
        self.dashboard.update(pos_data)
        self.process_queue()
        
        # Check Ticker Parent Created
        self.assertIn("KRW-XRP", self.dashboard.registry)
        ticker_widget = self.dashboard.registry["KRW-XRP"]
        
        # Check Pocket Created
        self.assertIn("pos-uuid-1234", self.dashboard.registry)
        pos_widget = self.dashboard.registry["pos-uuid-1234"]
        
        self.assertIsInstance(pos_widget, PocketWidget)
        self.assertEqual(pos_widget.parent, ticker_widget)
        self.assertIn("pos-uuid-1234", ticker_widget.children)
        
        self.assertEqual(pos_widget.entry_price, 600)
        self.assertEqual(pos_widget.volume, 500)
        print(" -> PocketWidget created and linked to TickerWidget")

    def test_strategy_update(self):
        print("\n[Test] Generic Strategy Update")
        # Need position first
        pos_data = {
            'id': 'pos-sol-999',
            'ticker': 'KRW-SOL',
            'entry_price': 60000,
            'volume': 10
        }
        self.dashboard.update(pos_data)
        self.process_queue()
        
        # Strategy DTO
        strategy_data = {
            'strategy_id': 'strat-rsi-111',
            'pocket_id': 'pos-sol-999',
            'type': 'RSIStrategy',
            'status': 'active',
            'ticker': 'KRW-SOL'
        }
        self.dashboard.update(strategy_data)
        self.process_queue()
        
        # Check Strategy Created
        self.assertIn("strat-rsi-111", self.dashboard.registry)
        strat_widget = self.dashboard.registry["strat-rsi-111"]
        pos_widget = self.dashboard.registry["pos-sol-999"]
        
        self.assertIsInstance(strat_widget, StrategyWidget)
        self.assertEqual(strat_widget.parent, pos_widget)
        self.assertIn("strat-rsi-111", pos_widget.children)
        
        self.assertEqual(strat_widget.name, 'RSIStrategy')
        self.assertEqual(strat_widget.state, 'active')
        print(" -> StrategyWidget created and linked to PocketWidget")

    def test_orphan_strategy_update(self):
        print("\n[Test] Generic Orphan Strategy (No Pocket) Update")
        # Strategy DTO with only ticker
        strategy_data = {
            'strategy_id': 'strat-buy-001',
            # No pocket_id
            'type': 'BuyStrategy',
            'status': 'wait',
            'ticker': 'KRW-ETH'
        }
        
        # Ensure Ticker exists (optional, Dashboard should create it if missing, let's test that auto-creation too)
        self.dashboard.update(strategy_data)
        self.process_queue()
        
        # Check Ticker Created
        self.assertIn("KRW-ETH", self.dashboard.registry)
        ticker_widget = self.dashboard.registry["KRW-ETH"]
        
        # Check Strategy Created
        self.assertIn("strat-buy-001", self.dashboard.registry)
        strat_widget = self.dashboard.registry["strat-buy-001"]
        
        self.assertIsInstance(strat_widget, StrategyWidget)
        self.assertEqual(strat_widget.parent, ticker_widget)
        self.assertIn("strat-buy-001", ticker_widget.children)
        
        print(" -> Orphan StrategyWidget created and linked to TickerWidget")

if __name__ == '__main__':
    unittest.main()
