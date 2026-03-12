#!/usr/bin/env python3
"""
Emergency script: close a naked/untracked position in IBKR paper account.

Usage (on VM):
  python3 FX/scripts/emergency_close_position.py AUDJPY
  python3 FX/scripts/emergency_close_position.py AUDJPY --dry-run

Connects with clientId=99 (bot uses 7, so no conflict).
"""
import argparse
import sys
import time

from ib_insync import IB, Forex, MarketOrder


def main():
    parser = argparse.ArgumentParser(description="Emergency close untracked IBKR position")
    parser.add_argument("symbol", help="Symbol to close, e.g. AUDJPY")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=99)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done, but place no order")
    args = parser.parse_args()

    sym = args.symbol.upper()

    ib = IB()
    print(f"Connecting to IBKR {args.host}:{args.port} clientId={args.client_id}...")
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=20)
    time.sleep(1)

    # Refresh positions
    ib.reqPositions()
    ib.sleep(1)

    print("\n=== All open positions ===")
    all_positions = ib.positions()
    if not all_positions:
        print("  (none)")
    for p in all_positions:
        loc = getattr(p.contract, "localSymbol", "") or p.contract.symbol
        print(f"  {loc:12s}  pos={p.position:>10.2f}  avgCost={p.avgCost:.5f}")

    # Find target
    target = None
    for p in all_positions:
        loc = (getattr(p.contract, "localSymbol", "") or p.contract.symbol)
        normalized = loc.replace(".", "").replace("/", "").upper()
        if normalized == sym and p.position != 0:
            target = p
            break

    if target is None:
        print(f"\nERROR: No open position found for {sym}. Nothing to close.")
        ib.disconnect()
        sys.exit(1)

    qty    = abs(target.position)
    action = "BUY" if target.position < 0 else "SELL"
    print(f"\n>>> Closing {sym}: {action} {qty:.0f} @ MARKET  "
          f"(current pos={target.position}, avgCost={target.avgCost:.5f}) <<<")

    if args.dry_run:
        print("[DRY RUN] No order placed.")
        ib.disconnect()
        return

    contract = Forex(sym[:3], currency=sym[3:])
    ib.qualifyContracts(contract)
    print(f"Qualified contract: {contract.localSymbol}  conId={contract.conId}")

    order = MarketOrder(action, qty)
    trade = ib.placeOrder(contract, order)
    print(f"Order placed: orderId={trade.order.orderId}")

    # Wait up to 15 seconds for fill
    for _ in range(15):
        ib.sleep(1)
        status = trade.orderStatus.status
        filled = trade.orderStatus.filled
        price  = trade.orderStatus.avgFillPrice
        print(f"  status={status}  filled={filled}  avgFillPrice={price}")
        if status in ("Filled", "ApiCancelled", "Cancelled", "Inactive"):
            break

    final_status = trade.orderStatus.status
    if final_status == "Filled":
        print(f"\n✓ CLOSED {sym} @ {trade.orderStatus.avgFillPrice:.5f}")
    else:
        print(f"\n✗ Order did NOT fill (status={final_status}). "
              f"Check TWS/Gateway manually!")

    ib.disconnect()


if __name__ == "__main__":
    main()
