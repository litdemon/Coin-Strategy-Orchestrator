
import unittest
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from account.manager import AccountDBManager
from account.dbupbit import DBTradeManager
from account.dtos import AssetDTO, OrderDTO
from account.exceptions import InsufficientBalanceException

class TestAccount(unittest.TestCase):
    def setUp(self):
        # Mock callback
        self.mock_callback = MagicMock()
        # Initialize DBTradeManager with memory DB for speed/isolation if possible, 
        # but DBTradeManager hardcodes file path or uses Repositories.
        # Ideally we mock the repositories or use a temp file.
        # For simplicity, we'll mock the repositories attached to DBTradeManager.
        
        self.db_upbit = DBTradeManager(callback=self.mock_callback)
        self.db_upbit.asset_repo = MagicMock()
        self.db_upbit.order_repo = MagicMock()
        
        # AccountDBManager wrapper
        self.account = AccountDBManager(callback=self.mock_callback)
        self.account.manager = self.db_upbit # Inject mocked DBTradeManager
        
    def test_get_balances_filtering(self):
        """Test that get_balances filters out zero-volume assets."""
        assets = [
            AssetDTO(currency="BTC", balance=Decimal("1.0"), locked=Decimal("0.0"), avg_buy_price=Decimal("50000000"), avg_buy_price_modified=False, unit_currency="KRW"),
            AssetDTO(currency="ETH", balance=Decimal("0.0"), locked=Decimal("0.0"), avg_buy_price=Decimal("3000000"), avg_buy_price_modified=False, unit_currency="KRW"), # Should be filtered
            AssetDTO(currency="KRW", balance=Decimal("0.0"), locked=Decimal("1000000.0"), avg_buy_price=Decimal("1"), avg_buy_price_modified=False, unit_currency="KRW"),
            AssetDTO(currency="XRP", balance=Decimal("100.0"), locked=Decimal("0.0"), avg_buy_price=Decimal("1000"), avg_buy_price_modified=False, unit_currency="KRW")
        ]
        self.db_upbit.asset_repo.get_all.return_value = assets
        
        balances = self.account.get_balances()
        
        # BTC, KRW (locked), XRP should be present. ETH should be absent.
        currencies = [b['currency'] for b in balances]
        self.assertIn("BTC", currencies)
        self.assertIn("KRW", currencies)
        self.assertIn("XRP", currencies)
        self.assertNotIn("ETH", currencies)
        self.assertEqual(len(balances), 3)

    def test_create_order_insufficient_balance(self):
        """Test validation for insufficient balance."""
        # Setup KRW balance: 1M available
        krw_asset = AssetDTO(currency="KRW", balance=Decimal("1000000"), locked=Decimal("0"), avg_buy_price=Decimal("1"), avg_buy_price_modified=False, unit_currency="KRW")
        self.db_upbit.asset_repo.get.return_value = krw_asset
        
        # Try to buy 1 BTC at 50M (Cost 50M)
        with self.assertRaises(InsufficientBalanceException):
            self.db_upbit.create_order(
                market="KRW-BTC", 
                side="bid", 
                ord_type="limit", 
                price=Decimal("50000000"), 
                volume=Decimal("1")
            )
            
    def test_create_order_locking(self):
        """Test that funds are locked upon order creation."""
        # Setup KRW: 100M
        krw_asset = AssetDTO(currency="KRW", balance=Decimal("100000000"), locked=Decimal("0"), avg_buy_price=Decimal("1"), avg_buy_price_modified=False, unit_currency="KRW")
        self.db_upbit.asset_repo.get.return_value = krw_asset
        
        # Create Order: Buy 1 BTC @ 50M
        self.db_upbit.create_order(
            market="KRW-BTC",
            side="bid",
            ord_type="limit",
            price=Decimal("50000000"),
            volume=Decimal("1")
        )
        
        # Verify asset_repo.save was called with updated balance/locked
        # save is called 2 times (once for locking, once for order?)
        # DBTradeManager logic: 
        # 1. Lock funds -> repo.save(asset)
        # 2. Save order -> repo.save(order)
        
        # Check the asset passed to save
        saved_asset = self.db_upbit.asset_repo.save.call_args[0][0]
        self.assertEqual(saved_asset.currency, "KRW")
        # Cost = 50M + 0.05% fee = 50,025,000
        expected_locked = Decimal("50000000") * Decimal("1.0005")
        self.assertEqual(saved_asset.locked, expected_locked)
        self.assertEqual(saved_asset.balance, Decimal("100000000") - expected_locked)

    def test_market_buy_locking(self):
        """Test locking for market buy orders."""
        # Valid price provided
        krw_asset = AssetDTO(currency="KRW", balance=Decimal("100000000"), locked=Decimal("0"), avg_buy_price=Decimal("1"), avg_buy_price_modified=False, unit_currency="KRW")
        self.db_upbit.asset_repo.get.return_value = krw_asset
        
        # Market Buy: 1 BTC estimated at 50M
        self.db_upbit.create_order(
            market="KRW-BTC",
            side="bid",
            ord_type="market",
            price=Decimal("50000000"), # Estimated price pass-through
            volume=Decimal("1")
        )
        
        saved_asset = self.db_upbit.asset_repo.save.call_args[0][0]
        expected_locked = Decimal("50000000") * Decimal("1.0005")
        self.assertEqual(saved_asset.locked, expected_locked)

if __name__ == "__main__":
    unittest.main()
