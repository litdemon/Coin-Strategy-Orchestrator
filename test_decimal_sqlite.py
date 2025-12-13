import sqlite3
from decimal import Decimal

def test_sqlite_decimal():
    db_path = ":memory:"
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE test (name TEXT, amount TEXT)") # DBInterface maps unkown types to TEXT
            
            # Case 1: Inserting Decimal directly
            try:
                val = Decimal("10.505")
                conn.execute("INSERT INTO test (name, amount) VALUES (?, ?)", ("item1", val))
                print("SUCCESS: Inserted Decimal directly")
            except Exception as e:
                print(f"FAILURE: Could not insert Decimal directly: {e}")

            # Case 2: Reading back
            try:
                cursor = conn.execute("SELECT amount FROM test WHERE name='item1'")
                row = cursor.fetchone()
                if row:
                    print(f"Read back value: {row[0]} (Type: {type(row[0])})")
                else:
                    print("Row not found")
            except Exception as e:
                print(f"Read error: {e}")

    except Exception as e:
        print(f"General error: {e}")

if __name__ == "__main__":
    test_sqlite_decimal()
