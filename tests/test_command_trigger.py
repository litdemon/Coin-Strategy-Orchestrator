import unittest
from unittest.mock import MagicMock
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import Manager

class TestCommand(unittest.TestCase):
    def test_sell_command_triggers_account(self):
        # Setup
        manager = Manager(virtual=True)
        # Mock account manager
        manager.account_manager = MagicMock()
        manager.dashboard = MagicMock()
        manager.price_ob = MagicMock()
        
        # Test Limit Sell
        data_limit = {"action": "sell", "ticker": "KRW-BTC", "price": 50000000, "volume": 0.01}
        manager.process_command("maru/command/uuid", data_limit)
        
        manager.account_manager.sell_limit_order.assert_called_with("KRW-BTC", 50000000.0, 0.01)

        # Test Market Sell
        manager.price_ob.get.return_value = None
        data_market = {"action": "sell", "ticker": "KRW-ETH", "volume": 1.0}
        manager.process_command("maru/command/uuid", data_market)
        
        manager.account_manager.sell_market_order.assert_called_with("KRW-ETH", 1.0)

    def test_buy_command_triggers_account(self):
        # Setup
        manager = Manager(virtual=True)
        # Mock account manager
        manager.account_manager = MagicMock()
        manager.dashboard = MagicMock()
        manager.price_ob = MagicMock()
        
        # Test Limit Buy
        data_limit = {"action": "buy", "ticker": "KRW-BTC", "price": 50000000, "volume": 0.01}
        manager.process_command("maru/command/uuid", data_limit)
        
        manager.account_manager.buy_limit_order.assert_called_with("KRW-BTC", 50000000.0, 0.01)

if __name__ == '__main__':
    unittest.main()
