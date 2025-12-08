import sqlite3
import os
import time
from models.position import Position, initialize_db

DB_PATH = "test_archive.db"

def verify_archive():
    # Cleanup
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # Initialize
    initialize_db(DB_PATH)

    # 1. Create and Save Position
    pos = Position(ticker="KRW-BTC", entry_price=50000000.0, volume=0.1)
    pos.save(DB_PATH)
    print(f"Position created: {pos.id}")

    # Verify it is in 'positions'
    loaded_positions = Position.load_all(DB_PATH)
    assert len(loaded_positions) == 1
    assert loaded_positions[0].id == pos.id
    print("Verified position in 'positions' table.")

    # 2. Close Position
    pos.close(close_price=55000000.0)
    pos.save(DB_PATH) # Update status in positions table first
    print("Position closed.")

    # 3. Archive Position
    pos.archive(DB_PATH)
    print("Position archived.")

    # 4. Verify Not in 'positions'
    loaded_positions = Position.load_all(DB_PATH)
    assert len(loaded_positions) == 0
    print("Verified position removed from 'positions' table.")

    # 5. Verify In 'position_history'
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM position_history WHERE id = ?", (pos.id,))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == pos.id
        # Check close price
        assert row[9] == 55000000.0
        print("Verified position exists in 'position_history' table.")

    print("Verification Successful!")

    # Cleanup
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

if __name__ == "__main__":
    verify_archive()
