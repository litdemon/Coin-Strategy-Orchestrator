# Trading System Test Sheet: Buy / Sell / Cancel

**Date:** 2025-12-13  
**Target System:** `Coin Strategy` (Agent + Virtual Account)  
**Verification Tool:** `maru` CLI & `verify_db_account_flow.py`

---

## 1. Buy Order Tests

| ID | Test Case | Steps | Expected Result | Verified? |
| :--- | :--- | :--- | :--- | :--- |
| **B-01** | **Buy Limit Order (CLI)** | 1. Run `maru buy KRW-BTC 50000 1000000`<br>2. Check Dashboard/Logs | - Order created with state `wait`<br />- Price: 50,000 KRW<br>- Volume: Calculated based on 1M KRW<br>- Locked KRW increases. | ✅ |
| **B-02** | **Buy Market Order (CLI)** | 1. Run `maru buy KRW-BTC -1 1000000 -p`<br>*(Assuming market price support)* | - Order created with type `market`.<br>- Executed immediately (if real) or simulated.<br>- Position created. | ⬜ |
| **B-03** | **Buy Execution (Virtual)**| 1. Create Buy Limit Order.<br>2. Simulate Market Price Drop < Limit Price. | - Order state changes `wait` -> `done`.<br>- **Position Created** in `PositionManager`.<br>- KRW Balance decreases, BTC Balance increases. | ✅ |
| **B-04** | **Insufficient Balance** | 1. Try to buy with amount > KRW Balance. | - Order rejected.<br>- Error log in Dashboard. | ⬜ |

## 2. Sell Order Tests

| ID | Test Case | Steps | Expected Result | Verified? |
| :--- | :--- | :--- | :--- | :--- |
| **S-01** | **Sell Limit Order (CLI)** | 1. Run `maru sell KRW-BTC 60000 0.5`<br>2. Check Dashboard | - Order created with state `wait`.<br>- Price: 60,000 KRW<br>- Volume: 0.5 BTC<br>- Locked BTC increases. | ✅ |
| **S-02** | **Sell Execution (Virtual)**| 1. Create Sell Limit Order.<br>2. Simulate Market Price Rise > Limit Price. | - Order state changes `wait` -> `done`.<br>- **Position Closed** (Partial/Full) in `PositionManager`.<br>- BTC Balance decreases, KRW Balance increases. | ✅ |
| **S-03** | **Sell All (Market)** | 1. Run `maru sell KRW-BTC -1 -1` (Logic dependent) | - Sell entire available volume at market price.<br>- Position fully closed. | ⬜ |

## 3. Cancel Order Tests

| ID | Test Case | Steps | Expected Result | Verified? |
| :--- | :--- | :--- | :--- | :--- |
| **C-01** | **Cancel Active Order** | 1. Place Buy/Sell Limit Order (ensure it's `wait`).<br>2. Get UUID from logs (`maru status` pending).<br>3. Run `maru cancel <UUID>`. | - Command sent via MQTT.<br>- Order state changes to `cancel`.<br>- Locked Asset (KRW/BTC) returned to Balance.<br>- Dashboard logs "Order Cancelled". | ✅ |
| **C-02** | **Cancel Invalid UUID** | 1. Run `maru cancel invalid-uuid`. | - System logs "Order Not Found".<br>- No state change. | ⬜ |
| **C-03** | **Cancel Already Executed**| 1. Try to cancel a `done` order. | - Fail / "Not Active Order". | ⬜ |

## 4. CLI Command Reference

| Command | Usage Example | Description |
| :--- | :--- | :--- |
| **Buy** | `maru buy KRW-BTC <price> <krw_amount>` | Places a buy limit order. |
| **Sell** | `maru sell KRW-BTC <price> <volume>` | Places a sell limit order. |
| **Cancel**| `maru cancel <uuid>` | Cancels a specific order by UUID. |
| **Status**| `maru status` | Shows current balance and active positions. |

---

**Note:** Virtual Account Logic (`DBUpbit`) has been patched to ensure `myOrder` events are emitted for all state changes (`wait`, `done`, `cancel`), ensuring the Dashboard and Position logic update correctly.
