#!/usr/bin/env python3
"""
Emergency: cancel specific IBKR orders by orderId.

Usage (on VM):
  python3 /tmp/cancel_orders.py --order-ids 1390 1391
  python3 /tmp/cancel_orders.py --order-ids 1390 1391 --dry-run
  python3 /tmp/cancel_orders.py --show-all  # just show orders and positions

Connects with clientId=98 (bot uses 7, no conflict).
"""
import argparse
import sys
import time

from ib_insync import IB


def main():
    parser = argparse.ArgumentParser(description="Cancel IBKR orders by ID")
    parser.add_argument("--order-ids", nargs="*", type=int, default=[],
                        help="Order IDs to cancel")
    parser.add_argument("--show-all", action="store_true",
                        help="Show all open orders and positions, then exit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=98)
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be cancelled, but do nothing")
    args = parser.parse_args()

    ib = IB()
    print(f"Connecting to IBKR {args.host}:{args.port} clientId={args.client_id}...")
    ib.connect(args.host, args.port, clientId=args.client_id, timeout=20)

    # Wait for IBKR to push account data
    ib.sleep(2)

    # Request ALL open orders (across all clientIds) and positions
    ib.reqAllOpenOrders()
    ib.reqPositions()
    ib.sleep(3)

    # ── Show open positions ───────────────────────────────────────────────────
    all_positions = ib.positions()
    print("\n=== IBKR Open Positions ===")
    if not all_positions:
        print("  (none reported — paper FX positions may require longer wait)")
    for p in all_positions:
        loc = getattr(p.contract, "localSymbol", "") or p.contract.symbol
        print(f"  {loc:12s}  pos={p.position:>10.2f}  avgCost={p.avgCost:.5f}")

    # ── Show all open orders ──────────────────────────────────────────────────
    all_trades = ib.trades()
    active_trades = [
        t for t in all_trades
        if t.orderStatus.status not in ("Cancelled", "Filled", "Inactive", "ApiCancelled")
    ]
    print(f"\n=== IBKR Open Orders ({len(active_trades)} active) ===")
    for t in active_trades:
        loc = getattr(t.contract, "localSymbol", "") or t.contract.symbol
        o = t.order
        print(f"  orderId={o.orderId:5d}  {loc:12s}  {o.action:5s}  "
              f"{o.totalQuantity:8.0f}  {o.orderType:5s}  "
              f"lmt={o.lmtPrice:.5f}  aux={o.auxPrice:.5f}  "
              f"tif={o.tif}  parentId={getattr(o,'parentId',0)}  "
              f"status={t.orderStatus.status}")

    if args.show_all:
        ib.disconnect()
        return

    if not args.order_ids:
        print("\nNo --order-ids specified. Use --show-all to inspect, or provide order IDs to cancel.")
        ib.disconnect()
        return

    # ── Cancel requested orders ───────────────────────────────────────────────
    cancel_ids = set(args.order_ids)
    trade_by_id = {t.order.orderId: t for t in all_trades}

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Cancelling orders: {sorted(cancel_ids)}")
    cancelled = []
    not_found = []

    for oid in sorted(cancel_ids):
        trade = trade_by_id.get(oid)
        if trade is None:
            print(f"  WARN: orderId={oid} not found in ib.trades() — may already be gone")
            not_found.append(oid)
            continue

        loc = getattr(trade.contract, "localSymbol", "") or trade.contract.symbol
        o = trade.order
        print(f"  {'[DRY-RUN] Would cancel' if args.dry_run else 'Cancelling'}: "
              f"orderId={oid}  {loc}  {o.action}  {o.totalQuantity:.0f}  "
              f"{o.orderType}  status={trade.orderStatus.status}")

        if not args.dry_run:
            ib.cancelOrder(trade.order)
            cancelled.append(oid)

    if not args.dry_run and cancelled:
        print(f"\nWaiting 20s for cancellation confirmations...")
        ib.sleep(20)

        # Verify
        updated_trades = {t.order.orderId: t for t in ib.trades()}
        for oid in cancelled:
            t = updated_trades.get(oid)
            if t:
                print(f"  orderId={oid}: status now = {t.orderStatus.status}")
            else:
                print(f"  orderId={oid}: no longer in ib.trades() (cancelled/gone)")

    print(f"\nSummary: cancelled={cancelled}  not_found={not_found}")
    ib.disconnect()
    print("Done.")


if __name__ == "__main__":
    main()
