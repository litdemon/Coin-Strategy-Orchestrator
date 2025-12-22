import unittest
from unittest.mock import MagicMock, patch
from src.main import Manager

class MockStrategy:
    def __init__(self, sid, pocket_id=None):
        self.context = MagicMock()
        self.context.strategy_id = sid
        self.context.pocket_id = pocket_id
        self.config = MagicMock()
        self.config.name = "mock"
    
    def summary(self):
        return {"strategy_id": self.context.strategy_id, "status": "ACTIVE"}

class TestManagerInitPersistence(unittest.TestCase):
    @patch('src.main.MessagingFactory')
    @patch('src.main.UpbitWebSocket')
    @patch('src.main.AccountDBManager')
    @patch('src.main.StrategyManager')
    @patch('src.main.PocketManager')
    @patch('src.main.Dashboard')
    def test_init_updates_dashboard_for_all_strategies(self, MockDashboard, MockPocketManager, MockStrategyManager, MockAccount, MockWS, MockMessaging):
        # Setup Mocks
        manager = Manager(virtual=True)
        manager.dashboard = MockDashboard.return_value
        
        # Mock Strategy Manager strategies
        strat_linked = MockStrategy("linked", "pocket-1")
        strat_independent = MockStrategy("independent", None)
        
        mock_sm_instance = MockStrategyManager.return_value
        mock_sm_instance.strategies = {
            "linked": strat_linked,
            "independent": strat_independent
        }
        
        # Mock Pocket Manager
        mock_pm_instance = MockPocketManager.return_value
        mock_pm_instance.pockets = {"pocket-1": MagicMock()} # pocket-1 exists
        
        # Inject mocks into manager
        manager.strategy_manager = mock_sm_instance
        manager.pocket_manager = mock_pm_instance
        
        # Mock other init calls to avoid side effects
        manager.init_account = MagicMock(return_value=["KRW-BTC"])
        manager.init_strategy = MagicMock() # Don't run real init_strategy
        manager.init_pockets = MagicMock() # Don't run real init_pockets
        
        # Execute init
        # We need to suppress the real calls inside init() that we just mocked above
        # But wait, init() calls self.init_strategy(), self.init_pockets().
        # Since we assigned mocks to manager.strategy_manager, we need to make sure init_strategy doesn't overwrite them.
        # We mocked init_strategy method on the instance to do nothing.
        
        manager.init(config={})
        
        # Verify Dashboard Updates
        # Should have called update twice
        # 1. Linked Strategy
        # 2. Independent Strategy
        
        # We might have other updates (like 'log'), so we filter calls
        strategy_updates = []
        for call in manager.dashboard.update.call_args_list:
            args, _ = call
            data = args[0]
            if 'strategy' in data:
                strategy_updates.append(data['strategy']['strategy_id'])
        
        self.assertIn("linked", strategy_updates)
        self.assertIn("independent", strategy_updates)

if __name__ == '__main__':
    unittest.main()
