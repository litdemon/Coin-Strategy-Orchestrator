import unittest
from decimal import Decimal
import time
from src.dashboard import Dashboard
from src.tui_consumer import TickerWidget, StrategyWidget

class TestDashboardBuyStrategy(unittest.TestCase):
    def test_rendering_orphan_strategy(self):
        dashboard = Dashboard()
        
        # 1. Simulate Strategy Creation Logic (via update)
        # Payload mimicking what comes from StrategyManager/Observer
        strategy_data = {
            'type': 'strategy.update',
            'payload': {
                'strategy_id': 'strat-123',
                'name': 'scalping',
                'type': 'buy',
                'ticker': 'KRW-BTC',
                'pocket_id': None,
                'status': 'ACTIVE',
                'config': {},
                'display': 'Init'
            }
        }
        
        # Process Update (goes through StateStore → TUIConsumer subscriber)
        dashboard._process_item(strategy_data)
        time.sleep(0.05)  # let subscriber fire

        # 2. Verify Ticker Widget Created
        registry = dashboard._tui.registry
        self.assertIn('KRW-BTC', registry)
        ticker_widget = registry['KRW-BTC']
        self.assertIsInstance(ticker_widget, TickerWidget)

        # 3. Verify Strategy Widget Created and Attached
        self.assertIn('strat-123', ticker_widget.children)
        strat_widget = ticker_widget.children['strat-123']
        self.assertIsInstance(strat_widget, StrategyWidget)
        self.assertEqual(strat_widget.name, 'scalping')
        
        # 4. Verify Rendering
        output = ticker_widget.render()
        print(f"Render Output:\n{output}")
        
        self.assertIn("Strategies:", output)
        self.assertIn("scalping", output)
        self.assertIn("[Init]", output)

if __name__ == '__main__':
    unittest.main()
