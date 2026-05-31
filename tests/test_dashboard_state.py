import json
import unittest
from decimal import Decimal
from src.dashboard_state import DashboardStateStore


class TestDashboardStateStore(unittest.TestCase):

    def setUp(self):
        self.store = DashboardStateStore()

    # ── snapshot serialization ──────────────────────────────────────────────

    def test_snapshot_is_json_serializable(self):
        self.store.apply_event('asset.update', {
            'currency': 'BTC',
            'balance': Decimal('0.01'),
            'avg_buy_price': Decimal('50000000'),
            'locked': Decimal('0'),
        })
        snap = self.store.snapshot()
        # Must not raise
        json.dumps(snap)

    def test_decimal_converted_to_str_in_snapshot(self):
        self.store.apply_event('asset.update', {
            'currency': 'BTC',
            'balance': Decimal('0.5'),
            'locked': Decimal('0'),
        })
        snap = self.store.snapshot()
        asset = snap['tickers']['KRW-BTC']['asset']
        self.assertIsInstance(asset['balance'], str)

    # ── asset.update ────────────────────────────────────────────────────────

    def test_asset_update_creates_ticker_entry(self):
        self.store.apply_event('asset.update', {
            'currency': 'BTC',
            'balance': '0.5',
            'avg_buy_price': '45000000',
            'locked': '0',
        })
        snap = self.store.snapshot()
        self.assertIn('KRW-BTC', snap['tickers'])
        self.assertEqual(snap['tickers']['KRW-BTC']['asset']['balance'], '0.5')

    # ── ticker.update ───────────────────────────────────────────────────────

    def test_ticker_update_stores_trade_price(self):
        self.store.apply_event('ticker.update', {
            'code': 'KRW-BTC',
            'trade_price': 52000000,
        })
        snap = self.store.snapshot()
        self.assertEqual(snap['tickers']['KRW-BTC']['trade_price'], 52000000)

    # ── pocket.update ───────────────────────────────────────────────────────

    def test_pocket_update_indexed_in_tickers_and_flat(self):
        self.store.apply_event('pocket.update', {
            'id': 'pocket-1',
            'ticker': 'KRW-BTC',
            'entry_price': '50000000',
            'volume': '0.01',
            'status': 'ACTIVE',
        })
        snap = self.store.snapshot()
        self.assertIn('pocket-1', snap['pockets'])
        self.assertIn('pocket-1', snap['tickers']['KRW-BTC']['pockets'])

    # ── strategy.update ─────────────────────────────────────────────────────

    def test_strategy_update_nested_under_pocket(self):
        self.store.apply_event('pocket.update', {
            'id': 'pocket-1',
            'ticker': 'KRW-BTC',
            'entry_price': '50000000',
            'volume': '0.01',
            'status': 'ACTIVE',
        })
        self.store.apply_event('strategy.update', {
            'strategy_id': 'strat-1',
            'name': 'default',
            'ticker': 'KRW-BTC',
            'pocket_id': 'pocket-1',
            'status': 'ACTIVE',
        })
        snap = self.store.snapshot()
        self.assertIn('strat-1', snap['strategies'])
        self.assertIn('strat-1', snap['pockets']['pocket-1']['strategies'])

    def test_orphan_strategy_nested_under_ticker(self):
        self.store.apply_event('strategy.update', {
            'strategy_id': 'strat-orphan',
            'name': 'scalping',
            'ticker': 'KRW-ETH',
            'pocket_id': None,
            'status': 'ACTIVE',
        })
        snap = self.store.snapshot()
        self.assertIn('strat-orphan', snap['tickers']['KRW-ETH']['strategies'])

    # ── order.update ────────────────────────────────────────────────────────

    def test_order_update_added_and_removed_on_done(self):
        self.store.apply_event('order.update', {
            'uuid': 'order-1',
            'code': 'KRW-BTC',
            'state': 'wait',
            'side': 'bid',
        })
        snap = self.store.snapshot()
        self.assertIn('order-1', snap['orders'])

        self.store.apply_event('order.update', {
            'uuid': 'order-1',
            'code': 'KRW-BTC',
            'state': 'done',
            'side': 'bid',
        })
        snap2 = self.store.snapshot()
        self.assertNotIn('order-1', snap2['orders'])

    def test_order_removed_on_cancel(self):
        self.store.apply_event('order.update', {
            'uuid': 'order-2',
            'code': 'KRW-BTC',
            'state': 'wait',
        })
        self.store.apply_event('order.update', {
            'uuid': 'order-2',
            'code': 'KRW-BTC',
            'state': 'cancel',
        })
        snap = self.store.snapshot()
        self.assertNotIn('order-2', snap['orders'])

    # ── entity.remove ───────────────────────────────────────────────────────

    def test_entity_remove_strategy(self):
        self.store.apply_event('pocket.update', {
            'id': 'pocket-1',
            'ticker': 'KRW-BTC',
            'entry_price': '50000000',
            'volume': '0.01',
            'status': 'ACTIVE',
        })
        self.store.apply_event('strategy.update', {
            'strategy_id': 'strat-1',
            'ticker': 'KRW-BTC',
            'pocket_id': 'pocket-1',
            'status': 'ACTIVE',
        })
        self.store.apply_event('entity.remove', {'id': 'strat-1'})
        snap = self.store.snapshot()
        self.assertNotIn('strat-1', snap['strategies'])
        self.assertNotIn('strat-1', snap['pockets']['pocket-1'].get('strategies', {}))

    def test_entity_remove_pocket(self):
        self.store.apply_event('pocket.update', {
            'id': 'pocket-2',
            'ticker': 'KRW-ETH',
            'entry_price': '3000000',
            'volume': '0.1',
            'status': 'ACTIVE',
        })
        self.store.apply_event('entity.remove', {'id': 'pocket-2'})
        snap = self.store.snapshot()
        self.assertNotIn('pocket-2', snap['pockets'])
        self.assertNotIn('pocket-2', snap['tickers'].get('KRW-ETH', {}).get('pockets', {}))

    # ── log.append ──────────────────────────────────────────────────────────

    def test_log_append(self):
        self.store.apply_event('log.append', {'message': 'hello'})
        self.store.apply_event('log.append', {'message': 'world'})
        snap = self.store.snapshot()
        self.assertIn('hello', snap['logs'])
        self.assertIn('world', snap['logs'])

    # ── subscribe ───────────────────────────────────────────────────────────

    def test_subscribe_called_on_event(self):
        received = []
        self.store.subscribe(lambda t, p: received.append(t))
        self.store.apply_event('log.append', {'message': 'test'})
        self.assertIn('log.append', received)

    def test_subscribe_not_called_for_throttled_ticker(self):
        received = []
        self.store.subscribe(lambda t, p: received.append(t))
        for _ in range(5):
            self.store.apply_event('ticker.update', {'code': 'KRW-BTC', 'trade_price': 50000000})
        # Only 1 notification should have passed the throttle
        self.assertEqual(received.count('ticker.update'), 1)


if __name__ == '__main__':
    unittest.main()
