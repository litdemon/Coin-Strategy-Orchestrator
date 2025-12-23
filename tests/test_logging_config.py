import unittest
import logging
import os
import shutil
import time
from app import setup_logging

class TestLoggingConfig(unittest.TestCase):
    def setUp(self):
        # Create a temp logs dir
        if os.path.exists("logs_test"):
            shutil.rmtree("logs_test")
        os.makedirs("logs_test")
        
        # Patch app.py log_dir using a hack or just modify the global logging?
        # app.py has hardcoded "logs". We can't easily change it without modifying app.py or chdir.
        # Let's chdir to a temp dir.
        self.original_cwd = os.getcwd()
        self.test_dir = "temp_test_logging"
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        
        # Reset logging
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()

    def test_log_rotation_and_format(self):
        setup_logging(console=False)
        
        logger = logging.getLogger("test_logger")
        logger.info("Test Message")
        
        # Check file creation
        log_file = os.path.join("logs", "coin-stratege.log")
        self.assertTrue(os.path.exists(log_file))
        
        # Check content format
        with open(log_file, 'r') as f:
            content = f.read()
            
        print(f"Log Content: {content}")
        
        # Content should have time but not date (e.g., "10:00:00 - INFO - Test Message")
        # And NOT "2024-12-23"
        import datetime
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        self.assertNotIn(today_str, content, "Date should not be in the log line")
        self.assertIn("Test Message", content)
        
        # Verify Handler Type
        root = logging.getLogger()
        handler = [h for h in root.handlers if isinstance(h, logging.handlers.TimedRotatingFileHandler)]
        self.assertTrue(len(handler) > 0, "Should use TimedRotatingFileHandler")
        self.assertEqual(handler[0].when, 'MIDNIGHT')
        self.assertEqual(handler[0].interval, 86400)

if __name__ == '__main__':
    unittest.main()
