import sys
import os
import uuid
import shutil

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.order_manager import OrderManager, OrderInfoEx

class MockCurrentPrice:
    def __init__(self):
        self.prices = {}

    def update(self, market, price):
        self.prices[market] = price

    def get(self, market):
        return self.prices.get(market, 0.0)

def on_order_complete_callback(order):
    print(f"Callback triggered for order: {order.uuid}, State: {order.state}")

def test_order_manager():
    # Use a test DB
    test_db = "test_order_manager.db"
    if os.path.exists(test_db):
        os.remove(test_db)
        
    print("--- Starting OrderManager Test ---")

    # 1. Create Manager
    manager = OrderManager(on_order_complete=on_order_complete_callback, db_path=test_db)
    
    # 2. Create and Add Order
    order1 = OrderInfoEx(
        uuid=str(uuid.uuid4()),
        side="bid",
        ord_type="limit",
        price=100.0,
        state="wait",
        market="KRW-BTC",
        created_at="2023-01-01",
        reserved_fee=0, remaining_fee=0, paid_fee=0, locked=0, executed_volume=0, trades_count=0
    )
    manager.add_order(order1)
    
    order2 = OrderInfoEx(
        uuid=str(uuid.uuid4()),
        side="ask",
        ord_type="limit",
        price=200.0,
        state="wait",
        market="KRW-ETH",
        created_at="2023-01-01",
        reserved_fee=0, remaining_fee=0, paid_fee=0, locked=0, executed_volume=0, trades_count=0
    )
    manager.add_order(order2)
    
    # Verify orders are in wait list
    assert len(manager.wait_orders) == 2
    print("Orders added successfully.")
    
    # 3. Mock Price and Check Execution (No match)
    mock_price = MockCurrentPrice()
    mock_price.update("KRW-BTC", 110.0) # Bid 100, Price 110 -> No Match
    mock_price.update("KRW-ETH", 190.0) # Ask 200, Price 190 -> No Match
    
    manager.check_execution(mock_price)
    assert len(manager.wait_orders) == 2
    
    # 4. Check Execution (Match Bid)
    mock_price.update("KRW-BTC", 90.0) # Bid 100, Price 90 -> Match!
    manager.check_execution(mock_price)
    
    # Verify order1 is done and removed
    assert len(manager.wait_orders) == 1
    # Check DB
    loaded_order1 = OrderInfoEx.get(order1.uuid, db_path=test_db)
    assert loaded_order1.state == "done"
    print("Bid execution confirmed.")

    # 5. Check Execution (Match Ask)
    mock_price.update("KRW-ETH", 210.0) # Ask 200, Price 210 -> Match!
    manager.check_execution(mock_price)
    
    assert len(manager.wait_orders) == 0
    loaded_order2 = OrderInfoEx.get(order2.uuid, db_path=test_db)
    assert loaded_order2.state == "done"
    print("Ask execution confirmed.")
    
    # Cleanup
    if os.path.exists(test_db):
        os.remove(test_db)
    print("--- Test Passed ---")

if __name__ == "__main__":
    test_order_manager()
