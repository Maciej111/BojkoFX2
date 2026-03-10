"""
Smoke test for IBKR Paper Trading
Tests basic connectivity and bar building without placing orders
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ib_insync import IB


def test_connection():
    """Test IBKR connection"""
    print("="*60)
    print("SMOKE TEST 1: IBKR Connection")
    print("="*60)
    
    ib = IB()
    
    try:
        print("Connecting to IBKR on 127.0.0.1:7497...")
        ib.connect('127.0.0.1', 7497, clientId=999, timeout=10)
        print("✅ Connection successful")
        
        # Get account info
        account_values = ib.accountValues()
        print(f"✅ Retrieved {len(account_values)} account values")
        
        ib.disconnect()
        return True
    
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_market_data():
    """Test market data subscription"""
    print("\n" + "="*60)
    print("SMOKE TEST 2: Market Data Subscription")
    print("="*60)
    
    from ib_insync import Forex
    
    ib = IB()
    
    try:
        ib.connect('127.0.0.1', 7497, clientId=999, timeout=10)
        
        # Subscribe to EURUSD
        contract = Forex('EURUSD')
        ticker = ib.reqMktData(contract, '', False, False)
        
        print("Waiting for market data...")
        ib.sleep(2)
        
        if ticker.bid and ticker.ask:
            print(f"✅ EURUSD: Bid={ticker.bid}, Ask={ticker.ask}")
        else:
            print(f"⚠️ No quotes yet (may need market hours)")
        
        ib.disconnect()
        return True
    
    except Exception as e:
        print(f"❌ Market data failed: {e}")
        return False


def test_bar_builder():
    """Test historical bar loading"""
    print("\n" + "="*60)
    print("SMOKE TEST 3: Historical Bar Loading")
    print("="*60)
    
    from src.data.ibkr_marketdata import IBKRMarketData
    
    try:
        md = IBKRMarketData(host='127.0.0.1', port=7497, client_id=999)
        
        if not md.connect():
            print("❌ Failed to connect")
            return False
        
        # Subscribe and bootstrap
        if md.subscribe_symbol('EURUSD'):
            print("✅ Subscribed to EURUSD")
            
            bars = md.get_h1_bars('EURUSD')
            if bars is not None and len(bars) > 0:
                print(f"✅ Loaded {len(bars)} H1 bars")
                print(f"   Latest bar: {bars.index[-1]}")
            else:
                print("⚠️ No bars loaded")
        else:
            print("❌ Subscription failed")
        
        md.disconnect()
        return True
    
    except Exception as e:
        print(f"❌ Bar builder failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n")
    print("╔════════════════════════════════════════════════════════╗")
    print("║   IBKR PAPER TRADING - SMOKE TESTS                    ║")
    print("╚════════════════════════════════════════════════════════╝")
    print()
    print("Prerequisites:")
    print("  1. TWS or IB Gateway must be running")
    print("  2. API must be enabled")
    print("  3. Port 7497 must be available")
    print()
    
    input("Press Enter to start tests...")
    print()
    
    results = []
    
    # Test 1: Connection
    results.append(("Connection", test_connection()))
    
    # Test 2: Market Data
    results.append(("Market Data", test_market_data()))
    
    # Test 3: Bar Builder
    results.append(("Bar Builder", test_bar_builder()))
    
    # Summary
    print("\n" + "="*60)
    print("SMOKE TEST SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name:20s} {status}")
    
    print()
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("🎉 All smoke tests passed!")
        print("\nNext steps:")
        print("1. Run dry_run: python -m src.runners.run_paper_ibkr --dry_run 1")
        print("2. Let it run for 5-10 minutes")
        print("3. Check logs/paper_trading.csv for intents")
    else:
        print("⚠️ Some tests failed")
        print("\nTroubleshooting:")
        print("1. Is TWS/Gateway running?")
        print("2. Is API enabled in settings?")
        print("3. Try different client ID")
    
    print()


if __name__ == "__main__":
    main()

