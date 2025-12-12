import logging
import time
import os
from decimal import Decimal
from strategy.manager import StrategyManager
from strategy.tailingstop import TrailingStopStrategy, TrailingStopConfig
from strategy.buy_strategy import BuyStrategy, BuyStrategyConfig
from account.dbupbit import DBUpbit

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY")

DB_PATH = "verify_strategy.db"
ACCOUNT_DB_PATH = "verify_account.db"

def clean_dbs():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(ACCOUNT_DB_PATH):
        os.remove(ACCOUNT_DB_PATH)

def test_strategy_features():
    clean_dbs()
    
    # 1. Initialize Managers
    acc_manager = DBUpbit(db_path=ACCOUNT_DB_PATH)
    manager = StrategyManager(db_path=DB_PATH, account_manager=acc_manager)
    
    # 2. Register Strategies
    manager.register_strategy("trailing_stop", TrailingStopStrategy)
    manager.register_strategy("buy_strategy", BuyStrategy)
    
    logger.info("--- Test 1: Position Linking ---")
    # Strategy linked to Position "POS-123"
    ts_config = {
        "trail_percent": "0.05",
        "activation_percent": "0.1",
        "entry_price": "100"
    }
    
    pos_strategy_id = manager.create_strategy(
        type_name="trailing_stop",
        ticker="KRW-BTC",
        budget=Decimal("10000"),
        config=ts_config,
        position_id="POS-123"
    )
    
    assert manager.strategies[pos_strategy_id].context.position_id == "POS-123"
    logger.info("Position Linking Verified")
    
    logger.info("--- Test 2: Scheduled Execution ---")
    # Buy Strategy with 1 second interval
    buy_config = {
        "buy_amount": "5000",
        "execution_interval": 1
    }
    
    buy_strategy_id = manager.create_strategy(
        type_name="buy_strategy",
        ticker="KRW-ETH",
        budget=Decimal("100000"),
        config=buy_config
    )
    
    logger.info("Simulating Schedule Loop (Wait 1.5s)...")
    time.sleep(1.5)
    
    # Trigger Schedule
    manager.on_schedule()
    
    # Verify that a signal was generated (indirectly via Logs or Mock, here we check state)
    strategy = manager.strategies[buy_strategy_id]
    logger.info(f"Buy Strategy State: {strategy.get_state()}")
    
    # Last execution time should be updated
    assert strategy.last_execution_time > 0
    
    logger.info("--- Test 3: Persistence with New Fields ---")
    # Restart Manager
    del manager
    manager2 = StrategyManager(db_path=DB_PATH, account_manager=acc_manager)
    manager2.register_strategy("trailing_stop", TrailingStopStrategy)
    manager2.register_strategy("buy_strategy", BuyStrategy)
    manager2.load_strategies()
    
    restored_ts = manager2.strategies[pos_strategy_id]
    assert restored_ts.context.position_id == "POS-123"
    
    restored_buy = manager2.strategies[buy_strategy_id]
    assert restored_buy.last_execution_time > 0
    
    logger.info("Verification Passed!")
    clean_dbs()

if __name__ == "__main__":
    test_strategy_features()
