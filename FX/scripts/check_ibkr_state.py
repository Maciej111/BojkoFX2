"""
check_ibkr_state.py
-------------------
Diagnostics: active IBKR orders, positions, SQLite bot state.
Run on VM: /home/macie/bojkofx/venv/bin/python /tmp/check_ibkr_state.py
"""
from ib_insync import IB

ib = IB()
ib.connect("127.0.0.1", 4002, clientId=12, timeout=15)
print(f"Connected — server time: {ib.reqCurrentTime()}")

print("\n=== OPEN TRADES (active only) ===")
trades = ib.trades()
active = [t for t in trades if t.orderStatus.status not in ("Cancelled", "Filled", "Inactive")]
print(f"Active trades: {len(active)}")
parent_ids = set()
for t in active:
    pid = getattr(t.order, "parentId", 0)
    if pid == 0:
        parent_ids.add(t.order.orderId)
    print(
        f"  id={t.order.orderId:5d}  parent={pid:5d}  "
        f"{t.contract.localSymbol:10s}  {t.order.action:4s}  "
        f"qty={t.order.totalQuantity:6.0f}  type={t.order.orderType:4s}  "
        f"status={t.orderStatus.status}"
    )

print(f"\nUnique parent brackets: {len(parent_ids)} -> {sorted(parent_ids)}")

print("\n=== POSITIONS (non-zero) ===")
pos_count = 0
for p in ib.positions():
    if abs(p.position) > 0:
        pos_count += 1
        print(f"  {p.contract.localSymbol:10s}  pos={p.position:8.0f}  avgCost={p.avgCost:.5f}")
if pos_count == 0:
    print("  (none)")

print("\n=== SQLite state_store (open/pending orders) ===")
import sqlite3, os
db_path = "/home/macie/bojkofx/app/data/state/bojkofx_state.db"
if os.path.exists(db_path):
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT parent_id, symbol, status, created_at, updated_at "
        "FROM orders WHERE status NOT IN ('EXITED','CANCELLED','EXPIRED') "
        "ORDER BY updated_at DESC LIMIT 20"
    ).fetchall()
    print(f"Open/pending in DB ({len(rows)} rows):")
    for r in rows:
        print(f"  parent_id={r[0]:5d}  {r[1]:10s}  status={r[2]:20s}  updated={r[4]}")
    con.close()
else:
    print(f"  DB not found: {db_path}")

ib.disconnect()
print("\nDone.")
from ib_insync import IB
ib = IB() 
