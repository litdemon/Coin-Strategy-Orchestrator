import logging
import queue
import threading
import time
import traceback
from typing import Any, Dict

from src.dashboard_state import DashboardStateStore

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = frozenset({
    'log.append', 'ticker.update', 'asset.update', 'orderbook.update',
    'pocket.update', 'strategy.update', 'order.update', 'entity.remove',
})


class Dashboard:
    """
    Thin facade: routes update() calls through DashboardStateStore.
    No ANSI rendering. No Widget classes.
    TUI rendering is delegated to TUIConsumer (mode='tui').
    """

    def __init__(self, mode: str = "tui"):
        self.queue = queue.Queue()
        self.running = False
        self._mode = mode
        self._state_store = DashboardStateStore()
        self._thread = None

        if mode in ("tui", "both"):
            from src.tui_consumer import TUIConsumer
            self._tui = TUIConsumer(self._state_store)
        else:
            self._tui = None

    # ── Public API ──────────────────────────────────────────────────────────

    def start(self):
        self.running = True
        if self._tui:
            self._tui.start()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._tui:
            self._tui.stop()
        if self._thread:
            self._thread.join(timeout=1.0)

    def update(self, data: Dict[str, Any]):
        self.queue.put(data)

    def log(self, message: str):
        self.update({'type': 'log.append', 'payload': {'message': message}})
        logger.info(message)

    # ── Internal ────────────────────────────────────────────────────────────

    def _process_item(self, data: Dict[str, Any]):
        mtype = data.get('type')
        payload = data.get('payload')
        if mtype not in VALID_EVENT_TYPES or payload is None:
            logger.warning(f"Unknown or malformed event: {data}")
            return
        self._state_store.apply_event(mtype, payload)

    def _run_loop(self):
        while self.running:
            try:
                while True:
                    try:
                        data = self.queue.get_nowait()
                        self._process_item(data)
                    except queue.Empty:
                        break
                    except Exception as e:
                        logger.error(f"Error processing item: {e}\n{traceback.format_exc()}")
                        break
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                self.running = False
