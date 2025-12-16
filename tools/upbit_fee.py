from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict
from enum import Enum

class FeeType(Enum):
    FIXED = "fixed"
    PERCENTAGE = "percentage"

class FeePolicy(ABC):
    @abstractmethod
    def get_fee(self, currency: str, price: Decimal, volume: Decimal) -> Decimal:
        """
        Calculates the fee for a transaction.
        
        :param currency: The currency code (e.g., 'BTC', 'ETH', 'KRW-BTC' -> 'BTC')
        :param price: The price per unit
        :param volume: The volume of the transaction
        :return: The calculated fee amount
        """
        pass

class UpbitFeePolicy(FeePolicy):
    def __init__(self):
        # Default policy: 0.05%
        self.default_rate = Decimal("0.0005")
        
        # Specific fixed fees (amount independent)
        # "BTC일 경우 amount 에 상관 없이 0.000008 BTC"
        self.fixed_fees: Dict[str, Decimal] = {
            "BTC": Decimal("0.000008")
        }
        
        # Specific percentage fees (future extensible)
        self.percentage_fees: Dict[str, Decimal] = {}

    def get_fee(self, ticker: str, price: Decimal, volume: Decimal) -> Decimal:
        """
        Calculate fee based on ticker rules.
        Includes parsing ticker to find currency (e.g. KRW-BTC -> BTC).
        """
        # Parse currency from ticker (Assuming KRW-XXX or just XXX)
        currency = ticker.split("-")[1] if "-" in ticker else ticker
        
        # Rule 1: Fixed Fee Check
        if currency in self.fixed_fees:
            return self.fixed_fees[currency]

        # Rule 2: Specific Percentage Fee Check
        rate = self.percentage_fees.get(currency, self.default_rate)
        
        # Rule 3: Default Percentage Calculation
        # "buy : amount * 0.05%, sell amount * 0.05%"
        # Using Trade Value (Price * Volume) as "amount" base for percentage.
        trade_value = price * volume
        return trade_value * rate

    def add_fixed_rule(self, currency: str, fee: Decimal):
        """Add a specific fixed fee rule."""
        self.fixed_fees[currency] = fee

    def add_percentage_rule(self, currency: str, rate: Decimal):
        """Add a specific percentage fee rule."""
        self.percentage_fees[currency] = rate
