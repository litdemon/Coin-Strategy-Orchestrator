import asyncio
import json
import logging
import os
import threading
from typing import Optional, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Shared async loop (set when server thread starts)
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_ready = threading.Event()
_clients_view: Set[WebSocket] = set()


def _check_token(provided: Optional[str], required: Optional[str]) -> bool:
    if not required:
        return True  # no token configured → open
    return provided == required


def create_app(state_store, token: Optional[str], web_dir: str) -> FastAPI:
    app = FastAPI(title="Coin Strategy Dashboard")

    @app.websocket("/ws/view")
    async def ws_view(ws: WebSocket, token: Optional[str] = Query(None)):
        if not _check_token(token, globals().get('_required_token')):
            await ws.close(code=4003)
            return
        await ws.accept()
        _clients_view.add(ws)
        try:
            await ws.send_json({'type': 'snapshot', 'payload': state_store.snapshot()})
            async for _ in ws.iter_text():
                pass  # read-only: discard incoming messages
        except WebSocketDisconnect:
            pass
        finally:
            _clients_view.discard(ws)

    @app.websocket("/ws/control")
    async def ws_control(ws: WebSocket, token: Optional[str] = Query(None)):
        if not _check_token(token, globals().get('_required_token')):
            await ws.close(code=4003)
            return
        await ws.accept()
        try:
            await ws.send_json({'type': 'snapshot', 'payload': state_store.snapshot()})
            async for _ in ws.iter_text():
                pass  # Phase 3: command dispatch placeholder
        except WebSocketDisconnect:
            pass

    @app.get("/api/info")
    async def api_info():
        return {
            "mcp_url": f"http://{_mcp_host}:{_mcp_port}/mcp",
            "tools": ["status", "account", "buy", "sell", "cancel", "pockets", "orders", "strategy"],
        }

    if os.path.isdir(web_dir):
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="static")

    return app


async def _broadcast(event_type: str, payload: dict) -> None:
    if not _clients_view:
        return
    msg = json.dumps({'type': event_type, 'payload': payload})
    dead: Set[WebSocket] = set()
    for ws in list(_clients_view):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _clients_view.difference_update(dead)


def on_state_event(event_type: str, payload: dict) -> None:
    """Bridge from Dashboard sync thread → asyncio WebSocket loop."""
    if _loop_ready.is_set() and _loop and not _loop.is_closed():
        asyncio.run_coroutine_threadsafe(_broadcast(event_type, payload), _loop)


# Module-level token and MCP info (set before clients connect)
_required_token: Optional[str] = None
_mcp_host: str = "127.0.0.1"
_mcp_port: int = 8000


def start_ws_server(
    state_store,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: Optional[str] = None,
    web_dir: str = "web",
    mcp_host: str = "127.0.0.1",
    mcp_port: int = 8000,
) -> None:
    global _loop, _required_token, _mcp_host, _mcp_port
    _required_token = token
    _mcp_host = mcp_host
    _mcp_port = mcp_port

    app = create_app(state_store, token, web_dir)
    state_store.subscribe(on_state_event)

    def _run() -> None:
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop_ready.set()

        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            loop="none",
            log_level="warning",
        )
        server = uvicorn.Server(config)
        _loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True, name="ws-server")
    t.start()
    logger.info(f"WebSocket server starting on http://{host}:{port}")
