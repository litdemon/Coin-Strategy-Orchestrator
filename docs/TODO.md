# Project TODOs

## Messaging & Infrastructure
- [ ] **UUID Support in Messaging**:
    - Update `maru` CLI to generate a UUID for each request.
    - Publish to `trading/command/{uuid}` instead of `trading/command/{action}`.
    - Subscribe to `trading/response/{uuid}/#` to receive specific responses.
    - Reason: Current `src/main.py` expects UUID in topic path (`topic.split("/")[2]`).
- [ ] **Messaging Security** (User Request):
    - Implement authentication for MQTT connection (username/password).
    - Manage credentials via environment variables (`.env`).
- [ ] **Configuration Management**:
    - Externalize MQTT broker host/port and other constants from `tools/maru` and `src/main.py` into a config file or `.env`.

## Architecture & Refactoring
- [ ] **Refactor `src/main.py`**:
    - The `Manager` class violates SRP. It handles WebSocket, MQTT, Dashboard, and high-level orchestration.
    - Split into `Agent` (orchestrator), `MqttHandler`, `WebSocketHandler`?
- [ ] **Standardize Error Handling**:
    - `process_command` catches generic `Exception`. Define specific custom exceptions.

## Features
- [ ] **CLI Improvements**:
    - Add `cancel` command (Cancel UUID).
    - Add `limit_buy` / `limit_sell` distinct commands?
- [ ] **Dashboard**:
    - Add more real-time stats (e.g., total valuation in KRW).

## Testing & Verification
- [ ] **Update Verification Scripts**:
    - `verify/verify_changes.py` is broken because `process_command` now expects a specific topic structure with UUID.
- [ ] **Unit Tests**:
    - Add proper unit tests for `Account` module (currently relies on `verify/test_account.py` which is more of an integration script).