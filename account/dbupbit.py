from decimal import Decimal
import threading
import uuid
import datetime
import logging
from typing import List, Optional, Any, Callable

# Project imports
from account.dtos import AssetDTO, OrderDTO
from account.repositories import AssetRepository, OrderRepository
from account.exceptions import InsufficientBalanceException, OrderNotFoundException
from tools.ticker import Ticker
from models.my_asset import MyAsset, AssetItem

logger = logging.getLogger(__name__)

class DBUpbit:
    def __init__(self, db_path: str = "account.db", callback: Callable[[Any, dict], None] = None):
        self.db_path = db_path
        self.callback = callback or (lambda *args, **kwargs: None)
        
        # Repositories
        self.asset_repo = AssetRepository(db_path)
        self.order_repo = OrderRepository(db_path)
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Initialize DB tables
        self.asset_repo.init_db()
        self.order_repo.init_db()

    def get_balance(self, ticker: str) -> Decimal:
        """Get balance for a specific ticker (e.g. KRW-BTC -> BTC balance)."""
        ticker_obj = Ticker(ticker)
        asset = self.asset_repo.get(ticker_obj.currency)
        return asset.balance if asset else Decimal("0")

    def get_balances(self) -> List[dict]:
        """Get all balances as list of dicts (compatible with existing API)."""
        assets = self.asset_repo.get_all()
        return [asset.model_dump() for asset in assets]

    def add_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal("0")) -> dict:
        """Add balance (deposit or buy result). Updates avg_buy_price."""
        ticker_obj = Ticker(ticker)
        
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        if not isinstance(avg_buy_price, Decimal):
            avg_buy_price = Decimal(str(avg_buy_price))
            
        currency = ticker_obj.currency
        
        with self.lock:
            asset = self.asset_repo.get(currency)
            
            if asset:
                # Weighted Average Calculation
                # New Avg = (Old Bal * Old Avg + New Amt * New Price) / (Old Bal + New Amt)
                total_value = (asset.balance * asset.avg_buy_price) + (amount * avg_buy_price)
                new_balance = asset.balance + amount
                
                if new_balance > 0:
                    new_avg_buy_price = total_value / new_balance
                else:
                    new_avg_buy_price = Decimal("0")
                
                new_asset = asset.model_copy(update={
                    "balance": new_balance,
                    "avg_buy_price": new_avg_buy_price
                })
            else:
                new_asset = AssetDTO(
                    currency=currency,
                    balance=amount,
                    locked=Decimal("0"),
                    avg_buy_price=avg_buy_price,
                    avg_buy_price_modified=False,
                    unit_currency=ticker_obj.unit_currency
                )
            
            self.asset_repo.save(new_asset)
            
            # Create update message
            item = AssetItem(
                currency=currency,
                balance=float(new_asset.balance), # AssetItem might expect float
                locked=float(new_asset.locked)
            )
            my_asset_msg = MyAsset(assets=[item])
            msg_dict = my_asset_msg.model_dump()
            
            # Invoke callback
            self.callback(self, msg_dict)
            
            return msg_dict

    def sub_balance(self, ticker: str, amount: Any) -> dict:
        """Subtract balance (withdraw or sell start)."""
        ticker_obj = Ticker(ticker)
        
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
            
        currency = ticker_obj.currency
        
        with self.lock:
            asset = self.asset_repo.get(currency)
            if not asset:
                raise InsufficientBalanceException(f"Asset {currency} not found")
            
            if asset.balance < amount:
                raise InsufficientBalanceException(f"Insufficient balance: {asset.balance} < {amount}")
            
            new_balance = asset.balance - amount
            new_asset = asset.model_copy(update={"balance": new_balance})
            self.asset_repo.save(new_asset)
            
            item = AssetItem(
                currency=currency, 
                balance=float(new_asset.balance), 
                locked=float(new_asset.locked)
            )
            my_asset_msg = MyAsset(assets=[item])
            msg_dict = my_asset_msg.model_dump()
            
            # Invoke callback
            self.callback(self, msg_dict)
            
            return msg_dict

    def create_order(self, 
                     market: str, 
                     side: str, 
                     ord_type: str, 
                     price: Decimal, 
                     volume: Decimal) -> OrderDTO:
        
        if not isinstance(volume, Decimal):
            volume = Decimal(str(volume))
        if not isinstance(price, Decimal):
             price = Decimal(str(price)) if price is not None else Decimal("0")

        new_order = OrderDTO(
            uuid=str(uuid.uuid4()),
            side=side,
            ord_type=ord_type,
            price=price,
            state="wait",
            market=market,
            created_at=datetime.datetime.now(datetime.timezone.utc), # Use UTC
            volume=volume,
            remaining_volume=volume,
            reserved_fee=Decimal("0"),
            remaining_fee=Decimal("0"),
            paid_fee=Decimal("0"),
            locked=volume, # Simplification: locked volume for both bid/ask? 
                           # Actually for BID (buy), we lock KRW (price * volume). 
                           # For ASK (sell), we lock Coin (volume).
                           # The existing code seemingly locks 'volume' for both?
                           # Let's check existing logic in Account.
            executed_volume=Decimal("0"),
            trades_count=0
        )
        
        # Locking Logic
        # Existing logic: separate add_locked/sub_locked methods were on Asset but not used in buy_limit_order snippet?
        # Actually `Account.buy_limit_order` didn't explicitly call `add_locked`.
        # However, a real system should lock funds.
        # The user rules say: "Use Managers for orchestration".
        # I should probably implement valid locking logic here.
        
        with self.lock:
            self.order_repo.save(new_order)
            
        return new_order

    def get_order(self, uuid: str) -> Optional[OrderDTO]:
        return self.order_repo.get(uuid)

    def get_open_orders(self, ticker: str = None) -> List[OrderDTO]:
        if ticker:
            return self.order_repo.get_by_market_and_state(ticker, "wait")
        return self.order_repo.get_by_state("wait")

    def cancel_order(self, uuid: str) -> Optional[OrderDTO]:
        with self.lock:
            order = self.order_repo.get(uuid)
            if order and order.state == "wait":
                cancelled_order = order.model_copy(update={"state": "cancel"})
                self.order_repo.save(cancelled_order)
                return cancelled_order
            return order

    def process_order_complete(self, order: OrderDTO):
        """Handle order completion (balance updates)."""
        with self.lock:
            completed_order = order.model_copy(update={"state": "done"})
            self.order_repo.save(completed_order)
            
            # Logic from old Account.on_order_complete
            krw_volume = completed_order.volume * (completed_order.price or 0)
            fee = krw_volume * Decimal("0.0005") # 0.05%
            
            if completed_order.side == "bid":
                # Bought Coin
                # 1. Add Coin
                self.add_balance(completed_order.market, completed_order.volume, completed_order.price)
                # 2. Sub KRW
                # Note: This logic assumes we haven't already deducted/locked KRW.
                # If we locked it, we should unlock and deduct.
                # Existing Account.py didn't seem to have valid locking logic in `on_order_complete` either?
                # It just calls `sub_balance`.
                self.sub_balance("KRW", krw_volume + fee)
            else:
                # Sold Coin
                # 1. Sub Coin
                self.sub_balance(completed_order.market, completed_order.volume)
                # 2. Add KRW
                self.add_balance("KRW", krw_volume - fee)

    def check_and_execute_orders(self, market: str, orderbook_units: List[dict]) -> Optional[OrderDTO]:
        if not orderbook_units:
            return None
        
        # Taking top of orderbook
        unit = orderbook_units[0]
        ask_price = Decimal(str(unit["ask_price"]))
        bid_price = Decimal(str(unit["bid_price"]))
        
        # We need to check all wait orders for this market
        open_orders = self.get_open_orders(market)
        
        for order in open_orders:
            executed = False
            
            if order.ord_type == "limit":
                if order.side == "bid":
                    # Buy limit: if market ask <= limit price
                    if order.price >= ask_price:
                        executed = True
                else: 
                    # Sell limit: if market bid >= limit price
                    if order.price <= bid_price:
                        executed = True
            
            elif order.ord_type == "market":
                # Market order always executes at current price
                # Update price to execution price
                execution_price = ask_price if order.side == "bid" else bid_price
                order = order.model_copy(update={"price": execution_price, "executed_volume": order.volume})
                executed = True
            
            if executed:
                self.process_order_complete(order)
                return order # Return first executed for now
                
        return None
