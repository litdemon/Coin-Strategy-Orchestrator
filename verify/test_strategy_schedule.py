import sys
import os
import time
import unittest
from unittest.mock import MagicMock
from decimal import Decimal

sys.path.append(os.getcwd())
from strategy.models import StrategyContext, StrategyConfig, StrategyDTO
from strategy.base import StrategyBase
from strategy.manager import StrategyManager
from account.manager import AccountBase

class MockStrategy(StrategyBase):
    def on_tick(self, price: Decimal):
        pass
    def on_schedule(self):
        return None
    def get_state(self):
        return {}
    def restore_state(self, state):
        pass

import tempfile
import shutil

class TestStrategySchedule(unittest.TestCase):
    def setUp(self):
        self.account_manager = MagicMock(spec=AccountBase)
        # Use temp dir/file for testing to ensure persistence across connections
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_strategy.db")
        self.manager = StrategyManager(self.db_path, self.account_manager)
        self.manager.register_strategy("MockStrategy", MockStrategy)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_execution_interval(self):
        # 1. Create a strategy with 1 second interval
        config = {"strategy_type": "MockStrategy", "execution_interval": 1}
        sid = self.manager.create_strategy(
            type_name="MockStrategy", 
            ticker="KRW-BTC", 
            budget=Decimal("10000"), 
            config=config
        )
        
        strategy = self.manager.strategies[sid]
        strategy.on_schedule = MagicMock(return_value=None)
        
        # 2. First call - should run (or not? Logic says current - 0 >= interval)
        # last_exec default is 0. time.time() is huge. So it should run immediately.
        self.manager.on_schedule()
        strategy.on_schedule.assert_called_once()
        strategy.on_schedule.reset_mock()
        
        # 3. Call again immediately - should NOT run (interval 1s not passed)
        self.manager.on_schedule()
        strategy.on_schedule.assert_not_called()
        
        # 4. Wait 1.1s and call - should run
        time.sleep(1.1)
        self.manager.on_schedule()
        strategy.on_schedule.assert_called_once()

if __name__ == '__main__':
    unittest.main()
