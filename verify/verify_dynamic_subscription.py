
import unittest
import os
import sys
from unittest.mock import MagicMock
from decimal import Decimal

sys.path.append(os.getcwd())

from src.main import Manager
from upbit.upbit_websocket import UpbitWebSocket

class TestDynamicSubscription(unittest.TestCase):
    def test_buy_new_ticker_subscribes(self):
        # Setup Manager
        manager = Manager(virtual=True)
        
        # Mock dependencies
        manager.dashboard = MagicMock()
        manager.account_manager = MagicMock()
        manager.messaging = MagicMock()
        manager.price_ob = {}
        
        # Mock UpbitWebSocket
        mock_websocket = MagicMock(spec=UpbitWebSocket)
        mock_websocket.codes = ["KRW-BTC"] # Existing subscription
        manager.upbit_websocket = mock_websocket
        
        # 1. Buy existing ticker (KRW-BTC)
        cmd_existing = {
            "action": "buy",
            "ticker": "KRW-BTC",
            "volume": 0.001,
            "price": 50000000
        }
        manager.process_command("trading/command/1", cmd_existing)
        
        # Verify NO add_subscription called
        mock_websocket.add_subscription.assert_not_called()
        
        # 2. Buy NEW ticker (KRW-ETH)
        cmd_new = {
            "action": "buy",
            "ticker": "KRW-ETH",
            "volume": 0.1,
            "price": 3000000
        }
        manager.process_command("trading/command/2", cmd_new)
        
        # Verify add_subscription called with KRW-ETH
        mock_websocket.add_subscription.assert_called_with(["KRW-ETH"])
        print("[PASS] Dynamic subscription triggered for new ticker KRW-ETH")

if __name__ == "__main__":
    unittest.main()
