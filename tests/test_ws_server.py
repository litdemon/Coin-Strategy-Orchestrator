import asyncio
import json
import time
import unittest

from src.dashboard_state import DashboardStateStore

PORT = 18765


def _new_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


class TestWsServer(unittest.TestCase):
    """Smoke tests for WebSocket server: connect, snapshot, broadcast."""

    store: DashboardStateStore

    @classmethod
    def setUpClass(cls):
        import src.ws_server as ws_mod
        ws_mod._clients_view = set()
        ws_mod._loop = None
        ws_mod._loop_ready.clear()
        ws_mod._required_token = None

        cls.store = DashboardStateStore()
        from src.ws_server import start_ws_server
        start_ws_server(cls.store, host="127.0.0.1", port=PORT, token=None, web_dir="web")
        ws_mod._loop_ready.wait(timeout=5)
        time.sleep(0.5)  # let uvicorn finish binding

    def _run(self, coro):
        loop = _new_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_1_snapshot_on_connect(self):
        """Client receives snapshot immediately on connect."""
        import websockets.asyncio.client as wsclient

        self.store.apply_event('log.append', {'message': 'hello-ws'})

        async def _check():
            async with wsclient.connect(f"ws://127.0.0.1:{PORT}/ws/view") as ws:
                raw = await asyncio.wait_for(ws.recv(), timeout=3)
                msg = json.loads(raw)
                self.assertEqual(msg['type'], 'snapshot')
                self.assertIn('hello-ws', msg['payload']['logs'])

        self._run(_check())

    def test_2_event_broadcast(self):
        """Direct broadcast reaches connected WebSocket client."""
        import src.ws_server as ws_mod
        import websockets.asyncio.client as wsclient

        async def _check():
            async with wsclient.connect(f"ws://127.0.0.1:{PORT}/ws/view") as ws:
                await ws.recv()  # consume snapshot

                # Schedule _broadcast directly on the server loop and wait for it
                fut = asyncio.run_coroutine_threadsafe(
                    ws_mod._broadcast('test.ping', {'ok': True}),
                    ws_mod._loop,
                )
                fut.result(timeout=2)  # block until server has sent

                raw = await asyncio.wait_for(ws.recv(), timeout=3)
                msg = json.loads(raw)
                self.assertEqual(msg['type'], 'test.ping')
                self.assertEqual(msg['payload']['ok'], True)

        self._run(_check())

    def test_3_token_blocks_unauthenticated(self):
        """Unauthenticated client is rejected when token is required."""
        import src.ws_server as ws_mod
        import websockets.asyncio.client as wsclient
        ws_mod._required_token = "secret"

        rejected = False

        async def _check():
            nonlocal rejected
            try:
                async with wsclient.connect(f"ws://127.0.0.1:{PORT}/ws/view") as ws:
                    await ws.recv()
            except Exception:
                rejected = True

        self._run(_check())
        ws_mod._required_token = None
        self.assertTrue(rejected, "Expected connection to be rejected without token")


if __name__ == '__main__':
    unittest.main()
