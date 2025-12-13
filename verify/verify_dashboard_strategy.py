from src.dashboard import Dashboard
import time
import random

def verify_dashboard():
    dash = Dashboard()
    dash.start()
    
    try:
        dash.log("Starting Dashboard Verification...")
        
        # 1. Add some data
        dash.update_balance({'currency': 'BTC', 'balance': 0.5, 'avg_buy_price': 50000000})
        dash.update_ticker({'code': 'BTC-KRW', 'trade_price': 51000000, 'type': 'ticker'})
        
        # 2. Add Position with Text Strategies
        dash.update_positions('BTC-KRW', [{
            'id': 'pos1',
            'entry_price': 50000000,
            'volume': 0.1,
            'strategies': ['TrailingStop', 'RSI']
        }])
        time.sleep(2)
        
        # 3. Update Strategy State
        dash.log("Updating Strategy State...")
        dash.update_strategy('BTC-KRW', 'pos1', 'TrailingStop', 'Monitoring')
        time.sleep(2)
        
        dash.update_strategy('BTC-KRW', 'pos1', 'TrailingStop', 'Triggered!')
        time.sleep(2)
        
        # 4. Add new strategy dynamically
        dash.log("Adding dynamic strategy...")
        dash.update_strategy('BTC-KRW', 'pos1', 'NewStrat', 'Init')
        time.sleep(2)
        
        dash.log("Verification Complete. Closing in 3s...")
        time.sleep(3)
        
    except KeyboardInterrupt:
        pass
    finally:
        dash.stop()

if __name__ == "__main__":
    verify_dashboard()
