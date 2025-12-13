
import unittest
from unittest.mock import MagicMock
import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import Manager

class TestCancelCommand(unittest.TestCase):
    def setUp(self):
        # Mock Manager dependencies
        self.manager = Manager(virtual=True)
        self.manager.dashboard = MagicMock()
        self.manager.account_manager = MagicMock()
        self.manager.messaging = MagicMock()
        self.manager.price_ob = MagicMock()
        # Initialize other components to avoid init errors if any
        # Manager.__init__ creates Queue, Counter which are fine.
        # Manager.init() is where heavy lifting happens, but we can mock what we need.
        # We don't call manager.init() to avoid starting real connections.
        
        # Manually attach mocks that are usually set in init()
        self.manager.strategy_manager = MagicMock()
        self.manager.position_manager = MagicMock()

    def test_process_command_cancel_success(self):
        # Arrange
        uuid = "test-uuid-1234"
        data = {"action": "cancel", "uuid": uuid}
        topic = f"trading/command/{uuid}"
        
        # Mock cancel_order to return something (success)
        self.manager.account_manager.cancel_order.return_value = {"uuid": uuid, "state": "cancel"}
        
        # Act
        self.manager.process_command(topic, data)
        
        # Assert
        self.manager.account_manager.cancel_order.assert_called_once_with(uuid)
        self.manager.dashboard.log.assert_any_call(f"CMD CANCEL: {uuid}")
        self.manager.dashboard.log.assert_any_call("Order Cancelled: {'uuid': 'test-uuid-1234', 'state': 'cancel'}")

    def test_process_command_cancel_fail(self):
        # Arrange
        uuid = "test-uuid-fail"
        data = {"action": "cancel", "uuid": uuid}
        topic = f"trading/command/{uuid}"
        
        # Mock cancel_order to return None (fail)
        self.manager.account_manager.cancel_order.return_value = None
        
        # Act
        self.manager.process_command(topic, data)
        
        # Assert
        self.manager.account_manager.cancel_order.assert_called_once_with(uuid)
        self.manager.dashboard.log.assert_any_call(f"Order Cancel Failed or Not Found: {uuid}")

if __name__ == "__main__":
    unittest.main()
