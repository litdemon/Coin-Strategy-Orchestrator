import time
from decimal import Decimal
import threading
import uuid
import datetime
import logging
from typing import List, Optional, Any, Callable, Dict

# Project imports
from account.dtos import AssetDTO, OrderDTO
from account.repositories import AssetRepository, OrderRepository
from account.exceptions import InsufficientBalanceException, OrderNotFoundException
from tools.ticker import Ticker
from models.my_asset import MyAsset, AssetItem
from abc import ABC, abstractmethod
from models.orderInfo import OrderInfo
from models.my_order import MyOrder

logger = logging.getLogger(__name__)

class DBUpbit:
    def __init__(self, db_path: str = "account.db", callback: Callable[[Any, dict], None] = None, config: dict = None):
        self.db_path = db_path
        self.callback = callback or (lambda *args, **kwargs: None)
        self.config = config or {}
        
        # Default Fee Rates if not provided
        if "fees" not in self.config:
            self.config["fees"] = {"KRW": 0.0005}
        
        # Repositories
        self.asset_repo = AssetRepository(db_path)
        self.order_repo = OrderRepository(db_path)
        
        # Lock for thread safety - Use RLock for reentrant locking (e.g. process_order_complete calls add_balance)
        self.lock = threading.RLock()

    def init(self):    
        # Initialize DB tables
        self.asset_repo.init_db()
        self.order_repo.init_db()
        
        # Synchronize locked balances
        self.synchronize_locked_balances()

    def _orderDTO_to_order(self, orderDTO: OrderDTO) -> OrderInfo:
        return OrderInfo(
            id=orderDTO.id,
            market=orderDTO.market,
            side=orderDTO.side,
            state=orderDTO.state,
            volume=orderDTO.volume,
            locked=orderDTO.locked,
            avg_price=orderDTO.avg_price,
            created_at=orderDTO.created_at,
            updated_at=orderDTO.updated_at
        )
    
    def _create_my_order_model(self, order: OrderDTO) -> MyOrder:
        """Helper to create MyOrder model from OrderDTO with all required fields."""
        
        # Timestamp conversion (datetime -> ms int)
        ts = int(order.created_at.timestamp() * 1000) if order.created_at else int(time.time() * 1000)
        
        return MyOrder(
            type="myOrder",
            code=order.market,
            uuid=order.uuid,
            ask_bid=order.side, # Assuming lowercase is accepted or strictly "bid"/"ask". MyOrder comment says "BID","ASK" but usually "bid"/"ask" in data.
            order_type=order.ord_type,
            state=order.state,
            price=order.price,
            avg_price=order.avg_price or Decimal("0"),
            volume=order.volume,
            remaining_volume=order.remaining_volume,
            executed_volume=order.executed_volume,
            trades_count=order.trades_count,
            reserved_fee=Decimal("0"), # NotImplemented in OrderDTO yet
            remaining_fee=Decimal("0"),
            paid_fee=Decimal("0"),
            locked=order.locked,
            executed_funds=(order.executed_volume * (order.avg_price or Decimal("0"))),
            prevented_volume=Decimal("0"),
            prevented_locked=Decimal("0"),
            order_timestamp=ts,
            timestamp=ts,
            stream_type="REAL" 
        )

    def synchronize_locked_balances(self):
        """
        Synchronize 'locked' balance in assets table with actual open orders.
        Fixes discrepancies if DB state was inconsistent (e.g. crash).
        """
        with self.lock:
            # 1. Calculate expected locks from Open Orders
            open_orders = self.order_repo.get_by_state("wait")
            calculated_locks = {} # currency -> Decimal
            
            for order in open_orders:
                currency = ""
                if order.side == "bid":
                    # Lock is on Unit Currency (e.g. KRW)
                    ticker = Ticker(order.market)
                    currency = ticker.unit_currency
                else:
                    # Lock is on Currency (e.g. BTC)
                    ticker = Ticker(order.market)
                    currency = ticker.currency
                
                current_lock = calculated_locks.get(currency, Decimal("0"))
                calculated_locks[currency] = current_lock + order.locked

            # 2. Update Assets
            # We iterate ALL assets to ensure we also clear phantom locks (orders=0, but asset.locked>0)
            all_assets = self.asset_repo.get_all()
            for asset in all_assets:
                expected_locked = calculated_locks.get(asset.currency, Decimal("0"))
                
                if asset.locked != expected_locked:
                    diff = expected_locked - asset.locked
                    
                    # Logic: 
                    # Total Funds = Balance + Locked.
                    # We assume Total Funds is correct source of truth.
                    # New Locked = Expected.
                    # New Balance = Total - New Locked 
                    #             = (Balance + Locked) - Expected
                    #             = Balance - (Expected - Locked)
                    #             = Balance - diff
                    #             = Balance - diff
                    
                    new_balance = asset.balance - diff
                    
                    if new_balance < 0:
                        logger.warning(f"Sync Lock Error for {asset.currency}: Balance became negative ({new_balance}). Resetting to 0.")
                        new_balance = Decimal("0")
                        # If balance is 0, we can only lock what we have? 
                        # Or strictly follow order?
                        # If we strictly follow order, we might have negative balance which is bad.
                        # But 'locked' MUST match orders for execution logic.
                        # We'll set balance 0, and allow locked to be expected (assuming data corruption -> user manually fixed balance?)
                        # Or maybe 'locked' in order is wrong?
                        
                    logger.info(f"Syncing {asset.currency}: Locked {asset.locked} -> {expected_locked}. Balance {asset.balance} -> {new_balance}")
                    
                    new_asset = asset.model_copy(update={
                        "locked": expected_locked,
                        "balance": new_balance
                    })
                    self.asset_repo.save(new_asset)

    def get_fee_rate(self, market: str) -> Decimal:
        """Get fee rate for market (e.g. KRW-BTC). Default 0.05% for KRW."""
        ticker = Ticker(market)
        fees = self.config.get("fees", {})
        # Fee is based on Unit Currency (KRW, BTC, etc.)
        return Decimal(str(fees.get(ticker.unit_currency, 0.0005)))

    def get_balance(self, ticker: str) -> Decimal:
        """Get balance for a specific ticker (e.g. KRW-BTC -> BTC balance)."""
        ticker_obj = Ticker(ticker)
        asset = self.asset_repo.get(ticker_obj.currency)
        return asset.balance if asset else Decimal("0")

    def get_balances(self) -> List[dict]:
        """Get all balances as list of dicts (compatible with existing API)."""
        assets = self.asset_repo.get_all()
        # Filter out assets with 0 total volume (balance + locked)
        return [
            asset.model_dump() 
            for asset in assets 
            if (asset.balance + asset.locked) > 0
        ]

    def add_balance(self, ticker: str, amount: Any, avg_buy_price: Decimal = Decimal("0")) -> dict:
        """Add balance (deposit or buy result). Updates avg_buy_price."""
        ticker_obj = Ticker(ticker)
        
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        if not isinstance(avg_buy_price, Decimal):
            avg_buy_price = Decimal(str(avg_buy_price))
            
        currency = ticker_obj.currency
        
        # FiX: Ensure KRW always has avg_buy_price of 1
        if currency == "KRW":
            avg_buy_price = Decimal("1")
        
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
                balance=new_asset.balance, 
                locked=new_asset.locked
            )
            my_asset_msg = MyAsset(assets=[item])
            msg_dict = my_asset_msg.model_dump()
            
            # Invoke callback
            self.callback(self, msg_dict)
            
            return msg_dict

    def sub_balance(self, ticker: str, amount: Decimal) -> dict:
        """Subtract balance (withdraw or sell start)."""
        ticker_obj = Ticker(ticker)
        
        currency = ticker_obj.currency
        
        with self.lock:
            asset = self.asset_repo.get(currency)
            if not asset:
                raise InsufficientBalanceException(f"Asset {currency} not found")
            
            if asset.balance < amount:
                raise InsufficientBalanceException(f"Insufficient balance: {asset.balance} < {amount}")
            
            new_balance = asset.balance - amount
            new_asset = asset.model_copy(update={"balance": new_balance})
            if new_balance == 0 and asset.locked == 0:
                new_asset = asset.model_copy(update={"balance": 0, "avg_buy_price": Decimal("0")})

            self.asset_repo.save(new_asset)
            
            item = AssetItem(
                currency=currency, 
                balance=new_asset.balance, 
                locked=new_asset.locked
            )
            my_asset_msg = MyAsset(assets=[item])
            msg_dict = my_asset_msg.model_dump()
            
            # Invoke callback
            self.callback(self, msg_dict)
            
            return msg_dict

    def lock_asset(self, ticker_currency: str, amount: Decimal):
        """Lock asset amount. Raises InsufficientBalanceException if not enough."""
        with self.lock:
            asset = self.asset_repo.get(ticker_currency)
            if not asset or asset.balance < amount:
                raise InsufficientBalanceException(f"Insufficient funds for {ticker_currency}: {asset.balance if asset else 0} < {amount}")
            
            new_balance = asset.balance - amount
            new_locked = asset.locked + amount
            new_asset = asset.model_copy(update={"balance": new_balance, "locked": new_locked})
            self.asset_repo.save(new_asset)
            
            # Emit update
            item = AssetItem(
                currency=ticker_currency,
                balance=new_asset.balance,
                locked=new_asset.locked
            )
            self.callback(self, MyAsset(assets=[item]).model_dump())

    def unlock_asset(self, ticker_currency: str, amount: Decimal):
        """Unlock asset amount (e.g. on cancel)."""
        with self.lock:
            asset = self.asset_repo.get(ticker_currency)
            if not asset:
                return # Should not happen
                
            new_balance = asset.balance + amount
            new_locked = asset.locked - amount
            if new_locked < 0: new_locked = Decimal("0")
            
            new_asset = asset.model_copy(update={"balance": new_balance, "locked": new_locked})
            self.asset_repo.save(new_asset)
            
            item = AssetItem(
                currency=ticker_currency,
                balance=new_asset.balance,
                locked=new_asset.locked
            )
            self.callback(self, MyAsset(assets=[item]).model_dump())

    def create_order(self, 
                     market: str, 
                     side: str, 
                     ord_type: str, 
                     price: Decimal, 
                     volume: Decimal) -> Dict[str, Any]:
        
        def get_market_price(market: str) -> Decimal:
            orderbook = pyupbit.get_orderbook(market)
            return Decimal(orderbook[0]['orderbook_units'][0]['ask_price'])

        if not isinstance(volume, Decimal):
            volume = Decimal(str(volume))
        if not isinstance(price, Decimal):
            price = Decimal(str(price)) if price is not None else Decimal("0")

        # Validation & Locking
        ticker_obj = Ticker(market)
        lock_currency = ""
        lock_amount = Decimal("0")
        
        if side == "bid":
            # Buy -> Lock KRW (unit_currency)
            # Limit: Price * Volume
            # Market: Price (if ord_type is price) or Estimate?
            # Assuming Limit for now based on test cases.
            lock_currency = ticker_obj.unit_currency
            fee_rate = self.get_fee_rate(market)

            if ord_type == "limit":
                lock_amount = price * volume
                # Add fee buffer
                lock_amount += lock_amount * fee_rate
            elif ord_type == "market":
                # Market Buy: 
                price = get_market_price(market)
                if price > 0:
                    lock_amount = price * volume
                    lock_amount += lock_amount * fee_rate
                else:
                    # Fallback if no price provided (shouldn't happen with updated AccountDBManager)
                    logger.warning(f"Market Buy Order for {market} has 0 price. Locking skipped.") 
        else:
            # Sell -> Lock Coin (currency)
            lock_currency = ticker_obj.currency
            lock_amount = volume
            
        # Attempt Lock
        if lock_amount > 0:
            self.lock_asset(lock_currency, lock_amount)

        new_order = OrderDTO(
            uuid=str(uuid.uuid4()),
            side=side,
            ord_type=ord_type,
            price=price,
            state="wait",
            market=market,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            volume=volume,
            remaining_volume=volume,
            reserved_fee=Decimal("0"), # TODO: Track fee separately if needed
            remaining_fee=Decimal("0"),
            paid_fee=Decimal("0"),
            locked=lock_amount, 
            executed_volume=Decimal("0"),
            trades_count=0
        )
        
        with self.lock:
            self.order_repo.save(new_order)
            
            # Emit myOrder event
            myOrder = self._create_my_order_model(new_order)
            self.callback(self, myOrder.model_dump())
            
        return myOrder.model_dump()

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
                
                # Unlock Funds
                ticker_obj = Ticker(order.market)
                if order.side == "bid":
                    # Unlock KRW (use saved locked amount)
                    self.unlock_asset(ticker_obj.unit_currency, order.locked)
                else:
                    # Unlock Coin
                    self.unlock_asset(ticker_obj.currency, order.locked)
                
                # Emit myOrder event
                myOrder = self._create_my_order_model(cancelled_order)
                self.callback(self, myOrder.model_dump())
                
                return cancelled_order
            return order

    def process_order_complete(self, order: OrderDTO):
        """Handle order completion (balance updates)."""
        with self.lock:
            completed_order = order.model_copy(update={"state": "done"})
            self.order_repo.save(completed_order)
            
            # Emit myOrder event
            myOrder = self._create_my_order_model(completed_order)
            self.callback(self, myOrder.model_dump())
            
            # Logic with Locking
            krw_volume = completed_order.volume * (completed_order.price or 0)
            fee_rate = self.get_fee_rate(completed_order.market)
            fee = krw_volume * fee_rate
            
            if completed_order.side == "bid":
                # Bought Coin
                # 1. Add Coin (No lock involved)
                self.add_balance(completed_order.market, completed_order.volume, completed_order.price)
                
                # 2. Sub KRW
                # KRW was Locked. We need to Consume Locked KRW.
                # Total Cost = krw_volume + fee
                # Locked was = (price * volume) * 1.0005 (approx)
                
                # We need to reduce LOCKED by order.locked (release lock)
                # And reduce BALANCE by Cost (spend)
                # But wait, 'locked' definition:
                #    balance = available
                #    total = balance + locked?
                # In my lock_asset implementation:
                #    new_balance = asset.balance - amount (Available reduced)
                #    new_locked = asset.locked + amount (Locked increased)
                
                # So to Spend:
                #    locked -= order.locked
                #    balance -> No change (already deducted from available)
                #    Wait, if executed cost < locked? Refund difference to balance.
                
                currency = "KRW"
                with self.lock:
                    asset = self.asset_repo.get(currency)
                    if asset:
                        # Spend locked
                        new_locked = asset.locked - completed_order.locked
                        if new_locked < 0: new_locked = Decimal("0")
                        
                        # Refund excess (if any)
                        # Actual Cost
                        actual_cost = krw_volume + fee
                        excess = completed_order.locked - actual_cost
                        
                        # Since cost is paid, we don't add back to balance unless excess
                        # Asset Balance (Available) doesn't change since it was already deducted?
                        # Yes.
                        # So new_balance = asset.balance + excess
                        
                        new_balance = asset.balance + excess
                        if new_balance <= 0: 
                            new_balance = Decimal("0")
                            new_locked = Decimal("0")
                            avg_buy_price = Decimal("0")
                        else:
                            avg_buy_price = asset.avg_buy_price
                            
                        new_asset = asset.model_copy(update={"balance": new_balance, "locked": new_locked, "avg_buy_price": avg_buy_price})
                        self.asset_repo.save(new_asset)
                        
                        # Emit
                        item = AssetItem(currency=currency, balance=new_asset.balance, locked=new_asset.locked, avg_buy_price=new_asset.avg_buy_price)
                        self.callback(self, MyAsset(assets=[item]).model_dump())

            else:
                # Sold Coin
                # 1. Sub Coin (Consumed Locked)
                currency = Ticker(completed_order.market).currency
                with self.lock:
                    asset = self.asset_repo.get(currency)
                    if asset:
                        new_locked = asset.locked - completed_order.locked
                        if new_locked < 0: new_locked = Decimal("0")
                        
                        # If executed volume < locked? (Partial fill?)
                        # Assuming full fill for loop.
                        # If full fill, excess is 0.
                        
                        avg_buy_price = asset.avg_buy_price
                        if asset.balance == 0 and new_locked == 0:
                            avg_buy_price = Decimal("0")
                        
                        new_asset = asset.model_copy(update={"locked": new_locked, "avg_buy_price": avg_buy_price})
                        self.asset_repo.save(new_asset)
                        
                        item = AssetItem(currency=currency, balance=new_asset.balance, locked=new_asset.locked)
                        self.callback(self, MyAsset(assets=[item]).model_dump())
                        
                # 2. Add KRW
                self.add_balance("KRW", krw_volume - fee)
            
            return completed_order

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
                        # Executed at ask_price (better price)
                        order = order.model_copy(update={"price": ask_price, "avg_price": ask_price})
                        executed = True
                else: 
                    # Sell limit: if market bid >= limit price
                    if order.price <= bid_price:
                        # Executed at bid_price (better price)
                        order = order.model_copy(update={"price": bid_price, "avg_price": bid_price})
                        executed = True
            
            elif order.ord_type == "market":
                # Market order always executes at current price
                # Update price to execution price
                execution_price = ask_price if order.side == "bid" else bid_price
                order = order.model_copy(update={"price": execution_price, "executed_volume": order.volume, "avg_price": execution_price})
                executed = True
            
            if executed:
                completed_order = self.process_order_complete(order)
                return completed_order # Return first executed for now
                
        return None
