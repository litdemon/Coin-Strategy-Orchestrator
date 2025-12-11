import sys
import os
import uuid
from decimal import Decimal

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.account_manager import AccountManager
from src.order_manager import OrderManager, OrderInfoEx
from account.models import Balance, Asset

class MockCurrentPrice:
    def __init__(self):
        self.prices = {}

    def update(self, market, price):
        self.prices[market] = price

    def get(self, market):
        return self.prices.get(market, 0.0)

def observer_callback(source, msg):
    print(f"Callback Msg: Type={msg.get('type')} Code={msg.get('code', 'N/A')}")

def test_account_manager():
    # Use a test DB
    test_db = "test_account_manager.db"
    if os.path.exists(test_db):
        os.remove(test_db)
        
    print("--- Starting AccountManager Test ---")
    
    # 1. Setup Models
    Asset.initialize_db(test_db) # Init assets table
    # Create initial balance
    balance = Balance(assets=[
        Asset("KRW", Decimal(1000000), Decimal(0), Decimal(0), False, "KRW"),
        Asset("BTC", Decimal(0), Decimal(0), Decimal(0), False, "KRW")
    ])
    balance.save(test_db)
    
    order_manager = OrderManager(on_order_complete=None, db_path=test_db)
    
    manager = AccountManager(
        order_manager=order_manager, 
        balance=balance, 
        observer_callback=observer_callback
    )
    
    # 2. Test Buy
    # Buy 1 BTC @ 1000 KRW (Total 1000 + fee)
    print("Placing Buy Order...")
    order_id = manager.buy(ticker="KRW-BTC", price=1000.0, volume=1.0)
    assert order_id is not None
    
    # Check Balance Locked (Available KRW reduced)
    # Fee is 0.05% = 0.5 KRW. Total 1000.5
    current_krw = manager.balance.get_balance("KRW")
    print(f"KRW after order: {current_krw}")
    assert current_krw == Decimal("1000000") - Decimal("1000.5")
    
    # 3. Execution (Price Drop)
    mock_price = MockCurrentPrice()
    mock_price.update(ticker="KRW-BTC", price=900.0)
    
    print("Checking Execution...")
    order_manager.check_execution(mock_price)
    
    # Should trigger callback in AccountManager -> _on_order_executed
    # Updated Balance: KRW should remain same (as locked was used), BTC should be +1.0
    new_btc = manager.balance.get_balance("BTC")
    print(f"BTC after fill: {new_btc}")
    assert new_btc == Decimal("1.0")
    
    # 4. Test Sell
    # Sell 0.5 BTC @ 2000 KRW
    print("Placing Sell Order...")
    order_id = manager.sell("KRW-BTC", 2000.0, 0.5)
    
    # Check BTC Locked
    current_btc = manager.balance.get_balance("BTC")
    assert current_btc == Decimal("0.5") # 1.0 - 0.5
    
    # Fill Sell
    mock_price.update("KRW-BTC", 2100.0)
    order_manager.check_execution(mock_price)
    
    # Check KRW Incr
    # Revenue: 0.5 * 2000 = 1000. Fee 0.05% = 0.5. Net 999.5
    expected_krw = (Decimal("1000000") - Decimal("1000.5")) + Decimal("999.5")
    final_krw = manager.balance.get_balance("KRW")
    print(f"Final KRW: {final_krw}")
    assert final_krw == expected_krw
    
    # Cleanup
    if os.path.exists(test_db):
        os.remove(test_db)
    print("--- Test Passed ---")

if __name__ == "__main__":
    test_account_manager()
