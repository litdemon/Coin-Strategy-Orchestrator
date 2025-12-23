import os
import sys
import time
import logging
import traceback
import argparse
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import Manager

import logging.handlers

def setup_logging(console: bool = True):
    """Initialize logging configuration."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    # Date removed from format, only time
    time_format = "%H:%M:%S"
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    if root_logger.handlers:
        root_logger.handlers = []

    # File Handler - Timed Rotation (Daily at midnight)
    log_file = os.path.join(log_dir, "coin-stratege.log")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1, # 1 day
        backupCount=30, # Keep 30 days
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=time_format))
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    
    # Console Handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(log_format, datefmt=time_format))
        root_logger.addHandler(console_handler)

def main():
    parser = argparse.ArgumentParser(description="Coin Strategy Bot")
    parser.add_argument('--mode', choices=['virtual', 'real'], default='virtual', help='Running mode: virtual or real (upbit)')
    args = parser.parse_args()

    # Setup Logging
    setup_logging(console=False)
    logger = logging.getLogger(__name__)
    
    mode_str = args.mode.lower()
    is_virtual = True
    if mode_str in ['real']:
        is_virtual = False
    
    logger.info(f"Starting Coin Strategy Bot in {mode_str.upper()} mode")

    manager = Manager(virtual=is_virtual)
    
    # Default Configuration
    config = {
        "messaging": {
            "broker_type": "mqtt",
            "mqtt": {
                "host": "mqtt.toybox7.net",
                "port": 1883,
                "client_id": f"strategy_manager_{int(time.time())}"
            }
        },
        "account": {
            "initial_balance": 10000000,
            "fees": {
                "KRW": 0.0005  # 0.05%
            }
        }
    }
    
    manager.init(config=config)
    try:
        # Run loop
        while True:
            manager.run()
    except KeyboardInterrupt:
        logger.info("Stopping...")
        manager.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()
