import sys
import os
import uuid
import shutil
from typing import List

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.position_manager import PositionManager, PositionEx
from strategy.base import Signal, SignalType

class MockBalance:
    def __init__(self):
        self.balances = {}

    def get_balance(self, ticker):
        return self.balances.get(ticker, 0.0)
    
    def set_balance(self, ticker, amount):
        self.balances[ticker] = amount

class MockCurrentPrice:
    def __init__(self):
        self.prices = {}

    def update(self, market, price):
        self.prices[market] = price

    def get(self, market):
        return self.prices.get(market, 0.0)

def on_signal_callback(position, signals):
    print(f"Callback Signal for {position.ticker}: {[s.type.value for s in signals]}")

def test_position_manager():
    # Use a test DB
    test_db = "test_position_manager.db"
    if os.path.exists(test_db):
        os.remove(test_db)
        
    print("--- Starting PositionManager Test ---")

    # 1. Create Manager
    manager = PositionManager(db_path=test_db)
    
    # 2. Test register_positions_from_balance (requires pyupbit mocking, tricky)
    # We will skip direct pyupbit dependent test or mock it.
    # For now, let's test manual addition via on_order_fill which is cleaner.
    
    # 3. Test on_order_fill
    order_info = {
        'code': 'KRW-BTC',
        'ask_bid': 'bid',
        'state': 'done',
        'volume': 0.1,
        'price': 1000.0
    }
    manager.on_order_fill(order_info)
    
    assert len(manager.positions) == 1
    pos = manager.positions[0]
    assert pos.ticker == 'KRW-BTC'
    assert pos.volume == 0.1
    # Check default strategy
    assert len(pos.strategy_manager.strategies) > 0
    print("on_order_fill test passed.")
    
    # 4. Test update_all (No signal)
    mock_price = MockCurrentPrice()
    mock_price.update('KRW-BTC', 1010.0) # 1% up -> No signal (activation 1% but trailing needs drop)
    
    updated = manager.update_all(mock_price, on_signal_callback)
    
    # 5. Test Signal Generation
    # Strategy: Trailing Stop (5% trail, 1% activation)
    # Price 1000 -> 1010 (1% gain) -> Activated? 
    # Let's bump price to 1100 (10% gain) -> Activated. Highest 1100.
    # Then drop to 1000 (-9%) -> Should trigger close (trail 5%).
    
    mock_price.update('KRW-BTC', 1100.0)
    manager.update_all(mock_price, on_signal_callback)
    
    mock_price.update('KRW-BTC', 1040.0) # > 5% drop from 1100
    
    # Capture print or use callback
    signals_received = []
    def capture_signal(p, s):
        signals_received.extend(s)
        
    updated = manager.update_all(mock_price, capture_signal)
    
    assert updated == True
    assert len(signals_received) > 0
    assert any(s.type == SignalType.CLOSE for s in signals_received)
    
    # Verify post-signal handling (closed and archived)
    # Manager handles closing internal list? No, manager load_positions initially.
    # But update_all iterates self.positions.
    # Handle_signal sets is_closed=True.
    
    # Check if closed
    assert pos.is_closed == True
    
    # Verify it is removed from active list? 
    # Manager.get_active_positions() should return empty.
    assert len(manager.get_active_positions()) == 0
    
    print("Signal handling and Position closing confirmed.")

    # Cleanup
    if os.path.exists(test_db):
        os.remove(test_db)
    print("--- Test Passed ---")

if __name__ == "__main__":
    test_position_manager()
