
import unittest
import os
import sys
from unittest.mock import MagicMock
from decimal import Decimal

sys.path.append(os.getcwd())

from src.pocket_manager import PocketManager, Pocket
from strategy.models import Signal, SignalType

class MockObserver:
    def __init__(self):
        self.created = []
        self.updated = []
        self.deleted = []
        self.loaded = []
        
    def on_pocket_created(self, pos):
        self.created.append(pos)
        
    def on_pocket_updated(self, pos):
        self.updated.append(pos)
        
    def on_pocket_deleted(self, pos):
        self.deleted.append(pos)

    def on_pocket_loaded(self, pos):
        self.loaded.append(pos)

class TestPocketManager(unittest.TestCase):
    def setUp(self):
        self.test_db = "test_pocket.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        self.observer = MockObserver()
        self.manager = PocketManager(db_path=self.test_db, observer=self.observer)
        self.manager.init()
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_create_pocket(self):
        """Test that creating a pocket notifies observer."""
        ticker = 'KRW-BTC'
        price = Decimal("50000000.0")
        volume = Decimal("0.1")
        
        pos = self.manager.create_pocket(ticker, price, volume)
        
        # Verify pocket created
        pockets = self.manager.get_pockets('KRW-BTC')
        self.assertEqual(len(pockets), 1)
        self.assertEqual(pos.ticker, 'KRW-BTC')
        self.assertEqual(pos.volume, volume)
        self.assertEqual(pos.entry_price, price)
        self.assertFalse(pos.is_closed)
        
        # Verify Observer Notification
        self.assertEqual(len(self.observer.created), 1)
        self.assertEqual(self.observer.created[0], pos)

    def test_close_pocket(self):
        """Test that closing a pocket notifies observer."""
        # 1. Create Pocket
        pos = self.manager.create_pocket(ticker='KRW-BTC', entry_price=Decimal("50000000"), volume=Decimal("0.1"))
        pocket_id = pos.id
        
        # Verify creation callback
        self.assertEqual(len(self.observer.created), 1)
        
        # 2. Close Pocket
        self.manager.close_pocket(pocket_id)
        
        # 3. Close Pocket
        close_price = Decimal("60000000")
        self.manager.closed_pocket(pocket_id, close_price)
        # Reload
        pos = self.manager.get_pocket(pocket_id)
        self.assertTrue(pos.is_closed)
        self.assertEqual(pos.close_price, close_price)
        
        # Verify update callback (Status changed)
        self.assertEqual(len(self.observer.updated), 2)
        self.assertEqual(self.observer.updated[0].id, pos.id)
        self.assertEqual(self.observer.updated[0].status, "closed")

    def test_archive_pocket(self):
        """Test that archiving a pocket notifies observer."""
        pos = self.manager.create_pocket(ticker='KRW-BTC', entry_price=Decimal("50000000"), volume=Decimal("0.1"))
        
        self.manager.archive_pocket(pos.id)
        
        # Verify deleted callback
        self.assertEqual(len(self.observer.deleted), 1)
        self.assertEqual(self.observer.deleted[0].id, pos.id)
        
        # Verify removed from memory
        self.assertIsNone(self.manager.get_pocket(pos.id))

    def test_loader_observer(self):
        """Test that loading pockets on init notifies observer (if implemented)."""
        # 1. Populate DB directly
        manager1 = PocketManager(db_path=self.test_db)
        manager1.init()
        manager1.create_pocket(ticker='KRW-ETH', entry_price=Decimal("3000000"), volume=Decimal("1"))
        del manager1 # Close connection
        
        # 2. New Manager with Observer
        observer = MockObserver()
        manager2 = PocketManager(db_path=self.test_db, observer=observer)
        manager2.init() # Should trigger on_pocket_loaded
        
        self.assertEqual(len(observer.loaded), 1)
        self.assertEqual(observer.loaded[0].ticker, 'KRW-ETH')

