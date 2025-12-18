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
    

class Won:
    def __init__(self, amount: Decimal):
        self.amount = amount

    def __str__(self):
        return f"{self.amount:,.0f}원"


class WonR(Won):
    def __init__(self, amount: Decimal):
        super().__init__(amount)
        self.color = "\033[31m"

    def __str__(self):
        parent = super().__str__()
        return f"{self.color}{parent}\033[0m"
    
class WonG(Won):
    def __init__(self, amount: Decimal):
        super().__init__(amount)
        self.color = "\033[32m"

    def __str__(self):
        parent = super().__str__()
        return f"{self.color}{parent}\033[0m"
    
class WonY(Won):
    def __init__(self, amount: Decimal):
        super().__init__(amount)
        self.color = "\033[33m"

    def __str__(self):
        parent = super().__str__()
        return f"{self.color}{parent}\033[0m"
    
class WonB(Won):
    def __init__(self, amount: Decimal):
        super().__init__(amount)
        self.color = "\033[34m"

    def __str__(self):
        parent = super().__str__()
        return f"{self.color}{parent}\033[0m"