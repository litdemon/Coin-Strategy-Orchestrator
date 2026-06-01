import copy
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Dict, List


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _ticker_code(raw: str) -> str:
    from tools.ticker import Ticker
    return Ticker(raw).ticker


_THROTTLE_TYPES = frozenset({'ticker.update', 'orderbook.update'})
_THROTTLE_SEC = 0.5
_MAX_LOGS = 100


class DashboardStateStore:
    """
    Single source of truth for dashboard state.
    Pure dict state — no Widget objects. JSON-serializable via snapshot().
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            'tickers': {},     # code → {code, trade_price, asset, pockets, orders, strategies}
            'pockets': {},     # id → pocket dict (flat index)
            'strategies': {},  # strategy_id → strategy dict (flat index)
            'orders': {},      # uuid → order dict (flat index)
            'logs': [],
        }
        self._subscribers: List[Callable[[str, dict], None]] = []
        self._throttle: Dict[str, float] = {}

    # ── Public API ──────────────────────────────────────────────────────────

    def apply_event(self, event_type: str, payload: dict) -> None:
        with self._lock:
            self._update(event_type, payload)
        self._maybe_notify(event_type, payload)

    def snapshot(self) -> dict:
        with self._lock:
            return _json_safe(copy.deepcopy(self._state))

    def subscribe(self, callback: Callable[[str, dict], None]) -> None:
        self._subscribers.append(callback)

    # ── Internal State Update ────────────────────────────────────────────────

    def _update(self, event_type: str, payload: dict) -> None:
        if event_type == 'ticker.update':
            code = payload.get('code')
            if code:
                t = self._state['tickers'].setdefault(code, {'code': code})
                t['trade_price'] = payload.get('trade_price', t.get('trade_price'))

        elif event_type == 'asset.update':
            currency = payload.get('currency')
            if currency:
                code = _ticker_code(currency)
                t = self._state['tickers'].setdefault(code, {'code': code})
                t['asset'] = payload

        elif event_type == 'orderbook.update':
            code = payload.get('code')
            if code:
                t = self._state['tickers'].setdefault(code, {'code': code})
                t['orderbook'] = payload

        elif event_type == 'pocket.update':
            pid = payload.get('id')
            if not pid:
                return
            self._state['pockets'][pid] = payload
            tc = payload.get('ticker')
            if tc:
                code = _ticker_code(tc)
                t = self._state['tickers'].setdefault(code, {'code': code})
                t.setdefault('pockets', {})[pid] = payload

        elif event_type == 'strategy.update':
            sid = payload.get('strategy_id')
            if not sid:
                return
            self._state['strategies'][sid] = payload
            pocket_id = payload.get('pocket_id')
            ticker_code = payload.get('ticker')
            if pocket_id and pocket_id in self._state['pockets']:
                pocket = self._state['pockets'][pocket_id]
                pocket.setdefault('strategies', {})[sid] = payload
                tc = pocket.get('ticker')
                if tc:
                    code = _ticker_code(tc)
                    tp = self._state['tickers'].get(code, {}).get('pockets', {})
                    if pocket_id in tp:
                        tp[pocket_id].setdefault('strategies', {})[sid] = payload
            elif ticker_code:
                code = _ticker_code(ticker_code)
                t = self._state['tickers'].setdefault(code, {'code': code})
                t.setdefault('strategies', {})[sid] = payload

        elif event_type == 'order.update':
            uuid = payload.get('uuid')
            if not uuid:
                return
            market = payload.get('code') or payload.get('market', '')
            if payload.get('state') in ('done', 'cancel'):
                self._state['orders'].pop(uuid, None)
                if market:
                    code = _ticker_code(market)
                    self._state['tickers'].get(code, {}).get('orders', {}).pop(uuid, None)
            else:
                self._state['orders'][uuid] = payload
                if market:
                    code = _ticker_code(market)
                    t = self._state['tickers'].setdefault(code, {'code': code})
                    t.setdefault('orders', {})[uuid] = payload

        elif event_type == 'entity.remove':
            rid = payload.get('id')
            if not rid:
                return
            if rid in self._state['strategies']:
                strat = self._state['strategies'].pop(rid)
                pocket_id = strat.get('pocket_id')
                ticker_code = strat.get('ticker')
                if pocket_id and pocket_id in self._state['pockets']:
                    self._state['pockets'][pocket_id].get('strategies', {}).pop(rid, None)
                    tc = self._state['pockets'][pocket_id].get('ticker')
                    if tc:
                        code = _ticker_code(tc)
                        tp = self._state['tickers'].get(code, {}).get('pockets', {})
                        if pocket_id in tp:
                            tp[pocket_id].get('strategies', {}).pop(rid, None)
                elif ticker_code:
                    code = _ticker_code(ticker_code)
                    self._state['tickers'].get(code, {}).get('strategies', {}).pop(rid, None)
            elif rid in self._state['pockets']:
                pocket = self._state['pockets'].pop(rid)
                tc = pocket.get('ticker')
                if tc:
                    code = _ticker_code(tc)
                    self._state['tickers'].get(code, {}).get('pockets', {}).pop(rid, None)

        elif event_type == 'log.append':
            self._state['logs'].append(payload.get('message', ''))
            if len(self._state['logs']) > _MAX_LOGS:
                self._state['logs'] = self._state['logs'][-_MAX_LOGS:]

    # ── Throttle & Notify ───────────────────────────────────────────────────

    def _maybe_notify(self, event_type: str, payload: dict) -> None:
        if event_type in _THROTTLE_TYPES:
            key = f"{event_type}:{payload.get('code', '')}"
            now = time.monotonic()
            if now - self._throttle.get(key, -1e9) < _THROTTLE_SEC:
                return
            self._throttle[key] = now

        for cb in self._subscribers:
            try:
                cb(event_type, payload)
            except Exception:
                pass
