from decimal import Decimal


def Decimal2float(data):
    """Recursively convert Decimals to floats/strings for JSON serialization, returning new copies of mutable structures."""
    if isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, dict):
        # Create a new dictionary to avoid modifying the original
        return {k: Decimal2float(v) for k, v in data.items()}
    elif isinstance(data, list):
        # Create a new list to avoid modifying the original
        return [Decimal2float(i) for i in data]
    else:
        # For other types, return the data as is (it's either immutable or not subject to conversion)
        return data