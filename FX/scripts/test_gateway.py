#!/usr/bin/env python3
"""Quick test: connect to IB Gateway on port 4002 and fetch EURUSD price using ib_insync."""
import sys, asyncio
import ib_insync

async def main():
    ib = ib_insync.IB()
    print("Connecting to IB Gateway 127.0.0.1:4002 ...")
    try:
        await ib.connectAsync("127.0.0.1", 4002, clientId=99, timeout=10)
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

    print(f"✓ Connected — account: {ib.managedAccounts()}")

    # Request delayed market data (no live subscription needed)
    ib.reqMarketDataType(3)

    contract = ib_insync.Forex("EURUSD")
    # Don't qualifyContracts — just request directly
    ticker = ib.reqMktData(contract, "", False, False)

    # Wait up to 15s for a price tick
    for _ in range(15):
        await asyncio.sleep(1)
        if ticker.bid and ticker.bid > 0:
            break

    bid  = ticker.bid
    ask  = ticker.ask
    last = ticker.last

    if bid and bid > 0:
        print(f"✓ EURUSD  BID={bid:.5f}  ASK={ask:.5f}")
        print(f"\n✓ IB Gateway fully working — price received!")
    else:
        print(f"~ Connected OK, no real-time price (market closed or delayed)")
        print(f"  bid={bid}  ask={ask}  last={last}")

    ib.disconnect()

asyncio.run(main())




