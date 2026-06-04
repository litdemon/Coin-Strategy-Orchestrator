import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import time
import json
import io
import sys

from src.main import Manager
from strategy.models import StrategyType

class TestMaruStrategy(unittest.TestCase):
    def setUp(self):
        # Mock dependencies
        self.mock_messaging = MagicMock()
        
        # Patch Manager's components
        self.patcher_strategy = patch('src.main.StrategyManager')
        self.mock_strategy_manager_cls = self.patcher_strategy.start()
        self.mock_strategy_manager = self.mock_strategy_manager_cls.return_value
        
        # Patch UpbitWebSocket
        self.patcher_ws = patch('src.main.UpbitWebSocket')
        self.mock_ws_cls = self.patcher_ws.start()
        self.mock_ws = self.mock_ws_cls.return_value
        self.mock_ws.codes = [] # Mock codes list

        # Prevent live Upbit API call inside process_command
        self.patcher_price = patch('src.main.pyupbit.get_current_price', return_value=None)
        self.patcher_price.start()

        self.manager = Manager()
        self.manager.messaging = self.mock_messaging
        self.manager.strategy_manager = self.mock_strategy_manager
        self.manager.upbit_websocket = self.mock_ws
        self.manager.dashboard = MagicMock() # Mock dashboard

    def tearDown(self):
        self.patcher_strategy.stop()
        self.patcher_ws.stop()
        self.patcher_price.stop()

    def test_process_strategy_buy_command(self):
        """Verify processing of strategy buy command."""
        # Mock current price for volume calculation
        # Budget 10000 / (Price 1000 * (1 + 0.0005)) = 10000 / 1000.5 = 9.9950025
        self.patcher_price.stop() # stop the return_value=None patch
        with patch('src.main.pyupbit.get_current_price', return_value=1000.0):
            cmd_payload = {
                "action": "strategy",
                "sub_action": "create",
                "type": "buy",
                "ticker": "KRW-BTC",
                "budget": "10000",
                "name": "scalping_strategy",
                "reply_to": "reply/topic"
            }
            
            # Execute
            self.manager.process_command("trading/command/1234", cmd_payload)
            
            # Verify Strategy Creation
            self.mock_strategy_manager.create_strategy.assert_called_once()
            call_args = self.mock_strategy_manager.create_strategy.call_args[1]
            
            self.assertEqual(call_args['name'], "scalping_strategy")
            self.assertEqual(call_args['type'], StrategyType.BUY)
            self.assertEqual(call_args['ticker'], "KRW-BTC")
            self.assertEqual(call_args['budget'], Decimal("10000"))
            
            # Expected Volume: 10000 / (1000 * 1.0005) = 9.99500249875...
            expected_volume = Decimal("10000") / (Decimal("1000") * Decimal("1.0005"))
            self.assertEqual(call_args['config']['buy_amount'], expected_volume)
        
        # Verify WebSocket Subscription
        self.mock_ws.add_subscription.assert_called_with(["KRW-BTC"])
        
        # Verify Reply
        self.mock_messaging.publish.assert_called()
        topic, payload = self.mock_messaging.publish.call_args[0]
        self.assertEqual(topic, "reply/topic")
        self.assertIn("Strategy Created", payload["text"])

    def test_invalid_strategy_params(self):
        """Verify handling of invalid params."""
        cmd_payload = {
            "action": "strategy",
            "sub_action": "create",
            "type": "buy",
            "ticker": "", # Invalid
            "budget": "10000"
        }
        
        self.manager.process_command("trading/command/1234", cmd_payload)
        
        self.mock_strategy_manager.create_strategy.assert_not_called()
        # Should verify log but mock dashboard log is generic. simple assumption is fine.

if __name__ == '__main__':
    unittest.main()
