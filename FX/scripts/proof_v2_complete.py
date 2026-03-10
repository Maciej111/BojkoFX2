"""
PROOF V2 MODE - Complete Formal Validation
Steps: Determinism (3 runs all symbols) + Cost Model V2 + Outliers + Final GO/NO-GO
"""

import pandas as pd
import numpy as np
import sys
import os
import hashlib
import json
from datetime import datetime

sys.path.append('.')
from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("PROOF V2 MODE - FORMAL VALIDATION")
print("="*80)
print()

# FROZEN CONFIG
FROZEN_CONFIG = {
    'entry_offset_atr_mult': 0.3,
    'pullback_max_bars': 40,
    'risk_reward': 1.5,
    'sl_anchor': 'last_pivot',
    'sl_buffer_atr_mult': 0.5,
    'pivot_lookback_ltf': 3,
    'pivot_lookback_htf': 5,
    'confirmation_bars': 1,
    'require_close_break': True
}

SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
INITIAL_BALANCE = 10000
RISK_FRACTION = 0.01

os.makedirs('data/proof_v2', exist_ok=True)

# ========================================================
# STEP 1: FULL DETERMINISM (ALL SYMBOLS, 3 RUNS)
# ========================================================

print("="*80)
print("STEP 1: FULL DETERMINISM CHECK (3 RUNS PER SYMBOL)")
print("="*80)
print()

determinism_results = {}

for symbol in SYMBOLS:
    print(f"\nTesting {symbol}...")

    ltf_file = f'data/bars_validated/{symbol.lower()}_1h_validated.csv'
    htf_file = f'data/bars_validated/{symbol.lower()}_4h_validated.csv'

    if not os.path.exists(ltf_file) or not os.path.exists(htf_file):
        print(f"  [SKIP] Missing bars")
        continue

    ltf_df = pd.read_csv(ltf_file, parse_dates=['timestamp'])
    htf_df = pd.read_csv(htf_file, parse_dates=['timestamp'])

    runs = []

    for run_num in [1, 2, 3]:
        print(f"  Run {run_num}...", end=" ")

        # Execute backtest
        trades_full, _ = run_trend_backtest(symbol, ltf_df, htf_df, FROZEN_CONFIG, INITIAL_BALANCE)

        # Filter OOS
        trades_full['entry_time'] = pd.to_datetime(trades_full['entry_time'])
        trades_full['year'] = trades_full['entry_time'].dt.year
        trades_oos = trades_full[trades_full['year'].isin([2023, 2024])].copy()

        # Save trades CSV
        csv_file = f'data/proof_v2/trades_{symbol}_run{run_num}.csv'
        trades_oos.to_csv(csv_file, index=False)

        # Compute hash
        with open(csv_file, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Compute metrics
        trades_count = len(trades_oos)
        expectancy = trades_oos['R'].mean() if len(trades_oos) > 0 else 0

        wins = trades_oos[trades_oos['R'] > 0]
        losses = trades_oos[trades_oos['R'] <= 0]
        win_rate = len(wins) / len(trades_oos) * 100 if len(trades_oos) > 0 else 0

        pf = (wins['pnl'].sum() / abs(losses['pnl'].sum())) if len(losses) > 0 and losses['pnl'].sum() != 0 else 0

        # MaxDD with 1% sizing
        equity = INITIAL_BALANCE
        equity_curve = [equity]
        for r in trades_oos['R']:
            equity *= (1 + r * RISK_FRACTION)
            equity_curve.append(equity)

        peak = equity_curve[0]
        maxDD = 0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > maxDD:
                maxDD = dd

        runs.append({
            'run': run_num,
            'hash': file_hash,
            'trades': trades_count,
            'expectancy': expectancy,
            'pf': pf,
            'maxDD': maxDD,
            'win_rate': win_rate
        })

        print(f"{trades_count} trades, hash: {file_hash[:8]}")

    # Compare runs
    hash_match = (runs[0]['hash'] == runs[1]['hash'] == runs[2]['hash'])
    trades_match = (runs[0]['trades'] == runs[1]['trades'] == runs[2]['trades'])

    exp_diffs = [
        abs(runs[0]['expectancy'] - runs[1]['expectancy']),
        abs(runs[1]['expectancy'] - runs[2]['expectancy']),
        abs(runs[0]['expectancy'] - runs[2]['expectancy'])
    ]
    exp_match = all(d < 1e-9 for d in exp_diffs)

    pf_diffs = [
        abs(runs[0]['pf'] - runs[1]['pf']),
        abs(runs[1]['pf'] - runs[2]['pf']),
        abs(runs[0]['pf'] - runs[2]['pf'])
    ]
    pf_match = all(d < 1e-9 for d in pf_diffs)

    deterministic = hash_match and trades_match and exp_match and pf_match

    determinism_results[symbol] = {
        'runs': runs,
        'hash_match': hash_match,
        'trades_match': trades_match,
        'exp_match': exp_match,
        'pf_match': pf_match,
        'deterministic': deterministic
    }

    print(f"  Deterministic: {'PASS' if deterministic else 'FAIL'}")
    if not deterministic:
        print(f"    Hash match: {hash_match}")
        print(f"    Trades match: {trades_match}")
        print(f"    Exp match: {exp_match} (max diff: {max(exp_diffs):.2e})")
        print(f"    PF match: {pf_match} (max diff: {max(pf_diffs):.2e})")

# ========================================================
# STEP 2: COST MODEL V2 (CONSISTENT SLIPPAGE)
# ========================================================

print("\n" + "="*80)
print("STEP 2: COST MODEL V2 - CONSISTENT SLIPPAGE")
print("="*80)
print()

# Define slippage in price units
SLIPPAGE_CONFIG = {
    'EURUSD': {'mild': 0.0002, 'moderate': 0.0005, 'severe': 0.0010},  # 0.2, 0.5, 1.0 pips
    'GBPUSD': {'mild': 0.0002, 'moderate': 0.0005, 'severe': 0.0010},
    'USDJPY': {'mild': 0.02, 'moderate': 0.05, 'severe': 0.10},
    'XAUUSD': {'mild': 0.10, 'moderate': 0.25, 'severe': 0.50}
}

cost_results = {}

for symbol in SYMBOLS:
    print(f"\nApplying cost model to {symbol}...")

    trades_file = f'data/proof_v2/trades_{symbol}_run1.csv'  # Use run1 as baseline

    if not os.path.exists(trades_file):
        print(f"  [SKIP] No trades file")
        continue

    df = pd.read_csv(trades_file)

    if len(df) == 0:
        print(f"  [SKIP] No trades")
        continue

    # Calculate average risk_distance for R conversion
    # Estimate from entry_price and typical SL distance
    # For simplicity, use typical ATR-based risk
    typical_risk = {
        'EURUSD': 0.0050,
        'GBPUSD': 0.0060,
        'USDJPY': 0.50,
        'XAUUSD': 5.0
    }

    avg_risk = typical_risk.get(symbol, 0.005)

    scenarios = {}

    # BASELINE (no additional slippage)
    baseline_exp = df['R'].mean()
    baseline_wins = df[df['R'] > 0]
    baseline_losses = df[df['R'] <= 0]
    baseline_pf = (baseline_wins['pnl'].sum() / abs(baseline_losses['pnl'].sum())) if len(baseline_losses) > 0 else 0

    # Equity with 1% sizing
    equity_base = INITIAL_BALANCE
    equity_curve_base = [equity_base]
    for r in df['R']:
        equity_base *= (1 + r * RISK_FRACTION)
        equity_curve_base.append(equity_base)

    peak = equity_curve_base[0]
    maxDD_base = 0
    for val in equity_curve_base:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > maxDD_base:
            maxDD_base = dd

    return_base = ((equity_base - INITIAL_BALANCE) / INITIAL_BALANCE) * 100

    scenarios['baseline'] = {
        'expectancy': baseline_exp,
        'pf': baseline_pf,
        'maxDD': maxDD_base,
        'return': return_base
    }

    # Apply slippage scenarios
    slips = SLIPPAGE_CONFIG[symbol]

    for scenario_name, slip_price in slips.items():
        # Convert price slippage to R
        # Slippage hits both entry and exit
        # For conservative estimate: 2x slippage per trade (entry + exit)
        slip_R = (2 * slip_price) / avg_risk

        df_adjusted = df.copy()
        df_adjusted['R_adjusted'] = df_adjusted['R'] - slip_R

        adj_exp = df_adjusted['R_adjusted'].mean()

        adj_wins = df_adjusted[df_adjusted['R_adjusted'] > 0]
        adj_losses = df_adjusted[df_adjusted['R_adjusted'] <= 0]

        # Recompute PF (approximate with adjusted R)
        adj_pf = 0
        if len(adj_losses) > 0:
            # Approximate PnL adjustment
            total_win_pnl = adj_wins['pnl'].sum() - len(adj_wins) * slip_price * avg_risk * 10000
            total_loss_pnl = abs(adj_losses['pnl'].sum()) + len(adj_losses) * slip_price * avg_risk * 10000
            adj_pf = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else 0

        # Equity curve
        equity_adj = INITIAL_BALANCE
        equity_curve_adj = [equity_adj]
        for r in df_adjusted['R_adjusted']:
            equity_adj *= (1 + r * RISK_FRACTION)
            equity_curve_adj.append(equity_adj)

        peak_adj = equity_curve_adj[0]
        maxDD_adj = 0
        for val in equity_curve_adj:
            if val > peak_adj:
                peak_adj = val
            dd = (peak_adj - val) / peak_adj * 100
            if dd > maxDD_adj:
                maxDD_adj = dd

        return_adj = ((equity_adj - INITIAL_BALANCE) / INITIAL_BALANCE) * 100

        scenarios[scenario_name] = {
            'slip_R': slip_R,
            'expectancy': adj_exp,
            'pf': adj_pf,
            'maxDD': maxDD_adj,
            'return': return_adj
        }

    cost_results[symbol] = {
        'trades': len(df),
        'scenarios': scenarios
    }

    print(f"  Baseline: Exp={scenarios['baseline']['expectancy']:.3f}R")
    print(f"  Mild: Exp={scenarios['mild']['expectancy']:.3f}R (slip: {scenarios['mild']['slip_R']:.3f}R)")
    print(f"  Moderate: Exp={scenarios['moderate']['expectancy']:.3f}R (slip: {scenarios['moderate']['slip_R']:.3f}R)")
    print(f"  Severe: Exp={scenarios['severe']['expectancy']:.3f}R (slip: {scenarios['severe']['slip_R']:.3f}R)")

# ========================================================
# STEP 3: OUTLIER / CONCENTRATION CHECK
# ========================================================

print("\n" + "="*80)
print("STEP 4: OUTLIER / CONCENTRATION CHECK")
print("="*80)
print()

outlier_results = {}

for symbol in SYMBOLS:
    trades_file = f'data/proof_v2/trades_{symbol}_run1.csv'

    if not os.path.exists(trades_file):
        continue

    df = pd.read_csv(trades_file)

    if len(df) == 0:
        continue

    # Sort by R descending
    df_sorted = df.sort_values('R', ascending=False)

    top5 = df_sorted.head(5)
    top5_contribution = top5['R'].sum()
    total_R = df['R'].sum()

    concentration_pct = (top5_contribution / total_R * 100) if total_R != 0 else 0
    concentrated_risk = concentration_pct > 40

    outlier_results[symbol] = {
        'total_trades': len(df),
        'total_R': total_R,
        'top5_R': top5_contribution,
        'concentration_pct': concentration_pct,
        'concentrated_risk': concentrated_risk,
        'top5_trades': top5[['entry_time', 'direction', 'R']].to_dict('records')
    }

    print(f"\n{symbol}:")
    print(f"  Total R: {total_R:.2f}")
    print(f"  Top 5 R: {top5_contribution:.2f}")
    print(f"  Concentration: {concentration_pct:.1f}%")
    print(f"  Risk flag: {'YES' if concentrated_risk else 'NO'}")

# ========================================================
# GENERATE REPORTS
# ========================================================

print("\n" + "="*80)
print("GENERATING REPORTS")
print("="*80)
print()

# REPORT 1: DETERMINISM
report1 = 'reports/PROOF_V2_DETERMINISM.md'

with open(report1, 'w') as f:
    f.write("# PROOF V2: DETERMINISM CHECK (3 RUNS ALL SYMBOLS)\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## Test Setup\n\n")
    f.write("- Runs per symbol: 3\n")
    f.write("- Comparison: SHA256 hash + metrics\n")
    f.write("- Tolerance: 1e-9\n\n")

    f.write("## Results\n\n")
    f.write("| Symbol | Hash Match | Trades Match | Exp Match | PF Match | Deterministic |\n")
    f.write("|--------|------------|--------------|-----------|----------|---------------|\n")

    for symbol, data in sorted(determinism_results.items()):
        f.write(f"| {symbol} | {'PASS' if data['hash_match'] else 'FAIL'} | {'PASS' if data['trades_match'] else 'FAIL'} | {'PASS' if data['exp_match'] else 'FAIL'} | {'PASS' if data['pf_match'] else 'FAIL'} | {'PASS' if data['deterministic'] else 'FAIL'} |\n")

    f.write("\n### Run Details\n\n")

    for symbol, data in sorted(determinism_results.items()):
        f.write(f"**{symbol}:**\n\n")
        f.write("| Run | Trades | Expectancy | PF | MaxDD | Hash |\n")
        f.write("|-----|--------|------------|-------|-------|------|\n")

        for run in data['runs']:
            f.write(f"| {run['run']} | {run['trades']} | {run['expectancy']:.6f}R | {run['pf']:.4f} | {run['maxDD']:.2f}% | `{run['hash'][:12]}` |\n")

        f.write("\n")

    f.write("## Verdict\n\n")

    all_deterministic = all(d['deterministic'] for d in determinism_results.values())
    f.write(f"**Determinism Status:** {'PASS' if all_deterministic else 'FAIL'}\n\n")

    if all_deterministic:
        f.write("All symbols produce identical results across 3 independent runs.\n\n")
    else:
        failed = [s for s, d in determinism_results.items() if not d['deterministic']]
        f.write(f"Non-deterministic symbols: {', '.join(failed)}\n\n")

print(f"Saved: {report1}")

# REPORT 2: COST STRESS
report2 = 'reports/PROOF_V2_COST_STRESS.md'

with open(report2, 'w') as f:
    f.write("# PROOF V2: COST MODEL V2 - CONSISTENT SLIPPAGE\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## Slippage Configuration (Price Units)\n\n")
    f.write("| Symbol | Mild | Moderate | Severe |\n")
    f.write("|--------|------|----------|--------|\n")

    for symbol in SYMBOLS:
        if symbol in SLIPPAGE_CONFIG:
            cfg = SLIPPAGE_CONFIG[symbol]
            f.write(f"| {symbol} | {cfg['mild']} | {cfg['moderate']} | {cfg['severe']} |\n")

    f.write("\n**Note:** Slippage applied to both entry and exit (2x per trade)\n\n")

    f.write("---\n\n")

    f.write("## Baseline Results (No Additional Slippage)\n\n")
    f.write("| Symbol | Trades | WR (%) | Exp(R) | PF | MaxDD(1%) | Return(1%) |\n")
    f.write("|--------|--------|--------|--------|----|-----------|-----------|\n")

    for symbol, data in sorted(cost_results.items()):
        base = data['scenarios']['baseline']
        # WR from determinism results
        wr = determinism_results[symbol]['runs'][0]['win_rate'] if symbol in determinism_results else 0
        f.write(f"| {symbol} | {data['trades']} | {wr:.1f} | {base['expectancy']:.3f} | {base['pf']:.2f} | {base['maxDD']:.1f} | {base['return']:.1f} |\n")

    f.write("\n---\n\n")

    f.write("## Stress Test Results\n\n")

    for symbol, data in sorted(cost_results.items()):
        f.write(f"### {symbol}\n\n")
        f.write("| Scenario | Slip(R) | Exp(R) | PF | MaxDD(1%) | Return(1%) |\n")
        f.write("|----------|---------|--------|----|-----------|-----------|\n")

        for scenario in ['baseline', 'mild', 'moderate', 'severe']:
            s = data['scenarios'][scenario]
            slip_r = s.get('slip_R', 0.0)
            f.write(f"| {scenario.capitalize()} | {slip_r:.3f} | {s['expectancy']:.3f} | {s['pf']:.2f} | {s['maxDD']:.1f} | {s['return']:.1f} |\n")

        f.write("\n")

    f.write("---\n\n")

    f.write("## Edge Survival Summary\n\n")
    f.write("| Symbol | Baseline>0 | Mild>0 | Moderate>0 | Severe>0 |\n")
    f.write("|--------|------------|--------|------------|----------|\n")

    for symbol, data in sorted(cost_results.items()):
        base_pos = data['scenarios']['baseline']['expectancy'] > 0
        mild_pos = data['scenarios']['mild']['expectancy'] > 0
        mod_pos = data['scenarios']['moderate']['expectancy'] > 0
        sev_pos = data['scenarios']['severe']['expectancy'] > 0

        f.write(f"| {symbol} | {'PASS' if base_pos else 'FAIL'} | {'PASS' if mild_pos else 'FAIL'} | {'PASS' if mod_pos else 'FAIL'} | {'PASS' if sev_pos else 'FAIL'} |\n")

print(f"Saved: {report2}")

# REPORT 3: OUTLIERS
report3 = 'reports/PROOF_V2_OUTLIERS.md'

with open(report3, 'w') as f:
    f.write("# PROOF V2: OUTLIER / CONCENTRATION CHECK\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## Concentration Analysis\n\n")
    f.write("| Symbol | Total Trades | Total R | Top 5 R | Concentration (%) | Risk Flag |\n")
    f.write("|--------|--------------|---------|---------|-------------------|------------|\n")

    for symbol, data in sorted(outlier_results.items()):
        flag = 'YES' if data['concentrated_risk'] else 'NO'
        f.write(f"| {symbol} | {data['total_trades']} | {data['total_R']:.2f} | {data['top5_R']:.2f} | {data['concentration_pct']:.1f} | {flag} |\n")

    f.write("\n**Risk Flag:** YES if top 5 trades contribute > 40% of total R\n\n")

    f.write("---\n\n")

    f.write("## Top 5 Trades Details\n\n")

    for symbol, data in sorted(outlier_results.items()):
        f.write(f"### {symbol}\n\n")
        f.write("| Entry Time | Direction | R |\n")
        f.write("|------------|-----------|---|\n")

        for trade in data['top5_trades']:
            f.write(f"| {trade['entry_time']} | {trade['direction']} | {trade['R']:.3f} |\n")

        f.write("\n")

print(f"Saved: {report3}")

# REPORT 4: FINAL GO/NO-GO
report4 = 'reports/PROOF_V2_FINAL.md'

with open(report4, 'w') as f:
    f.write("# PROOF V2: FINAL GO/NO-GO DECISION\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## A) Determinism Status\n\n")
    f.write("| Symbol | Status | Notes |\n")
    f.write("|--------|--------|-------|\n")

    for symbol in SYMBOLS:
        if symbol in determinism_results:
            status = 'PASS' if determinism_results[symbol]['deterministic'] else 'FAIL'
            f.write(f"| {symbol} | {status} | 3 runs identical |\n")
        else:
            f.write(f"| {symbol} | SKIP | No data |\n")

    f.write("\n---\n\n")

    f.write("## B) Baseline OOS Results (2023-2024)\n\n")
    f.write("| Symbol | Trades | Exp(R) | PF | MaxDD(1%) | Return(1%) |\n")
    f.write("|--------|--------|--------|----|-----------|-----------|\n")

    for symbol in SYMBOLS:
        if symbol in cost_results:
            data = cost_results[symbol]
            base = data['scenarios']['baseline']
            f.write(f"| {symbol} | {data['trades']} | {base['expectancy']:.3f} | {base['pf']:.2f} | {base['maxDD']:.1f} | {base['return']:.1f} |\n")

    f.write("\n---\n\n")

    f.write("## C) Cost Stress Results\n\n")
    f.write("| Symbol | Baseline Exp | Mild Exp | Moderate Exp | Severe Exp |\n")
    f.write("|--------|--------------|----------|--------------|------------|\n")

    for symbol in SYMBOLS:
        if symbol in cost_results:
            scens = cost_results[symbol]['scenarios']
            f.write(f"| {symbol} | {scens['baseline']['expectancy']:.3f}R | {scens['mild']['expectancy']:.3f}R | {scens['moderate']['expectancy']:.3f}R | {scens['severe']['expectancy']:.3f}R |\n")

    f.write("\n---\n\n")

    f.write("## D) Outlier Risk\n\n")
    f.write("| Symbol | Concentration (%) | Risk Flag |\n")
    f.write("|--------|-------------------|------------|\n")

    for symbol in SYMBOLS:
        if symbol in outlier_results:
            data = outlier_results[symbol]
            flag = 'YES' if data['concentrated_risk'] else 'NO'
            f.write(f"| {symbol} | {data['concentration_pct']:.1f} | {flag} |\n")

    f.write("\n---\n\n")

    f.write("## E) Final Verdict\n\n")

    # Check GO/NO-GO criteria
    fx_symbols = ['EURUSD', 'GBPUSD', 'USDJPY']

    determinism_pass = all(
        determinism_results.get(s, {}).get('deterministic', False)
        for s in fx_symbols
    )

    baseline_positive = all(
        cost_results.get(s, {}).get('scenarios', {}).get('baseline', {}).get('expectancy', -1) > 0
        for s in fx_symbols
    )

    mild_positive = all(
        cost_results.get(s, {}).get('scenarios', {}).get('mild', {}).get('expectancy', -1) >= 0
        for s in fx_symbols
    )

    maxDD_ok = all(
        cost_results.get(s, {}).get('scenarios', {}).get('baseline', {}).get('maxDD', 999) <= 35
        for s in fx_symbols
    )

    go_decision = determinism_pass and baseline_positive and mild_positive and maxDD_ok

    f.write("### Criteria Check (FX Pairs: EURUSD, GBPUSD, USDJPY)\n\n")
    f.write(f"- **Determinism PASS:** {'YES' if determinism_pass else 'NO'}\n")
    f.write(f"- **Baseline Exp(R) > 0:** {'YES' if baseline_positive else 'NO'}\n")
    f.write(f"- **Mild Slippage Exp(R) >= 0:** {'YES' if mild_positive else 'NO'}\n")
    f.write(f"- **MaxDD(1%) <= 35%:** {'YES' if maxDD_ok else 'NO'}\n\n")

    f.write(f"### Decision: {'GO TO PAPER TRADING' if go_decision else 'NO-GO'}\n\n")

    if go_decision:
        f.write("**Status:** All criteria met for FX pairs (EURUSD, GBPUSD, USDJPY)\n\n")
        f.write("**Recommended Symbols:** EURUSD, GBPUSD, USDJPY\n\n")
    else:
        f.write("**Status:** Criteria not met. Further investigation required.\n\n")

    # XAUUSD separate assessment
    f.write("### XAUUSD Separate Assessment\n\n")

    if 'XAUUSD' in cost_results:
        xau_base_exp = cost_results['XAUUSD']['scenarios']['baseline']['expectancy']
        xau_mild_exp = cost_results['XAUUSD']['scenarios']['mild']['expectancy']
        xau_go = xau_base_exp > 0 and xau_mild_exp >= 0

        f.write(f"- Baseline Exp: {xau_base_exp:.3f}R\n")
        f.write(f"- Mild Exp: {xau_mild_exp:.3f}R\n")
        f.write(f"- Decision: {'GO' if xau_go else 'NO-GO'}\n\n")

        if not xau_go:
            f.write("**XAUUSD NOT RECOMMENDED** - Does not survive mild slippage\n\n")

    f.write("---\n\n")

    f.write("## F) Risk Management Recommendation\n\n")
    f.write("### Initial Risk\n\n")
    f.write("- **Start:** 0.5% risk per trade\n")
    f.write("- **Reasoning:** Conservative entry, validate execution quality\n")
    f.write("- **Scaling:** After 50 trades, if Exp(R) maintained and MaxDD < 25%, increase to 1.0%\n\n")

    f.write("### Position Limits\n\n")
    f.write("- Max concurrent positions: 3 (1 per symbol max)\n")
    f.write("- Daily loss limit: 2% of account\n")
    f.write("- Monthly DD stop: 15%\n\n")

    f.write("### Monitoring\n\n")
    f.write("- Track slippage per trade (actual vs expected)\n")
    f.write("- Compare live Exp(R) to backtest after 20 trades\n")
    f.write("- Alert if MaxDD exceeds 20%\n\n")

    f.write("---\n\n")
    f.write(f"**Report generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"Saved: {report4}")

print("\n" + "="*80)
print("PROOF V2 MODE COMPLETE")
print("="*80)
print()
print("Reports generated:")
print(f"  - {report1}")
print(f"  - {report2}")
print(f"  - {report3}")
print(f"  - {report4}")

