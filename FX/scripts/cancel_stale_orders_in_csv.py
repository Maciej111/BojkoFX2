"""
cancel_stale_orders_in_csv.py
==============================
Adds ORDER_CANCELLED rows to paper_trading_ibkr.csv for all ORDER_PLACED
entries that have no matching FILL or TRADE_CLOSED.
This resets the 'pending' flags in the dashboard.
Run on VM.
"""
import csv
import pathlib
from datetime import datetime, timezone

CSV_PATH = pathlib.Path("/home/macie/bojkofx/app/logs/paper_trading_ibkr.csv")

rows = list(csv.DictReader(CSV_PATH.open()))

# Find signal_ids that have ORDER_PLACED but no FILL or TRADE_CLOSED
placed   = {r["signal_id"]: r for r in rows if r["event_type"] == "ORDER_PLACED"}
filled   = {r["signal_id"] for r in rows if r["event_type"] in ("FILL", "TRADE_CLOSED", "ORDER_CANCELLED")}
stale    = {sig: row for sig, row in placed.items() if sig not in filled}

print(f"Total ORDER_PLACED:  {len(placed)}")
print(f"Already filled/closed: {len(filled & set(placed))}")
print(f"Stale (no fill):     {len(stale)}")

if not stale:
    print("Nothing to cancel.")
    exit(0)

now_ts = datetime.now(timezone.utc).isoformat()
cancel_rows = []
for sig, orig in stale.items():
    row = dict(orig)  # copy
    row["timestamp"]  = now_ts
    row["event_type"] = "ORDER_CANCELLED"
    row["notes"]      = "stale_order_no_fill_cancelled_by_script"
    cancel_rows.append(row)
    print(f"  Adding CANCELLED: {orig['symbol']} sig={sig} parentId={orig.get('parentOrderId')}")

# Append to CSV
fieldnames = list(csv.DictReader(CSV_PATH.open()).fieldnames)
with CSV_PATH.open("a", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    for row in cancel_rows:
        writer.writerow(row)

print(f"\nAdded {len(cancel_rows)} ORDER_CANCELLED rows to {CSV_PATH.name}")
print("Restart dashboard to apply: sudo systemctl restart bojkofx-dashboard")

