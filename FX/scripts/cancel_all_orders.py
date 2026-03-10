"""
cancel_all_orders.py
====================
Cancels ALL open orders in IBKR paper account and resets bot state.
Run on VM: /home/macie/bojkofx/venv/bin/python scripts/cancel_all_orders.py
"""
import time
import pathlib
import json
from ib_insync import IB

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=11, timeout=20)
print(f"Connected — server time: {ib.reqCurrentTime()}")

# 1. Show current state
print("\n=== OPEN ORDERS ===")
trades = ib.openTrades()
print(f"Found {len(trades)} open orders/trades")
for t in trades:
    print(f"  orderId={t.order.orderId} {t.contract.symbol} {t.order.action} "
          f"qty={t.order.totalQuantity} status={t.orderStatus.status}")

print("\n=== POSITIONS ===")
positions = ib.positions()
print(f"Found {len(positions)} positions")
for p in positions:
    print(f"  {p.contract.symbol}  pos={p.position}  avgCost={p.avgCost}")

# 2. Cancel all open orders
if trades:
    print(f"\n=== CANCELLING {len(trades)} ORDERS ===")
    for t in trades:
        try:
            ib.cancelOrder(t.order)
            print(f"  Cancelled orderId={t.order.orderId} {t.contract.symbol} {t.order.action}")
        except Exception as e:
            print(f"  ERROR cancelling {t.order.orderId}: {e}")
    ib.sleep(3)
    remaining = ib.openTrades()
    print(f"\nRemaining open orders after cancel: {len(remaining)}")
else:
    print("\nNo open orders to cancel.")

# 3. Reset bot internal state — clear pending flags in state file
state_path = pathlib.Path(__file__).parent.parent / "data" / "outputs" / "state" / "ibkr_state.json"
if state_path.exists():
    try:
        state = json.loads(state_path.read_text())
        changed = False
        for sym, sym_state in state.items():
            if isinstance(sym_state, dict):
                if sym_state.get("pending"):
                    sym_state["pending"] = False
                    sym_state["pending_order_id"] = None
                    changed = True
                    print(f"  Reset pending flag for {sym}")
        if changed:
            state_path.write_text(json.dumps(state, indent=2))
            print(f"State file updated: {state_path}")
    except Exception as e:
        print(f"  State file error: {e}")
else:
    print(f"\nState file not found at {state_path} — skipping state reset")

ib.disconnect()
print("\nDone.")

