#!/usr/bin/env python3
"""Global cancel all IBKR open orders (orphaned bracket cleanup)."""
import time
from ib_insync import IB

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=97, timeout=20)
ib.reqAllOpenOrders()
ib.sleep(3)

print("Open orders before global cancel:")
active = [t for t in ib.trades()
          if t.orderStatus.status not in ("Cancelled", "Filled", "Inactive", "ApiCancelled")]
if not active:
    print("  (none)")
for t in active:
    o = t.order
    loc = getattr(t.contract, "localSymbol", "") or t.contract.symbol
    print(f"  {o.orderId}  {loc}  {o.action}  {o.totalQuantity:.0f}  "
          f"{o.orderType}  {o.tif}  {t.orderStatus.status}")

print(f"\nSending GlobalCancel to {len(active)} order(s)...")
ib.reqGlobalCancel()
ib.sleep(15)

print("\nOpen orders after global cancel:")
remaining = [t for t in ib.trades()
             if t.orderStatus.status not in ("Cancelled", "Filled", "Inactive", "ApiCancelled")]
if not remaining:
    print("  ALL CLEAR — no active orders remaining.")
else:
    for t in remaining:
        o = t.order
        loc = getattr(t.contract, "localSymbol", "") or t.contract.symbol
        print(f"  {o.orderId}  {loc}  {o.action}  {t.orderStatus.status}")

ib.disconnect()
print("Done.")
