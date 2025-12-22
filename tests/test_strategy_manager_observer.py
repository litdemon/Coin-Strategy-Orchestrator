import unittest
from unittest.mock import MagicMock
from decimal import Decimal
import tempfile
import shutil
import os

from strategy.manager import StrategyManager, StrategyObserver
from strategy.models import StrategyType
from strategy.base import StrategyBase

class MockStrategy(StrategyBase):
    def on_tick(self, price): pass
    def get_state(self): return {}
    def restore_state(self, state): pass

class TestStrategyManagerObserver(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.observer = MagicMock(spec=StrategyObserver)
        self.manager = StrategyManager(self.db_path, self.observer)
        self.manager.register_strategy("mock", MockStrategy)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_create_strategy_notifies_observer_with_instance(self):
        # Create strategy
        sid = self.manager.create_strategy(
            name="mock",
            type=StrategyType.BUY,
            ticker="KRW-BTC",
            budget=Decimal("100"),
            config={"name": "mock", "type": StrategyType.BUY}
        )
        
        # Verify observer called
        self.observer.on_strategy_created.assert_called_once()
        
        # Check argument
        args, _ = self.observer.on_strategy_created.call_args
        passed_obj = args[0]
        
        # Assert it's an instance of StrategyBase (MockStrategy), NOT StrategyDTO
        self.assertIsInstance(passed_obj, MockStrategy)
        self.assertNotIsInstance(passed_obj, dict) # DTO is Pydantic, not dict, but check anyway
        
        # Double check it has correct context
        self.assertEqual(passed_obj.context.strategy_id, sid)

if __name__ == '__main__':
    unittest.main()
