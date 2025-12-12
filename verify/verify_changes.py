import unittest
from unittest.mock import MagicMock
import sys
import os
import json
from decimal import Decimal

# Add project root to sys.path
sys.path.append(os.getcwd())

# Import Manager (need to mock dependencies first if they run at import time, but functionality imports usually ok)
# However, Manager imports PositionManager, etc.
# We will rely on mocking instance attributes.

from src.main import Manager

class TestManagerCommand(unittest.TestCase):
    def setUp(self):
        # Instantiate Manager without calling init() which connects to MQTT/WS
        # Manager.__init__ creates Dashboard, Account. We can mock them.
        self.manager = Manager(virtual=True)
        
        # Mock dependencies
        self.manager.dashboard = MagicMock()
        self.manager.account_manager = MagicMock()
        self.manager.messaging = MagicMock()
        self.manager.price_ob = MagicMock()
        self.manager.position_manager = MagicMock() # Mock position manager
        
        # Mock price_ob.get behavior
        self.manager.price_ob.get.return_value = 50000.0

    def test_account_command(self):
        # Setup
        # Return Decimal to reproduce the issue
        self.manager.account_manager.get_balances.return_value = [{"currency": "BTC", "balance": Decimal("1.0")}]
        data = {"action": "account"}
        
        # Execute (use a mock topic with UUID)
        self.manager.process_command("trading/command/TEST-UUID", data)
        
        # Verify
        self.manager.account_manager.get_balances.assert_called_once()
        # Verify it was converted to float
        self.manager.messaging.publish.assert_called_with(
            "trading/response/TEST-UUID/account", 
            [{"currency": "BTC", "balance": 1.0}]
        )

    def test_buy_command_with_price(self):
        data = {"action": "buy", "ticker": "KRW-BTC", "volume": 0.1, "price": 40000}
        self.manager.process_command("trading/command/TEST-UUID", data)
        self.manager.dashboard.log.assert_any_call("CMD BUY: KRW-BTC 0.1 @ 40000")

    def test_buy_command_without_price(self):
        data = {"action": "buy", "ticker": "KRW-BTC", "volume": 0.1, "price": None}
        self.manager.process_command("trading/command/TEST-UUID", data)
        
        # Verify it used current price (50000.0)
        self.manager.price_ob.get.assert_called_with("KRW-BTC")
        self.manager.dashboard.log.assert_any_call("CMD BUY: KRW-BTC 0.1 @ 50000.0")

    def test_sell_command_without_price(self):
        data = {"action": "sell", "ticker": "KRW-ETH", "volume": 1.0, "price": None}
        self.manager.process_command("trading/command/TEST-UUID", data)
        
        # Verify it used current price
        self.manager.price_ob.get.assert_called_with("KRW-ETH")
        self.manager.dashboard.log.assert_any_call("CMD SELL: KRW-ETH 1.0 @ 50000.0")

if __name__ == '__main__':
    unittest.main()
