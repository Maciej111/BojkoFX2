"""
FINAL PROOF MODE - Complete Verification
Steps 1-4: Recompute, Determinism, Slippage, Edge Survival
"""

import pandas as pd
import numpy as np
import sys
import os
import hashlib
from datetime import datetime

sys.path.append('.')
from src.strategies.trend_following_v1 import run_trend_backtest

print("="*80)
print("FINAL PROOF MODE")
print("="*80)
print()

SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
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

# Reference from FULL_SYSTEM_REVALIDATION
REFERENCE_METRICS = {
    'EURUSD': {'expectancy': 0.212, 'pf': 1.03, 'trades': 234},
    'GBPUSD': {'expectancy': 0.572, 'pf': 1.71, 'trades': 200},
    'USDJPY': {'expectancy': 0.300, 'pf': 1.14, 'trades': 225},
    'XAUUSD': {'expectancy': 0.178, 'pf': 1.22, 'trades': 220}
}

# ========================================================
# STEP 1: RECOMPUTE METRICS FROM RAW TRADES
# ========================================================

print("="*80)
print("STEP 1: RECOMPUTE METRICS FROM RAW TRADES")
print("="*80)
print()

recompute_results = {}

for symbol in SYMBOLS:
    print(f"Recomputing {symbol}...")

    trades_file = f'data/outputs/trades_OOS_{symbol}_2023_2024.csv'

    if not os.path.exists(trades_file):
        print(f"  [SKIP] No trades file")
        continue

    df = pd.read_csv(trades_file)

    # Recompute metrics
    trades_count = len(df)

    wins = df[df['R'] > 0]
    losses = df[df['R'] <= 0]

    win_rate = len(wins) / len(df) * 100 if len(df) > 0 else 0
    avg_win_R = wins['R'].mean() if len(wins) > 0 else 0
    avg_loss_R = losses['R'].mean() if len(losses) > 0 else 0
    expectancy_R = df['R'].mean()

    gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Compare with reference
    ref = REFERENCE_METRICS[symbol]

    exp_diff = abs(expectancy_R - ref['expectancy'])
    pf_diff = abs(profit_factor - ref['pf'])
    trades_diff = abs(trades_count - ref['trades'])

    exp_match = exp_diff <= 0.001
    pf_match = pf_diff <= 0.01
    trades_match = trades_diff == 0

    recompute_results[symbol] = {
        'trades_count': trades_count,
        'win_rate': win_rate,
        'avg_win_R': avg_win_R,
        'avg_loss_R': avg_loss_R,
        'expectancy_R': expectancy_R,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor,
        'ref_expectancy': ref['expectancy'],
        'ref_pf': ref['pf'],
        'ref_trades': ref['trades'],
        'exp_diff': exp_diff,
        'pf_diff': pf_diff,
        'trades_diff': trades_diff,
        'exp_match': exp_match,
        'pf_match': pf_match,
        'trades_match': trades_match
    }

    print(f"  Trades: {trades_count} (ref: {ref['trades']}) {'PASS' if trades_match else 'FAIL'}")
    print(f"  Expectancy: {expectancy_R:.3f}R (ref: {ref['expectancy']:.3f}R) diff: {exp_diff:.4f} {'PASS' if exp_match else 'FAIL'}")
    print(f"  PF: {profit_factor:.2f} (ref: {ref['pf']:.2f}) diff: {pf_diff:.3f} {'PASS' if pf_match else 'FAIL'}")
    print()

# ========================================================
# STEP 2: EXTENDED DETERMINISM CHECK
# ========================================================

print("="*80)
print("STEP 2: EXTENDED DETERMINISM CHECK")
print("="*80)
print()

determinism_results = {}

for symbol in ['EURUSD', 'XAUUSD']:
    print(f"Testing determinism for {symbol}...")

    ltf_file = f'data/bars_validated/{symbol.lower()}_1h_validated.csv'
    htf_file = f'data/bars_validated/{symbol.lower()}_4h_validated.csv'

    ltf_df = pd.read_csv(ltf_file, parse_dates=['timestamp'])
    htf_df = pd.read_csv(htf_file, parse_dates=['timestamp'])

    # Run 1
    trades_run1, _ = run_trend_backtest(symbol, ltf_df, htf_df, FROZEN_CONFIG, 10000)
    trades_run1['entry_time'] = pd.to_datetime(trades_run1['entry_time'])
    trades_run1['year'] = trades_run1['entry_time'].dt.year
    trades_oos1 = trades_run1[trades_run1['year'].isin([2023, 2024])].copy()

    # Run 2
    trades_run2, _ = run_trend_backtest(symbol, ltf_df, htf_df, FROZEN_CONFIG, 10000)
    trades_run2['entry_time'] = pd.to_datetime(trades_run2['entry_time'])
    trades_run2['year'] = trades_run2['entry_time'].dt.year
    trades_oos2 = trades_run2[trades_run2['year'].isin([2023, 2024])].copy()

    # Compare
    count_match = len(trades_oos1) == len(trades_oos2)

    if count_match:
        hash1 = hashlib.md5(pd.util.hash_pandas_object(trades_oos1[['entry_time', 'direction', 'R']], index=False).values).hexdigest()
        hash2 = hashlib.md5(pd.util.hash_pandas_object(trades_oos2[['entry_time', 'direction', 'R']], index=False).values).hexdigest()

        hash_match = (hash1 == hash2)

        exp1 = trades_oos1['R'].mean()
        exp2 = trades_oos2['R'].mean()
        exp_match = abs(exp1 - exp2) < 1e-10

        wins1 = trades_oos1[trades_oos1['R'] > 0]
        losses1 = trades_oos1[trades_oos1['R'] <= 0]
        pf1 = wins1['pnl'].sum() / abs(losses1['pnl'].sum()) if len(losses1) > 0 else 0

        wins2 = trades_oos2[trades_oos2['R'] > 0]
        losses2 = trades_oos2[trades_oos2['R'] <= 0]
        pf2 = wins2['pnl'].sum() / abs(losses2['pnl'].sum()) if len(losses2) > 0 else 0

        pf_match = abs(pf1 - pf2) < 0.001
    else:
        hash_match = False
        exp_match = False
        pf_match = False
        hash1 = hash2 = "N/A"
        exp1 = exp2 = pf1 = pf2 = 0

    deterministic = count_match and hash_match and exp_match and pf_match

    determinism_results[symbol] = {
        'run1_trades': len(trades_oos1),
        'run2_trades': len(trades_oos2),
        'count_match': count_match,
        'hash1': hash1[:8] if hash1 != "N/A" else "N/A",
        'hash2': hash2[:8] if hash2 != "N/A" else "N/A",
        'hash_match': hash_match,
        'exp1': exp1,
        'exp2': exp2,
        'exp_match': exp_match,
        'pf1': pf1,
        'pf2': pf2,
        'pf_match': pf_match,
        'deterministic': deterministic
    }

    print(f"  Run 1: {len(trades_oos1)} trades, hash: {hash1[:8] if hash1 != 'N/A' else 'N/A'}")
    print(f"  Run 2: {len(trades_oos2)} trades, hash: {hash2[:8] if hash2 != 'N/A' else 'N/A'}")
    print(f"  Deterministic: {'PASS' if deterministic else 'FAIL'}")
    print()

# ========================================================
# STEP 3 & 4: SLIPPAGE STRESS TEST + EDGE SURVIVAL
# ========================================================

print("="*80)
print("STEPS 3 & 4: SLIPPAGE STRESS TEST + EDGE SURVIVAL")
print("="*80)
print()

slippage_results = {}

# Pip values for FX pairs (approximate)
PIP_VALUES = {
    'EURUSD': 0.0001,
    'GBPUSD': 0.0001,
    'USDJPY': 0.01,
    'XAUUSD': 1.0  # Will use R-based penalty instead
}

for symbol in SYMBOLS:
    print(f"Testing slippage impact on {symbol}...")

    trades_file = f'data/outputs/trades_OOS_{symbol}_2023_2024.csv'

    if not os.path.exists(trades_file):
        print(f"  [SKIP] No trades file")
        continue

    df = pd.read_csv(trades_file)

    # Calculate risk_distance for pip conversion
    # For R-based slippage, we need to convert pips to R
    # Assuming risk_distance is available or can be estimated from entry/sl

    if 'risk_distance' in df.columns:
        avg_risk = df['risk_distance'].mean()
    else:
        # Estimate from pnl and R
        # risk_distance ≈ pnl / R (but this is circular)
        # Use typical values
        avg_risk = 0.0050 if symbol in ['EURUSD', 'GBPUSD'] else (0.5 if symbol == 'USDJPY' else 5.0)

    # BASE SCENARIO
    base_exp = df['R'].mean()
    base_wins = df[df['R'] > 0]
    base_losses = df[df['R'] <= 0]
    base_pf = base_wins['pnl'].sum() / abs(base_losses['pnl'].sum()) if len(base_losses) > 0 else 0

    # MILD SLIPPAGE
    if symbol == 'XAUUSD':
        # 0.5R penalty per trade
        mild_penalty_R = 0.5
    else:
        # 1 pip
        pip_value = PIP_VALUES[symbol]
        mild_penalty_R = pip_value / avg_risk

    df_mild = df.copy()
    df_mild['R_adjusted'] = df_mild['R'] - mild_penalty_R

    mild_exp = df_mild['R_adjusted'].mean()
    mild_wins = df_mild[df_mild['R_adjusted'] > 0]
    mild_losses = df_mild[df_mild['R_adjusted'] <= 0]

    # Recalc PNL
    df_mild['pnl_adjusted'] = df_mild['R_adjusted'] * avg_risk * 10000  # Approximate
    mild_wins_pnl = df_mild[df_mild['R_adjusted'] > 0]
    mild_losses_pnl = df_mild[df_mild['R_adjusted'] <= 0]
    mild_pf = mild_wins_pnl['pnl_adjusted'].sum() / abs(mild_losses_pnl['pnl_adjusted'].sum()) if len(mild_losses_pnl) > 0 else 0

    # Realistic return with 1% risk
    equity_mild = 10000
    for r in df_mild['R_adjusted']:
        equity_mild *= (1 + r * 0.01)
    mild_return = ((equity_mild - 10000) / 10000) * 100

    # MaxDD
    equity_curve_mild = [10000]
    equity_temp = 10000
    for r in df_mild['R_adjusted']:
        equity_temp *= (1 + r * 0.01)
        equity_curve_mild.append(equity_temp)

    peak_mild = equity_curve_mild[0]
    mild_maxDD = 0
    for val in equity_curve_mild:
        if val > peak_mild:
            peak_mild = val
        dd = (peak_mild - val) / peak_mild * 100
        if dd > mild_maxDD:
            mild_maxDD = dd

    # SEVERE SLIPPAGE
    if symbol == 'XAUUSD':
        # 1.0R penalty per trade
        severe_penalty_R = 1.0
    else:
        # 2 pips
        pip_value = PIP_VALUES[symbol]
        severe_penalty_R = 2 * pip_value / avg_risk

    df_severe = df.copy()
    df_severe['R_adjusted'] = df_severe['R'] - severe_penalty_R

    severe_exp = df_severe['R_adjusted'].mean()
    severe_wins = df_severe[df_severe['R_adjusted'] > 0]
    severe_losses = df_severe[df_severe['R_adjusted'] <= 0]

    df_severe['pnl_adjusted'] = df_severe['R_adjusted'] * avg_risk * 10000
    severe_wins_pnl = df_severe[df_severe['R_adjusted'] > 0]
    severe_losses_pnl = df_severe[df_severe['R_adjusted'] <= 0]
    severe_pf = severe_wins_pnl['pnl_adjusted'].sum() / abs(severe_losses_pnl['pnl_adjusted'].sum()) if len(severe_losses_pnl) > 0 else 0

    # Realistic return
    equity_severe = 10000
    for r in df_severe['R_adjusted']:
        equity_severe *= (1 + r * 0.01)
    severe_return = ((equity_severe - 10000) / 10000) * 100

    # MaxDD
    equity_curve_severe = [10000]
    equity_temp = 10000
    for r in df_severe['R_adjusted']:
        equity_temp *= (1 + r * 0.01)
        equity_curve_severe.append(equity_temp)

    peak_severe = equity_curve_severe[0]
    severe_maxDD = 0
    for val in equity_curve_severe:
        if val > peak_severe:
            peak_severe = val
        dd = (peak_severe - val) / peak_severe * 100
        if dd > severe_maxDD:
            severe_maxDD = dd

    # SURVIVAL CHECK
    survives_mild = mild_exp > 0
    survives_severe = severe_exp > 0

    slippage_results[symbol] = {
        'base_exp': base_exp,
        'base_pf': base_pf,
        'mild_penalty_R': mild_penalty_R,
        'mild_exp': mild_exp,
        'mild_pf': mild_pf,
        'mild_return': mild_return,
        'mild_maxDD': mild_maxDD,
        'survives_mild': survives_mild,
        'severe_penalty_R': severe_penalty_R,
        'severe_exp': severe_exp,
        'severe_pf': severe_pf,
        'severe_return': severe_return,
        'severe_maxDD': severe_maxDD,
        'survives_severe': survives_severe
    }

    print(f"  Base: Exp={base_exp:.3f}R, PF={base_pf:.2f}")
    print(f"  Mild (-{mild_penalty_R:.3f}R): Exp={mild_exp:.3f}R, PF={mild_pf:.2f}, Return={mild_return:.1f}%, MaxDD={mild_maxDD:.1f}% {'SURVIVES' if survives_mild else 'FAILS'}")
    print(f"  Severe (-{severe_penalty_R:.3f}R): Exp={severe_exp:.3f}R, PF={severe_pf:.2f}, Return={severe_return:.1f}%, MaxDD={severe_maxDD:.1f}% {'SURVIVES' if survives_severe else 'FAILS'}")
    print()

# ========================================================
# GENERATE REPORTS
# ========================================================

print("="*80)
print("GENERATING REPORTS")
print("="*80)
print()

# STEP 1 REPORT
report1 = 'reports/PROOF_RECOMPUTE_CHECK.md'

with open(report1, 'w') as f:
    f.write("# PROOF: RECOMPUTE METRICS CHECK\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## Recomputed Metrics vs Reference\n\n")
    f.write("| Symbol | Trades | Expectancy (R) | PF | Ref Exp | Ref PF | Exp Diff | Match |\n")
    f.write("|--------|--------|----------------|----|---------|---------|-----------|-----------|\n")

    for symbol, data in sorted(recompute_results.items()):
        match_status = 'PASS' if data['exp_match'] and data['pf_match'] and data['trades_match'] else 'FAIL'
        f.write(f"| {symbol} | {data['trades_count']} | {data['expectancy_R']:.3f} | {data['profit_factor']:.2f} | {data['ref_expectancy']:.3f} | {data['ref_pf']:.2f} | {data['exp_diff']:.4f} | {match_status} |\n")

    f.write("\n---\n\n")
    f.write("## Verdict\n\n")

    all_pass = all(d['exp_match'] and d['pf_match'] and d['trades_match'] for d in recompute_results.values())
    f.write(f"**Recompute Check:** {'PASS' if all_pass else 'FAIL'}\n\n")

    if all_pass:
        f.write("All metrics match within tolerance (0.001R for expectancy).\n\n")
    else:
        f.write("Some metrics exceed tolerance.\n\n")

print(f"Saved: {report1}")

# STEP 2 REPORT
report2 = 'reports/PROOF_DETERMINISM_EXTENDED.md'

with open(report2, 'w') as f:
    f.write("# PROOF: EXTENDED DETERMINISM CHECK\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## Determinism Test Results\n\n")
    f.write("| Symbol | Run 1 Trades | Run 2 Trades | Hash Match | Exp Match | PF Match | Deterministic |\n")
    f.write("|--------|--------------|--------------|------------|-----------|----------|---------------|\n")

    for symbol, data in sorted(determinism_results.items()):
        f.write(f"| {symbol} | {data['run1_trades']} | {data['run2_trades']} | {'PASS' if data['hash_match'] else 'FAIL'} | {'PASS' if data['exp_match'] else 'FAIL'} | {'PASS' if data['pf_match'] else 'FAIL'} | {'PASS' if data['deterministic'] else 'FAIL'} |\n")

    f.write("\n---\n\n")
    f.write("## Verdict\n\n")

    all_deterministic = all(d['deterministic'] for d in determinism_results.values())
    f.write(f"**Determinism:** {'PASS' if all_deterministic else 'FAIL'}\n\n")

print(f"Saved: {report2}")

# FINAL PROOF REPORT
report_final = 'reports/FINAL_PROOF_REPORT.md'

with open(report_final, 'w') as f:
    f.write("# FINAL PROOF REPORT\n\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("---\n\n")

    f.write("## SLIPPAGE STRESS TEST\n\n")
    f.write("| Symbol | Base Exp | Mild Exp | Severe Exp | Survives Mild | Survives Severe |\n")
    f.write("|--------|----------|----------|------------|---------------|------------------|\n")

    for symbol, data in sorted(slippage_results.items()):
        f.write(f"| {symbol} | {data['base_exp']:.3f}R | {data['mild_exp']:.3f}R | {data['severe_exp']:.3f}R | {'PASS' if data['survives_mild'] else 'FAIL'} | {'PASS' if data['survives_severe'] else 'FAIL'} |\n")

    f.write("\n### Slippage Penalties Applied\n\n")
    f.write("| Symbol | Mild Penalty | Severe Penalty |\n")
    f.write("|--------|--------------|----------------|\n")

    for symbol, data in sorted(slippage_results.items()):
        f.write(f"| {symbol} | {data['mild_penalty_R']:.3f}R | {data['severe_penalty_R']:.3f}R |\n")

    f.write("\n### Performance Under Slippage (1% Risk)\n\n")
    f.write("| Symbol | Scenario | Expectancy | PF | Return (%) | MaxDD (%) |\n")
    f.write("|--------|----------|------------|----|-----------|-----------|\n")

    for symbol, data in sorted(slippage_results.items()):
        f.write(f"| {symbol} | Base | {data['base_exp']:.3f}R | {data['base_pf']:.2f} | - | - |\n")
        f.write(f"| {symbol} | Mild | {data['mild_exp']:.3f}R | {data['mild_pf']:.2f} | {data['mild_return']:.1f} | {data['mild_maxDD']:.1f} |\n")
        f.write(f"| {symbol} | Severe | {data['severe_exp']:.3f}R | {data['severe_pf']:.2f} | {data['severe_return']:.1f} | {data['severe_maxDD']:.1f} |\n")

    f.write("\n---\n\n")
    f.write("## EDGE SURVIVAL SUMMARY\n\n")

    mild_survivors = sum(1 for d in slippage_results.values() if d['survives_mild'])
    severe_survivors = sum(1 for d in slippage_results.values() if d['survives_severe'])
    total_symbols = len(slippage_results)

    f.write(f"**Mild Slippage Survivors:** {mild_survivors}/{total_symbols}\n\n")
    f.write(f"**Severe Slippage Survivors:** {severe_survivors}/{total_symbols}\n\n")

    f.write("### Impact on Expectancy\n\n")
    f.write("| Symbol | Base to Mild | Mild to Severe | Base to Severe |\n")
    f.write("|--------|--------------|----------------|----------------|\n")

    for symbol, data in sorted(slippage_results.items()):
        delta_mild = data['mild_exp'] - data['base_exp']
        delta_severe = data['severe_exp'] - data['mild_exp']
        delta_total = data['severe_exp'] - data['base_exp']
        f.write(f"| {symbol} | {delta_mild:+.3f}R | {delta_severe:+.3f}R | {delta_total:+.3f}R |\n")

    f.write("\n---\n\n")
    f.write("## PROFIT FACTOR UNDER SLIPPAGE\n\n")
    f.write("| Symbol | Base PF | Mild PF | Severe PF | Mild PF>1 | Severe PF>1 |\n")
    f.write("|--------|---------|---------|-----------|-----------|-------------|\n")

    for symbol, data in sorted(slippage_results.items()):
        mild_pf_ok = data['mild_pf'] > 1.0
        severe_pf_ok = data['severe_pf'] > 1.0
        f.write(f"| {symbol} | {data['base_pf']:.2f} | {data['mild_pf']:.2f} | {data['severe_pf']:.2f} | {'PASS' if mild_pf_ok else 'FAIL'} | {'PASS' if severe_pf_ok else 'FAIL'} |\n")

    f.write("\n---\n\n")
    f.write("## REALISTIC RETURNS (1% Risk Per Trade)\n\n")
    f.write("| Symbol | Mild Return | Mild MaxDD | Severe Return | Severe MaxDD | Mild Positive | Severe Positive |\n")
    f.write("|--------|-------------|------------|---------------|--------------|---------------|------------------|\n")

    for symbol, data in sorted(slippage_results.items()):
        mild_return_ok = data['mild_return'] > 0
        severe_return_ok = data['severe_return'] > 0
        f.write(f"| {symbol} | {data['mild_return']:.1f}% | {data['mild_maxDD']:.1f}% | {data['severe_return']:.1f}% | {data['severe_maxDD']:.1f}% | {'PASS' if mild_return_ok else 'FAIL'} | {'PASS' if severe_return_ok else 'FAIL'} |\n")

    f.write("\n---\n\n")
    f.write("## FINAL VERDICT\n\n")

    f.write(f"**Recompute Check:** {'PASS' if all(d['exp_match'] and d['pf_match'] and d['trades_match'] for d in recompute_results.values()) else 'FAIL'}\n\n")
    f.write(f"**Determinism Check:** {'PASS' if all(d['deterministic'] for d in determinism_results.values()) else 'FAIL'}\n\n")
    f.write(f"**Mild Slippage Survival:** {mild_survivors}/{total_symbols} symbols {'PASS' if mild_survivors >= 3 else 'FAIL'}\n\n")
    f.write(f"**Severe Slippage Survival:** {severe_survivors}/{total_symbols} symbols {'PASS' if severe_survivors >= 2 else 'FAIL'}\n\n")

    f.write("---\n\n")
    f.write(f"**Report generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

print(f"Saved: {report_final}")

print()
print("="*80)
print("FINAL PROOF MODE COMPLETE")
print("="*80)
print()
print("Reports generated:")
print(f"  - {report1}")
print(f"  - {report2}")
print(f"  - {report_final}")


