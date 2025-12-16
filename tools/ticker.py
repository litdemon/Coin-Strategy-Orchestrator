from dataclasses import dataclass
from typing import Any

@dataclass
class TickerBase:
    currency: str
    unit_currency: str
    

class Ticker(TickerBase):
    def __init__(self, ticker_str:str):
        if '-' in ticker_str:
            parts = ticker_str.split('-')
            self.unit_currency = parts[0]
            self.currency = parts[1]
        else:
            self.unit_currency = "KRW"  # Default unit currency as per example
            self.currency = ticker_str

    def amount(self, amount):
        if amount > 1000:
            return f"{amount:,.0f} {self.currency}"
        return f"{amount:,.4f} {self.currency}"

    def volume(self, volume):
        if volume > 1000000:
            return f"{volume/1000:,.0f}K {self.currency}"
        elif volume > 1000:
            return f"{volume/1000:,.0f}K {self.currency}"
        elif volume > 1:
            return f"{volume:,.2f} {self.currency}"
        elif volume > 0.001:
            return f"{volume:,.4f} {self.currency}"
        elif volume > 0.000001:
            return f"{volume:,.6f} {self.currency}"
        else:
            return f"{volume:,.8f} {self.currency}"

    @property
    def ticker(self):
        if self.currency == "KRW":
            return self.currency
        return f"{self.unit_currency}-{self.currency}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Ticker):
            return self.ticker == other.ticker
        elif isinstance(other, str):
            return other in [self.ticker, self.currency]
        return False

    def __str__(self):
        return self.ticker
