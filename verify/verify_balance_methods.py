from account.models import Balance
from decimal import Decimal

def verify_balance_methods():
    # Setup dummy data
    data = [
        {'currency': 'KRW', 'balance': '1000000', 'locked': '0.0', 'avg_buy_price': '0', 'avg_buy_price_modified': True, 'unit_currency': 'KRW'},
        {'currency': 'BTC', 'balance': '0.5', 'locked': '0.0', 'avg_buy_price': '50000000', 'avg_buy_price_modified': False, 'unit_currency': 'KRW'}
    ]
    balance_obj = Balance.from_list(data)

    # Verify get_balances()
    balances = balance_obj.get_balances()
    print("get_balances() output:", balances)
    assert len(balances) == 2
    assert balances[0]["currency"] == "KRW"
    
    # Verify get_balance("KRW")
    krw_bal = balance_obj.get_balance("KRW")
    print("get_balance('KRW'):", krw_bal)
    assert krw_bal == Decimal('1000000')

    # Verify get_balance("KRW-BTC")
    btc_bal = balance_obj.get_balance("KRW-BTC")
    print("get_balance('KRW-BTC'):", btc_bal)
    assert btc_bal == Decimal('0.5')
    
    # Verify get_balance("BTC") - direct currency code
    btc_bal_direct = balance_obj.get_balance("BTC")
    assert btc_bal_direct == Decimal('0.5')

    # Verify get_balance("XRP") - non-existent
    xrp_bal = balance_obj.get_balance("XRP")
    print("get_balance('XRP'):", xrp_bal)
    assert xrp_bal == Decimal('0')

    print("Verification Successful!")

if __name__ == "__main__":
    verify_balance_methods()
