# Coin Strategy Orchestrator — Project Guide

This file is the primary context source for Claude Code sessions (`CLAUDE.md` imports it via `@docs/project.md`).

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run
python app.py                        # starts Web UI + MCP server
python app.py --config default.json

# Tests
python -m unittest discover tests          # all 53 tests
python -m unittest tests.test_strategy     # single module

# Verification scripts (ad-hoc scenario tests, not in CI)
python verify/verify_all_feature.py
python verify/verify_buy_strategy.py
```

Startup prints to console:
```
  Dashboard  → http://127.0.0.1:8765
  MCP Server → http://127.0.0.1:8000/mcp
```

Logs rotate daily to `logs/coin-stratege.log` (30-day retention).

## Environment

API keys loaded from `~/.config/upbit.env`:
```
UPBIT_ACCESS_KEY=...
UPBIT_SECRET_KEY=...
```

Runtime config is `default.json`:
```json
{
  "messaging": { "broker_type": "mqtt", "mqtt": { "host": "...", "port": 1883 } },
  "account":   { "initial_balance": 10000000, "fees": { "KRW": 0.0005 } },
  "dashboard": { "host": "127.0.0.1", "port": 8765, "token": "", "mode": "web" },
  "mcp":       { "host": "127.0.0.1", "port": 8000 }
}
```

`account.db` is the SQLite persistence file for strategies, pockets, and orders.

## Architecture

Single-process trading engine with a **task-queue loop** on the main thread, plus background threads (scheduler, WebSocket server, MCP server).

**Data flow:**
```
Upbit WebSocket → task_queue → Manager.on_task()
                                    ├─ on_ticker()  → StrategyManager.on_tick()
                                    ├─ on_orderbook() → AccountManager.check_order()
                                    ├─ on_my_order() → PocketManager (create/close pocket)
                                    └─ on_signal_processing() → AccountManager (buy/sell)
MQTT/MCP → execute_command() → CommandRouterTool
Dashboard events → DashboardStateStore → [TUIConsumer | WsServer] (parallel subscribers)
```

**Key classes:**

| Class | File | Role |
|---|---|---|
| `Manager` | `src/main.py` | Central orchestrator; `WebsocketObserver`, `StrategyObserver`, `PocketObserver` |
| `DashboardStateStore` | `src/dashboard_state.py` | JSON-serializable SSOT for all dashboard state; pub/sub for subscribers |
| `Dashboard` | `src/dashboard.py` | Thin facade over `DashboardStateStore`; accepts `mode` param |
| `TUIConsumer` | `src/tui_consumer.py` | ANSI/curses widget tree (active when `mode="tui"` or `"both"`) |
| `WsServer` | `src/ws_server.py` | FastAPI WebSocket server (`/ws/view`, `/ws/control`, `/api/info`); bridges state → browser |
| `PocketManager` | `src/pocket_manager.py` | Pocket lifecycle (`ACTIVE → CLOSING → CLOSED`); SQLite persistence |
| `StrategyManager` | `strategy/manager.py` | Loads/creates/deletes strategies; routes ticks |
| `AccountDBManager` | `account/manager.py` | Abstraction over real Upbit orders and virtual ledger |
| `DBTradeManager` | `account/dbupbit.py` | SQLite-backed virtual account (order fills, balance) |
| `UpbitWebSocket` | `upbit/upbit_websocket.py` | WebSocket client for Upbit real-time feed |
| `MessagingFactory` | `messaging/factory.py` | Creates MQTT/Redis/socket adapters from config |

## Dashboard — Web UI

Default mode is `"web"`. The browser dashboard is a single-file Alpine.js app (`web/index.html`):
- Connects to `/ws/view` WebSocket for real-time state snapshots and incremental events
- On load, fetches `/api/info` to show the MCP server URL in the Agent Setup Guide panel
- Agent Setup Guide (collapsible) guides users to configure Claude Desktop with the MCP server

`DashboardStateStore` state shape:
```python
{
  'tickers':    { code: { code, trade_price, asset, pockets, orders, strategies } },
  'pockets':    { id: pocket_dict },      # flat index
  'strategies': { strategy_id: dict },   # flat index
  'orders':     { uuid: dict },           # flat index
  'logs':       [ str, ... ],
}
```

Event types (EventType contract — must use exact strings):
`log.append`, `ticker.update`, `asset.update`, `orderbook.update`,
`pocket.update`, `strategy.update`, `order.update`, `entity.remove`

## MCP Server

`project_mcp/mymcp.py` auto-discovers Tools, Resources, Prompts via `discover_components()`.
Starts on `streamable-http` transport in a daemon thread (port from `default.json → mcp.port`).

- **Tools** (`project_mcp/tools/`): subclass `Tool`; command-type tools register with `CommandToolRegistry`
- **Resources** (`project_mcp/resources/`): subclass `Resource`
- **Prompts** (`project_mcp/prompts/`): subclass `Prompt`
- Context injected globally via `initialize_command_context(CommandExecutionContext(...))`
- MQTT and MCP share the same routing: `execute_command()` → `CommandRouterTool`

Available MCP tools: `buy`, `sell`, `strategy`, `account`, `pockets`, `orders`, `status`, `cancel`

## Strategy System

All strategies extend `StrategyBase` (`strategy/base.py`):
- `on_tick(current_price)` → returns `Signal` or `None`
- `get_state()` / `restore_state(state)` — DB persistence across restarts
- `on_schedule()` — optional, called every 60 s
- `ConfigModel = XxxConfig` — class attribute required for `StrategyManager._instantiate_strategy()`

| Name | Class | File |
|---|---|---|
| `default` | `DefaultStrategy` | `strategy/default_strategy.py` |
| `scalping_strategy` | `ScalpingStrategy` | `strategy/buy_strategy.py` |
| `volume_spike_strategy` | `VolumeSpikeStrategy` | `strategy/volume_strategy.py` |
| `anomaly_detection` | `AnomalyStrategy` | `strategy/anomaly_strategy.py` |
| `dl_anomaly_detection` | `DeepAnomalyStrategy` | `strategy/dl_anomaly_strategy.py` |
| `trailing_stop` | `TrailingStopStrategy` | `strategy/trailingstop.py` |

When a buy order fills, `Manager.on_order_completed` auto-creates a `DefaultStrategy` on the new Pocket.

## Pocket Lifecycle

`Pocket` = one open position (ticker + entry price + volume).
States: `ACTIVE → CLOSING → CLOSED`

`SignalType.CLOSE_POCKET` → `PocketManager.close_pocket()` → market sell → order fill (`state=done`) → `closed_pocket()`

## Conventions

- `tests/` — unit/integration tests (`unittest discover`)
- `verify/` — ad-hoc scenario tests (not in CI)
- Use `Decimal` for all financial values; never `float`
- Ticker format: `KRW-BTC`, `KRW-ETH` (use `tools/ticker.py` to normalise `BTC` → `KRW-BTC`)
- Dashboard events must use the explicit EventType strings above (no substring matching)

## GitHub — v1.0 Milestone

Active issues targeting v1.0 user-ready release:

| # | Title |
|---|-------|
| #6 | 문서화: 설치부터 실행까지 사용자 가이드 |
| #7 | Web UI: 전략 생성/삭제/조회 제어 (/ws/control 활성화) |
| #8 | 업비트 실계좌 연동 (live/paper 모드) |
| #9 | Docker 지원 (Dockerfile + docker-compose) |
| #10 | 안정성: 연결 끊김 자동 복구 |
