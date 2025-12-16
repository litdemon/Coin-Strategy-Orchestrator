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

def setup_logging(console: bool = True):
    """Initialize logging configuration."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    time_format = "%m-%d %H:%M:%S"
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO, 
        filename=os.path.join(log_dir, "coin-stratege.log"), 
        filemode="a+", 
        format=log_format, 
        datefmt=time_format
    )
    
    # Also print to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter(log_format, datefmt=time_format)
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

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
