from __future__ import annotations

import time
import traceback
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pyupbit

from project_mcp.base import Tool
from project_mcp.tools.context import get_execution_context
from tools.converter import Decimal2float
from tools.ticker import Ticker
from strategy.models import StrategyType


def _to_decimal(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(value if value is not None else default))


def _log_and_fetch_price(ticker: Ticker, op: str) -> Optional[Decimal]:
    context = get_execution_context()
    try:
        price_value = pyupbit.get_current_price(ticker.ticker)
    except Exception as exc:
        context.dashboard.log(f"{op}: Error checking price for {ticker.ticker}: {exc}")
        return None
    if price_value is None:
        context.dashboard.log(f"{op}: Price not found for {ticker.ticker}")
        return None
    return Decimal(str(price_value))


class CommandActionTool(Tool):
    action: str = ""

    def identifier(self) -> str:
        if not self.action:
            raise ValueError("CommandActionTool requires an action name")
        return self.action


class StatusCommandTool(CommandActionTool):
    action = "status"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        status = {
            "running": True,
            "pockets": len(context.pocket_manager.pockets),
            "timestamp": time.time(),
        }
        context.messaging.publish(f"trading/response/{uuid}/status", status)
        return status


class AccountCommandTool(CommandActionTool):
    action = "account"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        balances = context.account_manager.get_balances()
        serializable = Decimal2float(balances)
        context.messaging.publish(f"trading/response/{uuid}/account", serializable)
        context.dashboard.log(f"Account: {serializable}")
        return {"balances": serializable}


class BuyCommandTool(CommandActionTool):
    action = "buy"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        ticker_value = data.get("ticker")
        if not ticker_value:
            context.dashboard.log("Buy command requires ticker")
            return {}

        ticker = Ticker(ticker_value)
        volume = _to_decimal(data.get("volume"))
        price = _to_decimal(data.get("price"))
        won = _to_decimal(data.get("won"))

        if context.upbit_websocket and ticker.ticker not in context.upbit_websocket.codes:
            context.dashboard.log(f"Subscribing to new ticker: {ticker.ticker}")
            context.upbit_websocket.add_subscription([ticker.ticker])

        is_market = price <= 0
        price = None if is_market else price

        if price is None and not is_market:
            fetched_price = _log_and_fetch_price(ticker, "Buy")
            if fetched_price is None:
                return {}
            price = fetched_price
            context.dashboard.log(f"Buy Price not specified. Using Current Price: {price}")

        if won > 0 and volume <= 0:
            calc_price = price if price and price > 0 else _log_and_fetch_price(ticker, "Buy")
            if not calc_price:
                return {}
            fee = Decimal("0.0005")
            volume = (won - won * fee) / calc_price

        if volume <= 0:
            context.dashboard.log(f"Invalid Buy Volume: {volume}. Must be positive.")
            return {}
        if not is_market and (price is None or price <= 0):
            context.dashboard.log(
                f"Invalid Buy Price: {price}. Must be positive for Limit Order."
            )
            return {}

        context.dashboard.log(
            f"CMD BUY: {ticker.currency} {ticker.volume(volume)} @ {'Market' if is_market else price}"
        )

        if is_market:
            order = context.account_manager.buy_market_order(ticker.ticker, volume)
        else:
            order = context.account_manager.buy_limit_order(
                ticker.ticker, price, volume
            )
        return order or {}


class SellCommandTool(CommandActionTool):
    action = "sell"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        ticker_value = data.get("ticker")
        if not ticker_value:
            context.dashboard.log("Sell command requires ticker")
            return {}

        ticker = Ticker(ticker_value)
        volume = _to_decimal(data.get("volume"))
        price = _to_decimal(data.get("price"))
        won = _to_decimal(data.get("won"))

        is_market = price <= 0
        price = None if is_market else price

        current_price = _log_and_fetch_price(ticker, "Sell")
        if current_price is None:
            return {}

        if price is None and not is_market:
            price = current_price

        if won > 0 and volume <= 0:
            fee = Decimal("0.005")
            price = current_price
            volume = (won - won * fee) / price

        is_sell_all = float(volume) == -1
        if is_sell_all:
            balance = context.account_manager.get_balance(ticker.ticker)
            context.dashboard.log(f"Sell All requested. Avail Balance: {balance}")
            volume = balance

        if volume <= 0 and not is_sell_all:
            context.dashboard.log(
                f"Invalid Sell Volume: {volume}. Must be positive."
            )
            return {}
        if price is not None and price <= 0 and not is_market:
            context.dashboard.log(
                f"Invalid Sell Price: {price}. Must be positive for Limit Order."
            )
            return {}

        context.dashboard.log(
            f"CMD SELL: {ticker} {volume} @ {'Market' if is_market else price}"
        )

        if is_market:
            context.account_manager.sell_market_order(ticker.ticker, volume)
        else:
            context.account_manager.sell_limit_order(ticker.ticker, price, volume)

        if is_sell_all and context.virtual:
            pockets = context.pocket_manager.get_pockets(ticker.ticker)
            for pocket in pockets:
                context.pocket_manager.archive_pocket(pocket.id)
            to_archive = [
                sid
                for sid, strategy in context.strategy_manager.strategies.items()
                if getattr(strategy.context, "ticker", None) == ticker.ticker
            ]
            for sid in to_archive:
                context.strategy_manager.archive_strategy(sid)
                context.dashboard.log(f"Archived Strategy: {sid}")

            context.dashboard.log(f"Cleanup complete for {ticker}")

        return {"result": "sell_requested"}


class CancelCommandTool(CommandActionTool):
    action = "cancel"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        uuid_arg = data.get("uuid")
        ticker_str = data.get("ticker")

        if ticker_str:
            ticker = Ticker(ticker_str)
            context.dashboard.log(f"CMD CANCEL ALL: {ticker.ticker}")
            orders = context.account_manager.get_order(ticker.ticker)
            if not orders:
                context.dashboard.log(f"No open orders found for {ticker.ticker}")
            for order in orders or []:
                oid = order.get("uuid") if isinstance(order, dict) else getattr(order, "uuid", None)
                if oid:
                    context.account_manager.cancel_order(oid)
                    context.dashboard.log(f"Cancelled {oid}")
            return {"result": "cancelled_by_ticker"}

        if uuid_arg:
            target_uuid = self._resolve_partial_uuid(uuid_arg)
            if not target_uuid:
                context.dashboard.log(
                    f"No order found matching partial UUID '{uuid_arg}'"
                )
                return {}
            context.dashboard.log(f"CMD CANCEL: {target_uuid}")
            result = context.account_manager.cancel_order(target_uuid)
            formatted = self._format_result(result)
            if result:
                context.dashboard.log(
                    f"Order Cancelled: {formatted.get('market')} {formatted.get('side')} "
                    f"{formatted.get('state')} {formatted.get('locked')}"
                )
            else:
                context.dashboard.log(
                    f"Order Cancel Failed or Not Found: {target_uuid}"
                )
            return formatted

        raise ValueError("uuid or ticker is required for cancel action")

    @staticmethod
    def _format_result(result: Any) -> Dict[str, Any]:
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        return {}

    @staticmethod
    def _resolve_partial_uuid(partial: str) -> Optional[str]:
        context = get_execution_context()
        if len(partial) >= 36:
            return partial
        matches: List[str] = []
        for order in context.account_manager.get_orders():
            oid = order.get("uuid") if isinstance(order, dict) else getattr(order, "uuid", None)
            if oid and oid.startswith(partial):
                matches.append(oid)
        if len(matches) == 1:
            context.dashboard.log(
                f"Partial UUID '{partial}' resolved to {matches[0]}"
            )
            return matches[0]
        if len(matches) > 1:
            context.dashboard.log(
                f"Ambiguous partial UUID '{partial}'. Matches: {matches}"
            )
            return None
        return None


class PocketsCommandTool(CommandActionTool):
    action = "pockets"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        reply_to = data.get("reply_to")
        context.dashboard.log("CMD POCKETS Request")

        lines = [f"{'UUID':<8} | {'Ticker':<10} | {'ROI':<8} | {'Vol':<12}", "-" * 50]
        count = 0
        for pos in context.pocket_manager.pockets.values():
            ticker = Ticker(pos.ticker)
            current_price = context.current_prices.get(ticker.ticker)
            if not current_price or pos.entry_price <= 0:
                continue
            profit_rate = (current_price / pos.entry_price) - 1
            lines.append(
                f"{pos.id[:6]:<8} | {ticker.ticker:<10} | {profit_rate * 100:.2f}% | {pos.volume}"
            )
            count += 1

        if count == 0:
            lines.append("No active pockets.")

        response_text = "\n".join(lines)
        if reply_to:
            context.messaging.publish(reply_to, {"text": response_text})
        else:
            context.dashboard.log(response_text)

        return {"count": count, "text": response_text}


class OrdersCommandTool(CommandActionTool):
    action = "orders"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        reply_to = data.get("reply_to")
        context.dashboard.log("CMD ORDERS Request")

        orders = context.account_manager.get_orders()

        lines = [f"{'UUID':<8} | {'Ticker':<10} | {'Side':<4} | {'Price':<12} | {'Vol'}", "-" * 65]
        count = 0
        for o in orders or []:
            oid = o.get('uuid') if isinstance(o, dict) else getattr(o, 'uuid', "")
            mkt = o.get('market') if isinstance(o, dict) else getattr(o, 'market', "")
            side = o.get('side') if isinstance(o, dict) else getattr(o, 'side', "")
            price = o.get('price') if isinstance(o, dict) else getattr(o, 'price', 0)
            vol = o.get('remaining_volume') if isinstance(o, dict) else getattr(o, 'remaining_volume', 0)

            uuid_short = (oid or "")[:6]
            lines.append(f"{uuid_short:<8} | {mkt:<10} | {side:<4} | {price:<12} | {vol}")
            count += 1

        if count == 0:
            lines.append("No open orders.")

        response_text = "\n".join(lines)
        if reply_to:
            context.messaging.publish(reply_to, {"text": response_text})
        else:
            context.dashboard.log(response_text)

        return {"count": count, "text": response_text}


class StrategyCommandTool(CommandActionTool):
    action = "strategy"

    def execute(self, uuid: str, data: Dict[str, Any]) -> Dict[str, Any]:
        context = get_execution_context()
        sub_action = data.get("sub_action")
        strategy_type_str = data.get("type")

        if sub_action == "create":
            if strategy_type_str == "buy":
                ticker_str = data.get("ticker")
                budget = _to_decimal(data.get("budget", "0"))
                name = data.get("name", "scalping_strategy")

                if not ticker_str or budget <= 0:
                    context.dashboard.log("Invalid Strategy Creation Params")
                    return {}

                ticker = Ticker(ticker_str)
                if context.upbit_websocket and ticker.ticker not in context.upbit_websocket.codes:
                    context.upbit_websocket.add_subscription([ticker.ticker])

                current_price = context.current_prices.get(ticker.ticker)
                if not current_price:
                    try:
                        current_price = pyupbit.get_current_price(ticker.ticker)
                    except Exception:
                        current_price = None

                calc_volume = Decimal("0")
                if current_price:
                    cp = Decimal(str(current_price))
                    fee_rate = Decimal("0.0005")
                    if cp > 0:
                        calc_volume = budget / (cp * (1 + fee_rate))
                        context.dashboard.log(f"Calc Volume: {calc_volume:.8f} (Budget: {budget}, Price: {cp})")
                else:
                    context.dashboard.log(f"Warning: Could not fetch price for {ticker.ticker}. Using Budget as raw volume (dangerous if not intended).")
                    calc_volume = budget

                config = {
                    "name": name,
                    "type": StrategyType.BUY.value,
                    "buy_amount": calc_volume,
                }

                if name == "volume_spike_strategy":
                    config["execution_interval"] = 60
                    config["period"] = 20
                    config["multiplier"] = 2.0

                try:
                    sid = context.strategy_manager.create_strategy(
                        name=name,
                        type=StrategyType.BUY,
                        ticker=ticker.ticker,
                        budget=budget,
                        config=config,
                    )
                    msg = f"CMD STRATEGY: Created {name} ({sid}) for {ticker.ticker}"
                    context.dashboard.log(msg)
                    reply_to = data.get("reply_to")
                    if reply_to:
                        context.messaging.publish(reply_to, {"text": f"Strategy Created: {sid}"})
                    return {"strategy_id": sid}
                except Exception as exc:
                    context.dashboard.log(f"Failed to create strategy: {exc}")
                    return {"error": str(exc)}
            else:
                context.dashboard.log(f"Unknown strategy type: {strategy_type_str}")
                return {}

        elif sub_action == "list":
            strategies = context.strategy_manager.strategies
            if not strategies:
                response_text = "No active strategies."
            else:
                lines = [f"{'ID':<8} | {'Name':<20} | {'Ticker':<10} | {'Type':<6}", "-" * 60]
                for sid, strategy in strategies.items():
                    s_name = getattr(strategy.config, 'name', str(strategy.config))[:20]
                    s_ticker = getattr(strategy.context, 'ticker', '')
                    s_type = getattr(strategy.config, 'type', '')
                    lines.append(f"{sid[:8]:<8} | {s_name:<20} | {s_ticker:<10} | {s_type:<6}")
                response_text = "\n".join(lines)

            reply_to = data.get("reply_to")
            if reply_to:
                context.messaging.publish(reply_to, {"text": response_text})
            else:
                context.dashboard.log(response_text)
            return {"text": response_text}

        elif sub_action == "delete":
            strategy_id = data.get("strategy_id")
            if not strategy_id:
                context.dashboard.log("Delete command requires strategy_id")
                return {}

            target_id = strategy_id
            if len(strategy_id) < 36:
                found = False
                for sid in context.strategy_manager.strategies.keys():
                    if sid.startswith(strategy_id):
                        target_id = sid
                        found = True
                        break
                if not found:
                    context.dashboard.log(f"Strategy ID not found: {strategy_id}")
                    return {}

            try:
                context.strategy_manager.stop_strategy(target_id)
                context.strategy_manager.archive_strategy(target_id)
                msg = f"Strategy Deleted: {target_id}"
                context.dashboard.log(msg)
                reply_to = data.get("reply_to")
                if reply_to:
                    context.messaging.publish(reply_to, {"text": msg})
                return {"deleted": target_id}
            except Exception as exc:
                context.dashboard.log(f"Failed to delete strategy: {exc}")
                return {"error": str(exc)}

        else:
            context.dashboard.log(f"Unknown strategy sub-action: {sub_action}")
            return {}
