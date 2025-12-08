from account.models import Asset, Balance
from decimal import Decimal
import os

def verify_asset_db():
    db_path = "test_account.db"
    
    # Remove existing db if exists
    if os.path.exists(db_path):
        os.remove(db_path)

    # Create dummy data
    data = [
        {'currency': 'KRW', 'balance': '1000000', 'locked': '0.0', 'avg_buy_price': '0', 'avg_buy_price_modified': True, 'unit_currency': 'KRW'},
        {'currency': 'BTC', 'balance': '0.5', 'locked': '0.0', 'avg_buy_price': '50000000', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}
    ]
    
    # Create Balance object
    balance = Balance.from_list(data)
    print("Initial Balance:", balance)

    # Save to DB
    balance.save(db_path)
    print("Saved to DB.")

    # Load from DB
    loaded_balance = Balance.load(db_path)
    print("Loaded from DB:", loaded_balance)

    # Verify
    assert len(loaded_balance.assets) == 2
    assert loaded_balance.assets[0].currency == 'KRW'
    assert loaded_balance.assets[0].balance == Decimal('1000000')
    assert loaded_balance.assets[1].currency == 'BTC'
    assert loaded_balance.assets[1].balance == Decimal('0.5')
    
    print("Verification Successful!")
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    verify_asset_db()
