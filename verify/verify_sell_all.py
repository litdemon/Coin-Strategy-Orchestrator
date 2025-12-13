
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.append(os.getcwd())

from src.main import Manager

class TestSellAll(unittest.TestCase):
    def test_sell_all_logic(self):
        # Mock dependencies
        mock_dashboard = MagicMock()
        mock_account_manager = MagicMock()
        mock_messaging = MagicMock()
        mock_strategy_manager = MagicMock()
        mock_position_manager = MagicMock()
        
        # Init Manager with mocks
        manager = Manager(virtual=True)
        # Inject mocks manually since init() is not called or overrides them
        manager.dashboard = mock_dashboard
        manager.account_manager = mock_account_manager
        manager.messaging = mock_messaging
        manager.strategy_manager = mock_strategy_manager
        manager.position_manager = mock_position_manager
        manager.price_ob = {} # Mock price orderbook
        
        # Setup specific mock behavior
        mock_account_manager.get_balance.return_value = Decimal("2.5") # Balance
        
        # Simulate Sell Command with volume = -1 (Sell All)
        cmd_data = {
            "action": "sell",
            "ticker": "KRW-BTC",
            "volume": -1, # Trigger
            "price": "60000",
            "won": None
        }
        
        manager.process_command("trading/command/fake-uuid", cmd_data)
        
        # Verify get_balance called
        mock_account_manager.get_balance.assert_called_with("KRW-BTC")
        
        # Verify sell_limit_order called with REPLACE volume (2.5)
        mock_account_manager.sell_limit_order.assert_called_with("KRW-BTC", 60000.0, 2.5)
        print("[PASS] Sell All Logic verified: Volume -1 replaced by Balance 2.5")

if __name__ == "__main__":
    unittest.main()
