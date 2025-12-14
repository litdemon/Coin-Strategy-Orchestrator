
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock
import shutil

sys.path.append(os.getcwd())

from strategy.manager import StrategyManager
from strategy.trailingstop import TrailingStopStrategy, TrailingStopConfig
from strategy.models import StrategyContext

class TestStrategyPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_strategy_persist.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        
        self.account_manager = MagicMock()
        self.manager = StrategyManager(db_path=self.db_path, account_manager=self.account_manager)
        
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_load_strategy(self):
        """Test that strategies are saved to DB and reloaded correctly."""
        # 1. Create a Strategy
        context = StrategyContext(
            strategy_id="test-strat-1",
            ticker="KRW-BTC",
            budget=Decimal("10000"),
            position_id="pos-1"
        )
        config = TrailingStopConfig(
            entry_price=Decimal("50000000"),
            trail_percent=Decimal("0.05")
        )
        strategy = TrailingStopStrategy(context=context, config=config)
        
        self.manager.add_strategy(strategy)
        
        # 2. Simulate Restart (New Manager instance)
        del self.manager
        
        new_manager = StrategyManager(db_path=self.db_path, account_manager=self.account_manager)
        new_manager.register_strategy("trailing_stop", TrailingStopStrategy)
        # Assuming load_strategies is called manually or in init? 
        # StrategyManager usually loads in init or explicit method.
        # Let's check StrategyManager definition if needed. 
        # Usually we call load_strategies() or it's auto.
        # Based on verify_strategy.py, it called load_strategies().
        new_manager.load_strategies()
        
        # 3. Verify Loaded Strategy
        self.assertIn("test-strat-1", new_manager.strategies)
        loaded_strat = new_manager.strategies["test-strat-1"]
        
        self.assertIsInstance(loaded_strat, TrailingStopStrategy)
        self.assertEqual(loaded_strat.context.ticker, "KRW-BTC")
        self.assertEqual(loaded_strat.config.trail_percent, Decimal("0.05"))
        self.assertEqual(loaded_strat.context.position_id, "pos-1")

if __name__ == "__main__":
    unittest.main()
