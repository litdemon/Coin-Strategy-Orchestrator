from pydantic import BaseModel
from decimal import Decimal
from tools.db_interface import DBInterface
import os

# Define a test model
class TestModel(BaseModel, DBInterface):
    name: str
    amount: Decimal
    score: int

def run_verify():
    db_file = "verify_test.db"
    if os.path.exists(db_file):
        os.remove(db_file)
    
    print("1. Initializing DB...")
    TestModel.init_db(db_file)
    
    print("2. Creating instance with Decimal...")
    item = TestModel(name="TestItem", amount=Decimal("123.4567890123456789"), score=100)
    
    print("3. Saving instance...")
    try:
        item.save(db_file)
        print("   Save Success")
    except Exception as e:
        print(f"   Save Failed: {e}")
        return

    print("4. Loading instance...")
    try:
        items = TestModel.load_all(db_file)
        if items:
            loaded_item = items[0]
            print(f"   Loaded: {loaded_item}")
            print(f"   Type of amount: {type(loaded_item.amount)}")
            
            # Verify value match
            if loaded_item.amount == item.amount:
                 print("   Value Match: YES")
            else:
                 print(f"   Value Match: NO ({loaded_item.amount} != {item.amount})")
                 
            # Verify Type (Note: SQLite adaptor stores as str, loading back might imply we need conversion if not automatic)
            # Pydantic should auto-convert str back to Decimal if defined in model!
        else:
            print("   Load Failed: No items found")
    except Exception as e:
        print(f"   Load Error: {e}")
        
    # Clean up
    if os.path.exists(db_file):
        os.remove(db_file)

if __name__ == "__main__":
    run_verify()
