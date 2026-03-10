"""
ENGINE AUDIT - Dowodowy audyt na surowych danych
"""
import pandas as pd
import numpy as np
import sys
import os

print("="*80)
print("ENGINE AUDIT - EVIDENCE-BASED VERIFICATION")
print("="*80)
print()

# Load data
print("Loading data...")
trades = pd.read_csv('data/outputs/trades_full_2_EURUSD_H1_2021_2024.csv', parse_dates=['entry_time', 'exit_time'])
reported = pd.read_csv('data/outputs/full_run_top3_summary.csv')
reported = reported[reported['rank'] == 2].iloc[0]
bars = pd.read_csv('data/bars/eurusd_h1_bars.csv', index_col='timestamp', parse_dates=True)

print(f"Trades loaded: {len(trades)}")
print(f"Bars loaded: {len(bars)}")
print()

# ============================================================================
# 1. METRIC RECOMPUTATION AUDIT
# ============================================================================
print("="*80)
print("1. METRIC RECOMPUTATION AUDIT")
print("="*80)
print()

results = []

# Expectancy R
if 'R' in trades.columns:
    recomp_exp = trades['R'].mean()
    diff_exp = abs(reported['overall_expectancy_R'] - recomp_exp)
    match_exp = diff_exp < 0.001
    print(f"Expectancy R:")
    print(f"  Reported:    {reported['overall_expectancy_R']:.6f}")
    print(f"  Recomputed:  {recomp_exp:.6f}")
    print(f"  Diff:        {diff_exp:.6f}")
    print(f"  Match:       {match_exp}")
    print()
    results.append(('Expectancy_R', reported['overall_expectancy_R'], recomp_exp, diff_exp, match_exp))
else:
    print("WARNING: R column missing in trades!")
    recomp_exp = 0
    results.append(('Expectancy_R', reported['overall_expectancy_R'], 0, 999, False))

# Win Rate
wins = (trades['pnl'] > 0).sum()
total = len(trades)
recomp_wr = (wins / total * 100) if total > 0 else 0
diff_wr = abs(reported['overall_win_rate'] - recomp_wr)
match_wr = diff_wr < 0.1
print(f"Win Rate:")
print(f"  Reported:    {reported['overall_win_rate']:.2f}%")
print(f"  Recomputed:  {recomp_wr:.2f}%")
print(f"  Diff:        {diff_wr:.2f}%")
print(f"  Match:       {match_wr}")
print()
results.append(('Win_Rate', reported['overall_win_rate'], recomp_wr, diff_wr, match_wr))

# Profit Factor
gross_wins = trades[trades['pnl'] > 0]['pnl'].sum()
gross_losses = abs(trades[trades['pnl'] < 0]['pnl'].sum())
recomp_pf = gross_wins / gross_losses if gross_losses > 0 else 0
diff_pf = abs(reported['overall_profit_factor'] - recomp_pf)
match_pf = diff_pf < 0.01
print(f"Profit Factor:")
print(f"  Reported:    {reported['overall_profit_factor']:.4f}")
print(f"  Recomputed:  {recomp_pf:.4f}")
print(f"  Diff:        {diff_pf:.4f}")
print(f"  Match:       {match_pf}")
print()
results.append(('Profit_Factor', reported['overall_profit_factor'], recomp_pf, diff_pf, match_pf))

# Max Drawdown
initial = 10000
equity = initial
equity_curve = [equity]
trades_sorted = trades.sort_values('exit_time')
for pnl in trades_sorted['pnl']:
    equity += pnl
    equity_curve.append(equity)

peak = equity_curve[0]
max_dd_pct = 0
for val in equity_curve:
    if val > peak:
        peak = val
    dd = (peak - val) / peak * 100
    if dd > max_dd_pct:
        max_dd_pct = dd

diff_dd = abs(reported['overall_maxDD_pct'] - max_dd_pct)
match_dd = diff_dd < 0.1
print(f"Max Drawdown:")
print(f"  Reported:    {reported['overall_maxDD_pct']:.2f}%")
print(f"  Recomputed:  {max_dd_pct:.2f}%")
print(f"  Diff:        {diff_dd:.2f}%")
print(f"  Match:       {match_dd}")
print()
results.append(('Max_DD_pct', reported['overall_maxDD_pct'], max_dd_pct, diff_dd, match_dd))

# Summary
all_match = all([r[4] for r in results])
print(f"METRIC AUDIT RESULT: {'PASS' if all_match else 'FAIL'}")
print()

# ============================================================================
# 2. R-MULTIPLE AUDIT
# ============================================================================
print("="*80)
print("2. R-MULTIPLE AUDIT")
print("="*80)
print()

if 'R' not in trades.columns:
    print("SKIP: R column missing")
    r_audit_pass = False
    r_issues = []
else:
    # We need to calculate SL from entry_price and pnl/R
    # For trend following: RR = 1.8, so risk = pnl / R

    r_issues = []

    for idx, row in trades.iterrows():
        # Calculate what the R should be from pnl
        # R = pnl / risk_dollars
        # We need to infer risk from exit

        # Simple check: if exit_reason is TP and R is positive, should be around RR (1.8)
        # if exit_reason is SL and R is negative, should be around -1.0

        if row['exit_reason'] == 'TP' and row['R'] > 0:
            expected_R_range = (1.7, 1.9)  # RR 1.8 with some tolerance
            if not (expected_R_range[0] <= row['R'] <= expected_R_range[1]):
                r_issues.append({
                    'trade_id': idx,
                    'direction': row['direction'],
                    'exit_reason': row['exit_reason'],
                    'R': row['R'],
                    'expected_range': expected_R_range,
                    'issue': 'TP R outside expected range'
                })
        elif row['exit_reason'] == 'SL' and row['R'] < 0:
            expected_R_range = (-1.1, -0.9)  # Around -1.0 with tolerance
            if not (expected_R_range[0] <= row['R'] <= expected_R_range[1]):
                r_issues.append({
                    'trade_id': idx,
                    'direction': row['direction'],
                    'exit_reason': row['exit_reason'],
                    'R': row['R'],
                    'expected_range': expected_R_range,
                    'issue': 'SL R outside expected range'
                })

    print(f"Total trades: {len(trades)}")
    print(f"R anomalies (outside expected range): {len(r_issues)}")

    if len(r_issues) > 0:
        print()
        print("Sample of R anomalies (first 20):")
        for issue in r_issues[:20]:
            print(f"  Trade {issue['trade_id']}: {issue['direction']} - {issue['exit_reason']}")
            print(f"    R: {issue['R']:.4f}")
            print(f"    Expected: {issue['expected_range']}")
            print(f"    Issue: {issue['issue']}")
            print()

    r_audit_pass = len(r_issues) < 10  # Allow small number of edge cases

print(f"R-MULTIPLE AUDIT RESULT: {'PASS' if r_audit_pass else 'FAIL'}")
print()

# ============================================================================
# 3. INTRABAR CONFLICT AUDIT
# ============================================================================
print("="*80)
print("3. INTRABAR CONFLICT AUDIT")
print("="*80)
print()

conflicts = []

for idx, row in trades.iterrows():
    exit_time = row['exit_time']

    # Find exit bar
    if exit_time in bars.index:
        exit_bar = bars.loc[exit_time]

        # Calculate SL and TP from entry and R
        # For RR 1.8: risk = pnl/R, TP = entry + risk*1.8 (LONG) or entry - risk*1.8 (SHORT)

        if row['exit_reason'] == 'TP' and row['R'] > 0:
            risk_R = row['pnl'] / row['R'] / 100000  # Convert back to price

            if row['direction'] == 'LONG':
                estimated_sl = row['entry_price'] - risk_R
                estimated_tp = row['entry_price'] + risk_R * 1.8

                # Check if both were hit in same bar
                sl_hit = exit_bar['low_bid'] <= estimated_sl
                tp_hit = exit_bar['high_bid'] >= estimated_tp

                if sl_hit and tp_hit:
                    # CONFLICT: Both hit, but TP was chosen (FAIL for worst-case)
                    conflicts.append({
                        'trade_id': idx,
                        'direction': 'LONG',
                        'exit_time': exit_time,
                        'exit_reason': row['exit_reason'],
                        'entry': row['entry_price'],
                        'est_sl': estimated_sl,
                        'est_tp': estimated_tp,
                        'bar_low_bid': exit_bar['low_bid'],
                        'bar_high_bid': exit_bar['high_bid'],
                        'sl_hit': sl_hit,
                        'tp_hit': tp_hit,
                        'verdict': 'FAIL'  # TP in conflict = FAIL
                    })
            else:  # SHORT
                estimated_sl = row['entry_price'] + risk_R
                estimated_tp = row['entry_price'] - risk_R * 1.8

                sl_hit = exit_bar['high_bid'] >= estimated_sl
                tp_hit = exit_bar['low_bid'] <= estimated_tp

                if sl_hit and tp_hit:
                    conflicts.append({
                        'trade_id': idx,
                        'direction': 'SHORT',
                        'exit_time': exit_time,
                        'exit_reason': row['exit_reason'],
                        'entry': row['entry_price'],
                        'est_sl': estimated_sl,
                        'est_tp': estimated_tp,
                        'bar_low_bid': exit_bar['low_bid'],
                        'bar_high_bid': exit_bar['high_bid'],
                        'sl_hit': sl_hit,
                        'tp_hit': tp_hit,
                        'verdict': 'FAIL'
                    })

print(f"Total conflicts (SL and TP in same bar with TP exit): {len(conflicts)}")

if len(conflicts) > 0:
    print()
    print("Sample of conflicts (first 20):")
    for conf in conflicts[:20]:
        print(f"  Trade {conf['trade_id']}: {conf['direction']} - {conf['verdict']}")
        print(f"    Exit time: {conf['exit_time']}")
        print(f"    Exit reason: {conf['exit_reason']}")
        print(f"    Entry: {conf['entry']:.5f}, Est SL: {conf['est_sl']:.5f}, Est TP: {conf['est_tp']:.5f}")
        print(f"    Bar Low: {conf['bar_low_bid']:.5f}, Bar High: {conf['bar_high_bid']:.5f}")
        print(f"    SL hit: {conf['sl_hit']}, TP hit: {conf['tp_hit']}")
        print()

    conflict_audit_pass = False  # Any TP in conflict is FAIL
else:
    conflict_audit_pass = True

print(f"INTRABAR CONFLICT AUDIT RESULT: {'PASS' if conflict_audit_pass else 'FAIL'}")
print()

# ============================================================================
# 4. PIVOT LOOK-AHEAD AUDIT (SIMPLIFIED - No pivot data in trades)
# ============================================================================
print("="*80)
print("4. PIVOT LOOK-AHEAD AUDIT")
print("="*80)
print()

print("INFO: Pivot data not stored in trades CSV")
print("Checking: entry_time vs exit_time chronology")
print()

lookahead_issues = []

for idx, row in trades.iterrows():
    if row['entry_time'] >= row['exit_time']:
        lookahead_issues.append({
            'trade_id': idx,
            'entry_time': row['entry_time'],
            'exit_time': row['exit_time'],
            'issue': 'entry >= exit (time paradox)'
        })

print(f"Time paradoxes found: {len(lookahead_issues)}")

if len(lookahead_issues) > 0:
    print("Sample:")
    for issue in lookahead_issues[:20]:
        print(f"  Trade {issue['trade_id']}: {issue['issue']}")
        print(f"    Entry: {issue['entry_time']}, Exit: {issue['exit_time']}")
        print()

pivot_audit_pass = len(lookahead_issues) == 0

print(f"PIVOT LOOK-AHEAD AUDIT RESULT: {'PASS' if pivot_audit_pass else 'FAIL'}")
print(f"NOTE: Full pivot audit requires pivot timestamps in trades data")
print()

# ============================================================================
# 5. BID/ASK FEASIBILITY AUDIT
# ============================================================================
print("="*80)
print("5. BID/ASK FEASIBILITY AUDIT")
print("="*80)
print()

# Sample 50 random trades
sample_size = min(50, len(trades))
sample_indices = np.random.choice(trades.index, size=sample_size, replace=False)

feasibility_issues = []

for idx in sample_indices:
    row = trades.loc[idx]

    # Find entry and exit bars
    entry_time = row['entry_time']
    exit_time = row['exit_time']

    if entry_time in bars.index and exit_time in bars.index:
        entry_bar = bars.loc[entry_time]
        exit_bar = bars.loc[exit_time]

        # Check entry feasibility
        if row['direction'] == 'LONG':
            # LONG entry should be by ASK
            entry_feasible = entry_bar['low_ask'] <= row['entry_price'] <= entry_bar['high_ask']
            # LONG exit should be by BID
            exit_feasible = exit_bar['low_bid'] <= row['exit_price'] <= exit_bar['high_bid']
        else:  # SHORT
            # SHORT entry should be by BID
            entry_feasible = entry_bar['low_bid'] <= row['entry_price'] <= entry_bar['high_bid']
            # SHORT exit should be by ASK
            exit_feasible = exit_bar['low_ask'] <= row['exit_price'] <= exit_bar['high_ask']

        if not entry_feasible or not exit_feasible:
            feasibility_issues.append({
                'trade_id': idx,
                'direction': row['direction'],
                'entry_price': row['entry_price'],
                'entry_bar_low': entry_bar['low_ask'] if row['direction'] == 'LONG' else entry_bar['low_bid'],
                'entry_bar_high': entry_bar['high_ask'] if row['direction'] == 'LONG' else entry_bar['high_bid'],
                'entry_feasible': entry_feasible,
                'exit_price': row['exit_price'],
                'exit_bar_low': exit_bar['low_bid'] if row['direction'] == 'LONG' else exit_bar['low_ask'],
                'exit_bar_high': exit_bar['high_bid'] if row['direction'] == 'LONG' else exit_bar['high_ask'],
                'exit_feasible': exit_feasible
            })

print(f"Sampled trades: {sample_size}")
print(f"Feasibility issues: {len(feasibility_issues)}")

if len(feasibility_issues) > 0:
    print()
    print("Sample of issues (first 20):")
    for issue in feasibility_issues[:20]:
        print(f"  Trade {issue['trade_id']}: {issue['direction']}")
        print(f"    Entry: {issue['entry_price']:.5f} in [{issue['entry_bar_low']:.5f}, {issue['entry_bar_high']:.5f}] - {'OK' if issue['entry_feasible'] else 'FAIL'}")
        print(f"    Exit: {issue['exit_price']:.5f} in [{issue['exit_bar_low']:.5f}, {issue['exit_bar_high']:.5f}] - {'OK' if issue['exit_feasible'] else 'FAIL'}")
        print()

feasibility_audit_pass = len(feasibility_issues) == 0

print(f"BID/ASK FEASIBILITY AUDIT RESULT: {'PASS' if feasibility_audit_pass else 'FAIL'}")
print()

# ============================================================================
# OVERALL RESULTS
# ============================================================================
overall_pass = all_match and r_audit_pass and conflict_audit_pass and pivot_audit_pass and feasibility_audit_pass

print("="*80)
print("OVERALL AUDIT RESULTS")
print("="*80)
print()
print(f"1. Metric Recomputation:    {'PASS' if all_match else 'FAIL'}")
print(f"2. R-Multiple Validation:   {'PASS' if r_audit_pass else 'FAIL'}")
print(f"3. Intrabar Conflicts:      {'PASS' if conflict_audit_pass else 'FAIL'}")
print(f"4. Pivot Look-Ahead:        {'PASS' if pivot_audit_pass else 'FAIL'}")
print(f"5. Bid/Ask Feasibility:     {'PASS' if feasibility_audit_pass else 'FAIL'}")
print()
print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}")
print()

# ============================================================================
# SAVE EVIDENCE
# ============================================================================
print("="*80)
print("SAVING EVIDENCE FILES")
print("="*80)
print()

# Save audit summary
with open('reports/AUDIT_ENGINE_REPORT.md', 'w') as f:
    f.write("# ENGINE AUDIT REPORT - EVIDENCE-BASED VERIFICATION\n\n")
    f.write("**Date:** 2026-02-18\n")
    f.write("**Data:** trades_full_2_EURUSD_H1_2021_2024.csv (414 trades)\n")
    f.write("**Config:** #2 (Winner: +0.582R)\n\n")
    f.write("---\n\n")

    # 1. Metric Audit
    f.write("## 1. METRIC RECOMPUTATION AUDIT\n\n")
    f.write("**Objective:** Verify reported metrics by recomputing from raw trades data.\n\n")
    f.write("| Metric | Reported | Recomputed | Diff | Match |\n")
    f.write("|--------|----------|------------|------|-------|\n")
    for r in results:
        f.write(f"| {r[0]} | {r[1]:.4f} | {r[2]:.4f} | {r[3]:.6f} | {'PASS' if r[4] else 'FAIL'} |\n")
    f.write(f"\n**Result:** {'PASS - All metrics verified' if all_match else 'FAIL - Metrics mismatch'}\n\n")

    # 2. R-Multiple Audit
    f.write("## 2. R-MULTIPLE AUDIT\n\n")
    f.write("**Objective:** Verify R-multiples are consistent with exit reasons.\n\n")
    f.write(f"- Total trades checked: {len(trades)}\n")
    f.write(f"- R anomalies found: {len(r_issues) if 'r_issues' in locals() else 'N/A'}\n")

    if len(r_issues) > 0:
        f.write(f"\n**Issues Found:**\n")
        f.write("- TP exits should have R near 1.8 (RR ratio)\n")
        f.write("- SL exits should have R near -1.0\n")
        f.write(f"- {len(r_issues)} trades outside expected ranges\n\n")
        f.write("Sample (first 10):\n\n")
        for issue in r_issues[:10]:
            f.write(f"- Trade {issue['trade_id']}: {issue['direction']} {issue['exit_reason']}\n")
            f.write(f"  - R: {issue['R']:.4f} (expected: {issue['expected_range']})\n")

    f.write(f"\n**Result:** {'PASS' if r_audit_pass else 'FAIL - R anomalies detected'}\n\n")

    # 3. Intrabar Conflict Audit
    f.write("## 3. INTRABAR CONFLICT AUDIT\n\n")
    f.write("**Objective:** Verify worst-case execution when SL and TP both hit in same bar.\n\n")
    f.write(f"- Total conflicts (SL & TP in same bar): {len(conflicts)}\n")

    if len(conflicts) > 0:
        f.write(f"\n**FAIL:** {len(conflicts)} trades closed at TP despite SL also being hit.\n")
        f.write("With worst-case policy, SL should be hit first.\n\n")
        f.write("Sample (first 10):\n\n")
        for conf in conflicts[:10]:
            f.write(f"- Trade {conf['trade_id']}: {conf['direction']}\n")
            f.write(f"  - Exit time: {conf['exit_time']}\n")
            f.write(f"  - Entry: {conf['entry']:.5f}, Est SL: {conf['est_sl']:.5f}, Est TP: {conf['est_tp']:.5f}\n")
            f.write(f"  - Bar range: [{conf['bar_low_bid']:.5f}, {conf['bar_high_bid']:.5f}]\n")
            f.write(f"  - SL hit: {conf['sl_hit']}, TP hit: {conf['tp_hit']}\n")
            f.write(f"  - Exit reason: {conf['exit_reason']} (should be SL!)\n\n")

    f.write(f"**Result:** {'PASS - No conflicts' if conflict_audit_pass else f'FAIL - {len(conflicts)} worst-case violations'}\n\n")

    # 4. Pivot Look-Ahead Audit
    f.write("## 4. PIVOT LOOK-AHEAD AUDIT\n\n")
    f.write("**Objective:** Verify pivots used for SL are confirmed before entry.\n\n")
    f.write("**Note:** Pivot timestamps not stored in trades CSV. Simplified check performed.\n\n")
    f.write(f"- Time paradoxes (entry >= exit): {len(lookahead_issues)}\n")

    if len(lookahead_issues) > 0:
        f.write("\n**Issues:**\n\n")
        for issue in lookahead_issues[:10]:
            f.write(f"- Trade {issue['trade_id']}: {issue['issue']}\n")

    f.write(f"\n**Result:** {'PASS' if pivot_audit_pass else 'FAIL - Time paradoxes detected'}\n")
    f.write("\n*Full pivot audit requires pivot_time column in trades data.*\n\n")

    # 5. Bid/Ask Feasibility Audit
    f.write("## 5. BID/ASK FEASIBILITY AUDIT\n\n")
    f.write("**Objective:** Verify entry/exit prices are feasible given OHLC bid/ask.\n\n")
    f.write(f"- Sampled trades: {sample_size}\n")
    f.write(f"- Feasibility issues: {len(feasibility_issues)}\n")

    if len(feasibility_issues) > 0:
        f.write("\n**Issues Found:**\n\n")
        for issue in feasibility_issues[:10]:
            f.write(f"- Trade {issue['trade_id']}: {issue['direction']}\n")
            if not issue['entry_feasible']:
                f.write(f"  - Entry FAIL: {issue['entry_price']:.5f} not in [{issue['entry_bar_low']:.5f}, {issue['entry_bar_high']:.5f}]\n")
            if not issue['exit_feasible']:
                f.write(f"  - Exit FAIL: {issue['exit_price']:.5f} not in [{issue['exit_bar_low']:.5f}, {issue['exit_bar_high']:.5f}]\n")

    f.write(f"\n**Result:** {'PASS' if feasibility_audit_pass else f'FAIL - {len(feasibility_issues)} feasibility issues'}\n\n")

    # Overall Summary
    f.write("---\n\n")
    f.write("## OVERALL AUDIT RESULT\n\n")
    f.write(f"1. Metric Recomputation:    {'PASS' if all_match else 'FAIL'}\n")
    f.write(f"2. R-Multiple Validation:   {'PASS' if r_audit_pass else 'FAIL'}\n")
    f.write(f"3. Intrabar Conflicts:      {'PASS' if conflict_audit_pass else 'FAIL'}\n")
    f.write(f"4. Pivot Look-Ahead:        {'PASS' if pivot_audit_pass else 'FAIL'}\n")
    f.write(f"5. Bid/Ask Feasibility:     {'PASS' if feasibility_audit_pass else 'FAIL'}\n\n")
    f.write(f"**OVERALL: {'PASS' if overall_pass else 'FAIL'}**\n\n")

    f.write("---\n\n")
    f.write("*Report generated: 2026-02-18*\n")

print("[OK] Saved: reports/AUDIT_ENGINE_REPORT.md")

# Save evidence CSV
evidence_rows = []
for idx, row in trades.iterrows():
    evidence_rows.append({
        'trade_id': idx,
        'entry_time': row['entry_time'],
        'exit_time': row['exit_time'],
        'direction': row['direction'],
        'pnl': row['pnl'],
        'R': row.get('R', np.nan),
        'exit_reason': row['exit_reason'],
        'metric_audit': 'PASS' if all_match else 'FAIL',
        'r_anomaly': 'YES' if idx in [r['trade_id'] for r in (r_issues if 'r_issues' in locals() else [])] else 'NO',
        'conflict_flag': 'YES' if idx in [c['trade_id'] for c in conflicts] else 'NO',
        'lookahead_flag': 'YES' if idx in [i['trade_id'] for i in lookahead_issues] else 'NO',
        'feasibility_flag': 'YES' if idx in [i['trade_id'] for i in feasibility_issues] else 'NO'
    })

evidence_df = pd.DataFrame(evidence_rows)
evidence_df.to_csv('reports/AUDIT_ENGINE_EVIDENCE.csv', index=False)
print("[OK] Saved: reports/AUDIT_ENGINE_EVIDENCE.csv")

print()
print("="*80)
print("AUDIT COMPLETE")
print("="*80)
print()

overall_pass = all_match and r_audit_pass and conflict_audit_pass and pivot_audit_pass and feasibility_audit_pass
print(f"OVERALL RESULT: {'PASS' if overall_pass else 'FAIL'}")






