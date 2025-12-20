import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import threading
import time

from strategy.base import StrategyBase
from strategy.manager import StrategyManager
from strategy.default_strategy import DefaultStrategy, DefaultStrategyConfig
from strategy.models import StrategyContext, Signal, StrategyType

class TestStrategyDisplay(unittest.TestCase):
    def setUp(self):
        self.mock_observer = MagicMock()
        self.mock_repo = MagicMock()
        
        # Patch StrategyManager init to avoid complex setup
        with patch("strategy.manager.StrategyRepository", return_value=self.mock_repo):
            self.manager = StrategyManager(db_path="test_db.db", observer=self.mock_observer)
            self.manager.strategies = {} # Reset

    def test_trailing_stop_display_update(self):
        """Verify DefaultStrategy (TrailingStop) updates display and sets is_updated flag."""
        context = StrategyContext(strategy_id="test_id", ticker="KRW-BTC", budget=Decimal("1000"), last_execution_time=0)
        config = DefaultStrategyConfig(
            name="default", # Updated Name
            type=StrategyType.SELL,
            trail_percent=Decimal("0.1"), # 10%
            entry_price=Decimal("100")
        )
        strategy = DefaultStrategy(context, config)
        
        # 1. Initial State
        self.assertEqual(strategy.display, "Nothing") 
        self.assertFalse(strategy.is_updated) 
        
        # 2. First Tick (Update Highest)
        # Price 100 -> Highest 100 -> Stop Price 90
        strategy.on_tick(Decimal("100"))
        
        expected_display = "TS:90"
        self.assertEqual(strategy.display, expected_display)
        self.assertTrue(strategy.is_updated)
        
        # Reset flag
        strategy.is_updated = False
        
        # 3. Second Tick (No Change)
        strategy.on_tick(Decimal("100"))
        self.assertFalse(strategy.is_updated) 
        
        # 4. Third Tick (New High)
        strategy.on_tick(Decimal("110"))
        # High 110, Stop 99
        self.assertEqual(strategy.display, "TS:99")
        self.assertTrue(strategy.is_updated)

    def test_manager_propagates_updates(self):
        """Verify StrategyManager persists and notifies when is_updated is True."""
        # Setup Mock Strategy
        mock_strategy = MagicMock()
        mock_strategy.context.ticker = "KRW-BTC"
        mock_strategy.context.strategy_id = "test_strat"
        mock_strategy.on_tick.return_value = None # No signal
        mock_strategy.is_updated = True # Simulate update flag set
        
        # Inject
        self.manager.strategies["test_strat"] = mock_strategy
        
        # Setup Repo Mock to return DTO
        mock_dto = MagicMock()
        self.mock_repo.get.return_value = mock_dto
        
        # Execute Manager on_tick
        self.manager.on_tick("KRW-BTC", Decimal("1000"))
        
        # Verify Persistence
        self.mock_repo.save.assert_called_with(mock_dto)
        
        # Verify Notification
        self.mock_observer.on_strategy_updated.assert_called_with(mock_strategy)
        
        # Verify Flag Reset (Mock doesn't automatically reset attributes but we can check if it was set to False)
        # self.assertFalse(mock_strategy.is_updated) 
        # With MagicMock property setting might be tricky to test unless we check setattr calls, but for now this is fine.
        # Actually in `manager.on_tick`: strategy.is_updated = False
        self.assertEqual(mock_strategy.is_updated, False) # MagicMock stores the last assigned value

if __name__ == "__main__":
    unittest.main()
