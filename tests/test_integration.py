
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

sys.path.append(os.getcwd())

from src.main import Manager
from upbit.upbit_websocket import UpbitWebSocket

class TestManagerIntegration(unittest.TestCase):
    def setUp(self):
        self.manager = Manager()
        # Mock dependencies
        self.manager.dashboard = MagicMock()
        self.manager.account_manager = MagicMock()
        self.manager.messaging = MagicMock()
        self.manager.current_prices = MagicMock()
        self.manager.upbit_websocket = MagicMock(spec=UpbitWebSocket)
        self.manager.upbit_websocket.codes = ["KRW-BTC"] # Pre-subscribed
        self.manager.strategy_manager = MagicMock()
        self.manager.pocket_manager = MagicMock()
        
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
        
        # Setup: Some pockets and strategies to be cleaned up
        mock_pocket = MagicMock()
        mock_pocket.id = "pocket-1"
        self.manager.pocket_manager.get_pockets.return_value = [mock_pocket]
        
        mock_strategy = MagicMock()
        mock_strategy.context.ticker = "KRW-BTC"
        mock_strategy.context.strategy_id = "strat-1"
        self.manager.strategy_manager.strategies = {"strat-1": mock_strategy}
        
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
        # Note: Manager converts price to Decimal, so assert with float or Decimal should work depending on mock
        self.manager.account_manager.sell_limit_order.assert_called_with("KRW-BTC", Decimal("60000"), Decimal("2.5"))

        # Verify Cleanup
        self.manager.pocket_manager.archive_pocket.assert_called_with("pocket-1")
        self.manager.strategy_manager.archive_strategy.assert_called_with("strat-1")

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

    def test_price_command(self):
        """Test the 'price' command functionality."""
        from messaging.interface import MessagingClient
        
        # We need to simulate a task that triggers MCP execution
        # Manager.on_task for MessagingClient calls mymcp.execute_command
        mock_messaging = MagicMock(spec=MessagingClient)
        
        with patch('project_mcp.tools.command_actions.pyupbit.get_current_price') as mock_price:
            mock_price.side_effect = lambda ticker: 50000000.0 if ticker == "KRW-BTC" else 3000000.0
            
            # 1. Single Ticker
            task_single = MagicMock()
            task_single.cls = mock_messaging
            task_single.message = {
                "type": "command",
                "topic": "trading/command/123456",
                "data": {"action": "price", "ticker": "KRW-BTC"}
            }
            self.manager.on_task(task_single)
            
            # 2. Multiple Tickers
            task_multi = MagicMock()
            task_multi.cls = mock_messaging
            task_multi.message = {
                "type": "command",
                "topic": "trading/command/789012",
                "data": {"action": "price", "tickers": ["KRW-BTC", "KRW-ETH"]}
            }
            self.manager.on_task(task_multi)
            
            self.assertEqual(mock_price.call_count, 3) # 1 for single, 2 for multi

if __name__ == "__main__":
    unittest.main()
