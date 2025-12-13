
import unittest
from unittest.mock import MagicMock
from src.dashboard import Dashboard, TickerWidget, PositionWidget, StrategyWidget
import time

class TestDashboardWidgets(unittest.TestCase):
    def test_strategy_widget(self):
        w = StrategyWidget("TrailingStop", "0.05")
        self.assertEqual(w.render(), "TrailingStop(0.05)")
        w2 = StrategyWidget("Simple", "")
        self.assertEqual(w2.render(), "Simple")

    def test_position_widget(self):
        strategies = [{'name': 'TS', 'state': 'Active'}]
        w = PositionWidget(pid="123456", strategies=strategies, entry_price=1000, volume=10)
        
        # Test render with price
        rendered = w.render(1100) # 10% profit
        self.assertIn("10.00%", rendered)
        self.assertIn("TS(Active)", rendered)
        self.assertIn("10,000", rendered) # Volume

    @unittest.mock.patch('src.dashboard.pyupbit.get_ohlcv')
    def test_ticker_widget(self, mock_get_ohlcv):
        mock_get_ohlcv.return_value = None # Test fallback to 0.0
        t = TickerWidget("BTC")
        # Mock Candle
        t.candle = MagicMock()
        t.candle.current_price.return_value = 55000
        t.candle.render.return_value = "|||"
        
        # Test update_balance with dict
        t.update_balance({'amount': '0.1', 'avg_buy_price': '50000'})
        self.assertEqual(t.amount, 0.1)
        self.assertEqual(t.avg_buy_price, 50000.0)

        rendered = t.render()
        header = rendered[0]
        # Check for Amount (0.1 * 50000 = 5000)
        self.assertIn("5,000", header)
        # Check for Profit % ((55000 - 50000)/50000 = 10%)
        self.assertIn("10.00%", header)
        # Check Price
        self.assertIn("55,000", header)

if __name__ == '__main__':
    unittest.main()
