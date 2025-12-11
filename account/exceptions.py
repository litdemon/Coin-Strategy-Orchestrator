class AccountException(Exception):
    """Base exception for account related errors."""
    pass

class InsufficientBalanceException(AccountException):
    """Raised when there is insufficient balance for an operation."""
    pass

class OrderNotFoundException(AccountException):
    """Raised when an order is not found."""
    pass

class InvalidOrderStateException(AccountException):
    """Raised when an order is in an invalid state for the requested operation."""
    pass
