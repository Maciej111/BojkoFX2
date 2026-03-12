#!/usr/bin/env python3
"""
Patch CSV: append TRADE_CLOSED rows for ghost FILL rows that were never closed.
Run on VM after confirming no real open positions exist for these signal_ids.

Ghost positions identified:
  - restored_1390  AUDJPY SHORT (bracket order orphaned, now cancelled)
  - restored_1391  AUDJPY SHORT (bracket order orphaned, now cancelled)
  - restored_1211  AUDJPY SHORT (bracket TP fill, purge_zombie removed record without TRADE_CLOSED)
  - restored_1831  AUDJPY SHORT (bracket TP fill, purge_zombie removed record without TRADE_CLOSED)
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

CSV_PATH = "/home/macie/bojkofx/app/FX/logs/paper_trading_ibkr.csv"
GHOST_SIGNAL_IDS = {"restored_1390", "restored_1391", "restored_1211", "restored_1831"}

def main(dry_run=False):
    rows = list(csv.DictReader(open(CSV_PATH)))
    fieldnames = list(rows[0].keys()) if rows else []

    # Find last FILL row for each ghost signal_id
    last_fill: dict = {}
    for r in rows:
        if r["event_type"] == "FILL" and r["signal_id"] in GHOST_SIGNAL_IDS:
            if r.get("fill_price", "") not in ("", "0.0", "0"):
                last_fill[r["signal_id"]] = r

    # Check which already have TRADE_CLOSED
    closed: set = set()
    for r in rows:
        if r["event_type"] == "TRADE_CLOSED" and r["signal_id"] in GHOST_SIGNAL_IDS:
            closed.add(r["signal_id"])

    need_close = {sid: row for sid, row in last_fill.items() if sid not in closed}

    if not need_close:
        print("No ghost positions to close — CSV is already clean.")
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    close_rows = []
    for sid, fill_row in need_close.items():
        reason = "Cancelled_no_fill" if fill_row["signal_id"] in ("restored_1390", "restored_1391") \
                  else "PURGE_ZOMBIE_no_close"
        close_row = dict(fill_row)
        close_row["timestamp"]    = now
        close_row["event_type"]   = "TRADE_CLOSED"
        close_row["exit_time"]    = now
        close_row["exit_price"]   = "0.0"
        close_row["exit_reason"]  = reason
        close_row["latency_ms"]   = ""
        close_row["slippage_entry_pips"] = ""
        close_row["slippage_exit_pips"]  = ""
        close_row["realized_R"]   = "0.0"
        close_row["commissions"]  = "0.0"
        close_row["spread_at_entry"] = ""
        old_timeline = fill_row.get("status_timeline", "")
        close_row["status_timeline"] = f"{old_timeline} | {reason}" if old_timeline else reason
        close_row["notes"] = "csv_patched_manually"
        close_rows.append(close_row)

        print(f"[{'DRY-RUN ' if dry_run else ''}CLOSE] {sid} {fill_row['symbol']} "
              f"{fill_row['side']} fill={fill_row['fill_price']}  → {reason}")

    if dry_run:
        print("\nDry-run mode — no changes written.")
        return

    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for row in close_rows:
            writer.writerow(row)

    print(f"\nAppended {len(close_rows)} TRADE_CLOSED row(s) to {CSV_PATH}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
