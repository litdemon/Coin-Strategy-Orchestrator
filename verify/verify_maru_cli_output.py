
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import argparse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import types
from unittest.mock import MagicMock, patch

# Load maru module dynamically
maru_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "maru")
maru = types.ModuleType("maru")
with open(maru_path) as f:
    code = f.read()
exec(code, maru.__dict__)
sys.modules["maru"] = maru

class TestMaruCLI(unittest.TestCase):
    @patch('maru.get_mqtt_client')
    def test_cancel_command_sends_correct_payload(self, mock_get_client):
        # Arrange
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.connect.return_value = True
        
        test_uuid = "test-uuid-5678"
        
        # Act
        # We need to simulate argparse parsing or just call send_command directly.
        # send_command is what we want to test primarily.
        maru.send_command("cancel", uuid=test_uuid)
        
        # Assert
        # Check if publish was called with correct topic and payload
        mock_client.publish.assert_called_once()
        args, _ = mock_client.publish.call_args
        topic, payload = args
        
        self.assertTrue(topic.startswith("trading/command/"))
        self.assertEqual(payload["action"], "cancel")
        self.assertEqual(payload["uuid"], test_uuid)
        print(f"Verified payload: {payload}")

if __name__ == "__main__":
    unittest.main()
