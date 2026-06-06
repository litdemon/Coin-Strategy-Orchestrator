
import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from project_mcp.tools.command_actions import BuyCommandTool, SellCommandTool, CancelCommandTool
from project_mcp.tools.context import set_execution_context

class TestMCPInterface(unittest.TestCase):
    def setUp(self):
        self.mock_context = MagicMock()
        set_execution_context(self.mock_context)
        
    def test_buy_mcp_execute_named_params(self):
        tool = BuyCommandTool()
        # Mock execute to see what it receives
        tool.execute = MagicMock(return_value={"status": "ok"})
        
        # Simulate Agent call with named params
        result = tool.mcp_execute(ticker="KRW-BTC", won="100000")
        
        # Verify execute was called with correct data structure
        args, kwargs = tool.execute.call_args
        self.assertEqual(kwargs['data']['ticker'], "KRW-BTC")
        self.assertEqual(kwargs['data']['won'], "100000")
        self.assertEqual(kwargs['data']['volume'], "0") # Default value
        self.assertEqual(result, {"status": "ok"})

    def test_sell_mcp_execute_named_params(self):
        tool = SellCommandTool()
        tool.execute = MagicMock(return_value={"status": "ok"})
        
        # Simulate Agent call for "Sell All"
        result = tool.mcp_execute(ticker="KRW-ETH", volume="-1")
        
        args, kwargs = tool.execute.call_args
        self.assertEqual(kwargs['data']['ticker'], "KRW-ETH")
        self.assertEqual(kwargs['data']['volume'], "-1")
        self.assertEqual(result, {"status": "ok"})

    def test_cancel_mcp_execute_named_params(self):
        tool = CancelCommandTool()
        tool.execute = MagicMock(return_value={"status": "ok"})
        
        # Simulate Agent call for cancel by ticker
        tool.mcp_execute(ticker="KRW-XRP")
        args, kwargs = tool.execute.call_args
        self.assertEqual(kwargs['data']['ticker'], "KRW-XRP")
        self.assertEqual(kwargs['data']['uuid'], "") # Default

        # Simulate Agent call for cancel by uuid
        tool.mcp_execute(order_uuid="123456")
        args, kwargs = tool.execute.call_args
        self.assertEqual(kwargs['data']['uuid'], "123456")

if __name__ == "__main__":
    unittest.main()
