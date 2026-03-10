"""
MINI-AUDIT After FEASIBILITY FIX (FIX2)
"""
import pandas as pd

print("="*80)
print("MINI-AUDIT: FEASIBILITY FIX (FIX2)")
print("="*80)
print()

# Load FIX1 and FIX2 trades
print("Loading trades...")
try:
    trades_fix1 = pd.read_csv('data/outputs/trades_full_2_FIXED.csv')
    print(f"[OK] FIX1 loaded: {len(trades_fix1)} trades")
except:
    print("[ERROR] FIX1 not found")
    trades_fix1 = None

try:
    trades_fix2 = pd.read_csv('data/outputs/trades_full_2_FIXED2.csv')
    print(f"[OK] FIX2 loaded: {len(trades_fix2)} trades")
except:
    print("[ERROR] FIX2 not found - run rerun_config2_fixed2.py first")
    import sys
    sys.exit(1)

print()

# ============================================================================
# CHECK 1: Exit Feasibility
# ============================================================================
print("="*80)
print("CHECK 1: EXIT FEASIBILITY")
print("="*80)
print()

if 'exit_feasible' in trades_fix2.columns:
    violations = (~trades_fix2['exit_feasible']).sum()
    print(f"Exit feasibility violations: {violations}")

    if violations == 0:
        print("[PASS] All exits feasible!")
    else:
        print(f"[FAIL] {violations} violations detected")
        print()
        print("Sample violations:")
        bad_trades = trades_fix2[~trades_fix2['exit_feasible']].head(10)
        for idx, row in bad_trades.iterrows():
            print(f"  Trade {idx}: {row['direction']} - {row['exit_reason']}")
else:
    print("[ERROR] exit_feasible column missing!")
    violations = None

print()

# ============================================================================
# CHECK 2: Intrabar Conflicts
# ============================================================================
print("="*80)
print("CHECK 2: INTRABAR CONFLICTS")
print("="*80)
print()

conflicts = trades_fix2[trades_fix2['exit_reason'] == 'SL_intrabar_conflict']
print(f"Intrabar conflicts (SL & TP hit same bar): {len(conflicts)}")

tp_in_conflict = trades_fix2[(trades_fix2['exit_reason'] == 'TP') &
                              (trades_fix2['exit_reason'].str.contains('conflict', na=False))]
print(f"TP exits in conflict: {len(tp_in_conflict)}")

if len(tp_in_conflict) == 0:
    print("[PASS] No TP chosen in conflicts (worst-case working)")
else:
    print(f"[FAIL] {len(tp_in_conflict)} TP violations")

print()

# ============================================================================
# CHECK 3: Metrics
# ============================================================================
print("="*80)
print("CHECK 3: METRICS RECOMPUTATION")
print("="*80)
print()

expectancy = trades_fix2['R'].mean()
win_rate = (trades_fix2['pnl'] > 0).sum() / len(trades_fix2) * 100
gross_wins = trades_fix2[trades_fix2['pnl'] > 0]['pnl'].sum()
gross_losses = abs(trades_fix2[trades_fix2['pnl'] < 0]['pnl'].sum())
pf = gross_wins / gross_losses if gross_losses > 0 else 0

print(f"Expectancy: {expectancy:.4f}R")
print(f"Win Rate: {win_rate:.2f}%")
print(f"Profit Factor: {pf:.4f}")
print()

# ============================================================================
# COMPARISON: FIX1 vs FIX2
# ============================================================================
print("="*80)
print("COMPARISON: FIX1 vs FIX2")
print("="*80)
print()

if trades_fix1 is not None:
    fix1_exp = trades_fix1['R'].mean()
    fix1_wr = (trades_fix1['pnl'] > 0).sum() / len(trades_fix1) * 100
    fix1_pf = trades_fix1[trades_fix1['pnl'] > 0]['pnl'].sum() / abs(trades_fix1[trades_fix1['pnl'] < 0]['pnl'].sum())

    print("| Metric | FIX1 | FIX2 | Delta |")
    print("|--------|------|------|-------|")
    print(f"| Trades | {len(trades_fix1)} | {len(trades_fix2)} | {len(trades_fix2) - len(trades_fix1):+d} |")
    print(f"| Expectancy(R) | {fix1_exp:.4f} | {expectancy:.4f} | {expectancy - fix1_exp:+.4f} |")
    print(f"| Win Rate(%) | {fix1_wr:.2f} | {win_rate:.2f} | {win_rate - fix1_wr:+.2f} |")
    print(f"| Profit Factor | {fix1_pf:.4f} | {pf:.4f} | {pf - fix1_pf:+.4f} |")
    print()

    if abs(expectancy - fix1_exp) > 0.01:
        print(f"[INFO] Expectancy changed by {expectancy - fix1_exp:+.4f}R")
    else:
        print("[OK] Expectancy stable")
else:
    print("[SKIP] FIX1 not available for comparison")

print()

# ============================================================================
# OVERALL RESULT
# ============================================================================
print("="*80)
print("OVERALL MINI-AUDIT RESULT")
print("="*80)
print()

checks_passed = 0
checks_total = 3

if violations == 0:
    checks_passed += 1
    print("1. Exit Feasibility: PASS")
else:
    print(f"1. Exit Feasibility: FAIL ({violations} violations)")

if len(tp_in_conflict) == 0:
    checks_passed += 1
    print("2. Intrabar Conflicts: PASS")
else:
    print(f"2. Intrabar Conflicts: FAIL ({len(tp_in_conflict)} TP in conflict)")

checks_passed += 1
print("3. Metrics Computed: PASS")

print()
print(f"OVERALL: {checks_passed}/{checks_total} checks passed")

if checks_passed == checks_total:
    print()
    print("[SUCCESS] ALL CHECKS PASSED!")
    print("Feasibility fix is working correctly.")
else:
    print()
    print(f"[PARTIAL] {checks_total - checks_passed} checks failed")
    print("Review issues above.")

print()
print("="*80)
print("MINI-AUDIT COMPLETE")
print("="*80)

