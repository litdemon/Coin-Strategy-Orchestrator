
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, call

sys.path.append(os.getcwd())

from src.main import Manager
from upbit.upbit_websocket import UpbitWebSocket

class TestManagerIntegration(unittest.TestCase):
    def setUp(self):
        # Initialize Manager in virtual mode
        self.manager = Manager(virtual=True)
        # Mock dependencies
        self.manager.dashboard = MagicMock()
        self.manager.account_manager = MagicMock()
        self.manager.messaging = MagicMock()
        self.manager.price_ob = MagicMock()
        self.manager.upbit_websocket = MagicMock(spec=UpbitWebSocket)
        self.manager.upbit_websocket.codes = ["KRW-BTC"] # Pre-subscribed
        self.manager.strategy_manager = MagicMock()
        self.manager.position_manager = MagicMock()
        
    def test_dynamic_subscription(self):
        """Test that buying a new ticker triggers subscription."""
        cmd_new = {
            "action": "buy",
            "ticker": "KRW-ETH",
            "volume": 0.1,
            "price": 3000000
        }
        self.manager.process_command("trading/command/1", cmd_new)
        
        self.manager.upbit_websocket.add_subscription.assert_called_with(["KRW-ETH"])
        
        # Buying existing ticker should NOT trigger
        self.manager.upbit_websocket.add_subscription.reset_mock()
        cmd_existing = {
            "action": "buy",
            "ticker": "KRW-BTC",
            "volume": 0.1,
            "price": 50000000
        }
        self.manager.process_command("trading/command/2", cmd_existing)
        self.manager.upbit_websocket.add_subscription.assert_not_called()

    def test_sell_all_logic(self):
        """Test Sell All (-1 volume) logic."""
        # Setup: Avail balance for KRW-BTC is 2.5
        self.manager.account_manager.get_balance.return_value = Decimal("2.5")
        
        cmd = {
            "action": "sell",
            "ticker": "KRW-BTC",
            "volume": -1,
            "price": 60000
        }
        self.manager.process_command("trading/command/3", cmd)
        
        # Verify get_balance called
        self.manager.account_manager.get_balance.assert_called_with("KRW-BTC")
        # Verify sell_limit_order called with full balance
        self.manager.account_manager.sell_limit_order.assert_called_with("KRW-BTC", 60000.0, 2.5)

    def test_market_order_handling(self):
        """Test that price <= 0 triggers market order."""
        # Market Buy
        cmd_buy = {
            "action": "buy",
            "ticker": "KRW-BTC",
            "volume": 10000,
            "price": -1
        }
        self.manager.process_command("trading/command/4", cmd_buy)
        self.manager.account_manager.buy_market_order.assert_called_with("KRW-BTC", 10000.0)
        
        # Market Sell
        cmd_sell = {
            "action": "sell",
            "ticker": "KRW-BTC",
            "volume": 0.1,
            "price": -1
        }
        self.manager.process_command("trading/command/5", cmd_sell)
        self.manager.account_manager.sell_market_order.assert_called_with("KRW-BTC", 0.1)

if __name__ == "__main__":
    unittest.main()
