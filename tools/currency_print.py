from decimal import Decimal

class Color:
    def __init__(self, amount: Decimal, standard: Decimal=Decimal("0")):
        self.amount = amount
        if amount < standard:
            self.color = "\033[34m"
        elif amount > standard:
            self.color = "\033[31m"
        else:
            self.color = "\033[0m"
    
    def __str__(self):
        return f"{self.color}{self.amount}\033[0m"


class RateColor(Color):
    def __init__(self, amount: Decimal, standard: Decimal=Decimal("0")):
        super().__init__(amount, standard)
    def __str__(self):
        return f"{self.color}{self.amount:.2f}%\033[0m"


class WonColor(Color):
    def __init__(self, amount: Decimal, standard: Decimal=Decimal("0")):
        super().__init__(amount, standard)
    def __str__(self):
        return f"{self.color}{self.amount:>10,.0f}원\033[0m"
    
class RedWon:
    def __init__(self, amount: Decimal):
        self.amount = amount
        self.color = "\033[31m"
    def __str__(self):
        return f"{self.color}{self.amount:>10,.0f}원\033[0m"

class Won:
    def __init__(self, amount: Decimal):
        self.amount = amount
        self.color = "\033[33m"
    def __str__(self):
        return f"{self.color}{self.amount:>10,.0f}원\033[0m"
