
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.append(os.getcwd())

from account.dbupbit import DBUpbit
from account.repositories import AssetRepository
from account.dtos import AssetDTO

class TestBalanceFiltering(unittest.TestCase):
    def test_get_balances_filtering(self):
        # Setup
        db_upbit = DBUpbit(callback=MagicMock())
        # Inject mock repo
        mock_repo = MagicMock()
        db_upbit.asset_repo = mock_repo
        
        # Mock data: 1 valid, 1 zero-balance, 1 zero-avail-but-locked, 1 zero
        assets = [
            AssetDTO(currency="BTC", balance=Decimal("1.0"), locked=Decimal("0.0"), avg_buy_price=Decimal("50000000"), avg_buy_price_modified=False, unit_currency="KRW"),
            AssetDTO(currency="ETH", balance=Decimal("0.0"), locked=Decimal("0.0"), avg_buy_price=Decimal("3000000"), avg_buy_price_modified=False, unit_currency="KRW"),
            AssetDTO(currency="KRW", balance=Decimal("0.0"), locked=Decimal("1000000.0"), avg_buy_price=Decimal("1"), avg_buy_price_modified=False, unit_currency="KRW"),
            AssetDTO(currency="XRP", balance=Decimal("100.0"), locked=Decimal("0.0"), avg_buy_price=Decimal("1000"), avg_buy_price_modified=False, unit_currency="KRW")
        ]
        mock_repo.get_all.return_value = assets
        
        # Execute
        balances = db_upbit.get_balances()
        
        # Verify
        print(f"\n[TEST] Input Assets: {len(assets)}")
        for a in assets:
            print(f" - {a.currency}: B={a.balance}, L={a.locked}")
            
        print(f"[TEST] Output Balances: {len(balances)}")
        for b in balances:
            print(f" - {b['currency']}: B={b['balance']}, L={b['locked']}")
            
        # Assets with total > 0: BTC, KRW (locked > 0), XRP. ETH should be gone.
        self.assertEqual(len(balances), 3)
        currencies = [b['currency'] for b in balances]
        self.assertIn("BTC", currencies)
        self.assertIn("KRW", currencies)
        self.assertIn("XRP", currencies)
        self.assertNotIn("ETH", currencies)
        
        print("[PASS] Zero balance (ETH) was correctly filtered out.")

if __name__ == "__main__":
    unittest.main()
