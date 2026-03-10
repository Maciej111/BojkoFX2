"""
EURUSD 2024 FULL OOS TEST
Using frozen config from grid search winner (RR=1.5)
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest

print("="*60)
print("EURUSD 2024 FULL OOS TEST")
print("="*60)
print()

# FROZEN CONFIG (RR=1.5 winner)
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

print("FROZEN CONFIGURATION:")
for k, v in FROZEN_CONFIG.items():
    print(f"  {k}: {v}")
print()

# Load bars
print("Loading bars...")
try:
    ltf_df = pd.read_csv('data/bars/eurusd_1h_bars.csv', parse_dates=['timestamp'])
    htf_df = pd.read_csv('data/bars/eurusd_4h_bars.csv', parse_dates=['timestamp'])

    print(f"✓ LTF (H1): {len(ltf_df)} bars")
    print(f"  Period: {ltf_df['timestamp'].min()} to {ltf_df['timestamp'].max()}")
    print(f"✓ HTF (H4): {len(htf_df)} bars")
    print(f"  Period: {htf_df['timestamp'].min()} to {htf_df['timestamp'].max()}")
    print()

except Exception as e:
    print(f"❌ Error loading bars: {e}")
    exit(1)

# Filter to 2024
print("Filtering to 2024...")
ltf_2024 = ltf_df[ltf_df['timestamp'].dt.year == 2024].copy()
htf_2024 = htf_df[htf_df['timestamp'].dt.year == 2024].copy()

print(f"✓ LTF 2024: {len(ltf_2024)} bars")
print(f"✓ HTF 2024: {len(htf_2024)} bars")
print()

# Need historical context for HTF bias - use all data
print("Running backtest (with full historical context)...")
initial_balance = 10000

try:
    # Run on full data
    trades_full, metrics_full = run_trend_backtest('EURUSD', ltf_df, htf_df, FROZEN_CONFIG, initial_balance)

    # Filter trades to 2024
    if len(trades_full) > 0:
        trades_2024 = trades_full[pd.to_datetime(trades_full['entry_time']).dt.year == 2024].copy()

        print(f"\n✓ Total trades (all periods): {len(trades_full)}")
        print(f"✓ Trades in 2024: {len(trades_2024)}")
        print()

        if len(trades_2024) > 0:
            # Compute 2024 metrics
            wins = trades_2024[trades_2024['R'] > 0]
            losses = trades_2024[trades_2024['R'] <= 0]

            win_rate = len(wins) / len(trades_2024) * 100
            expectancy_R = trades_2024['R'].mean()

            total_wins = wins['pnl'].sum() if len(wins) > 0 else 0
            total_losses = abs(losses['pnl'].sum()) if len(losses) > 0 else 1
            profit_factor = total_wins / total_losses if total_losses > 0 else 0

            total_pnl = trades_2024['pnl'].sum()
            total_return = (total_pnl / initial_balance) * 100

            # Max DD for 2024
            equity_curve = [initial_balance]
            for pnl in trades_2024['pnl']:
                equity_curve.append(equity_curve[-1] + pnl)

            peak = equity_curve[0]
            max_dd = 0
            for val in equity_curve:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak * 100
                if dd > max_dd:
                    max_dd = dd

            # Max losing streak
            streak = 0
            max_streak = 0
            for pnl in trades_2024['pnl']:
                if pnl <= 0:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 0

            print("="*60)
            print("RESULTS - 2024 OOS")
            print("="*60)
            print()
            print(f"Trades: {len(trades_2024)}")
            print(f"Win Rate: {win_rate:.1f}%")
            print(f"Expectancy: {expectancy_R:.3f}R")
            print(f"Profit Factor: {profit_factor:.2f}")
            print(f"Max DD: {max_dd:.1f}%")
            print(f"Max Losing Streak: {max_streak}")
            print(f"Total PnL: ${total_pnl:.2f}")
            print(f"Total Return: {total_return:.2f}%")
            print()

            # Save trades
            output_file = 'data/outputs/eurusd_2024_oos_trades.csv'
            trades_2024.to_csv(output_file, index=False)
            print(f"✓ Trades saved to {output_file}")

            # Generate report
            report_file = 'reports/EURUSD_2024_FULL_OOS_REPORT.md'
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("# EURUSD 2024 FULL OOS TEST REPORT\n\n")
                f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")
                f.write("## Configuration\n\n")
                f.write("**Frozen parameters (from grid search winner):**\n\n")
                for k, v in FROZEN_CONFIG.items():
                    f.write(f"- {k}: `{v}`\n")
                f.write("\n")
                f.write("## Period\n\n")
                f.write(f"- **Test period:** 2024-01-01 to 2024-12-31\n")
                f.write(f"- **H1 bars:** {len(ltf_2024)}\n")
                f.write(f"- **H4 bars:** {len(htf_2024)}\n")
                f.write(f"- **Full history used for HTF context:** Yes\n\n")
                f.write("---\n\n")
                f.write("## Results\n\n")
                f.write(f"| Metric | Value |\n")
                f.write(f"|--------|-------|\n")
                f.write(f"| Trades | {len(trades_2024)} |\n")
                f.write(f"| Win Rate | {win_rate:.1f}% |\n")
                f.write(f"| Expectancy | {expectancy_R:.3f}R |\n")
                f.write(f"| Profit Factor | {profit_factor:.2f} |\n")
                f.write(f"| Max DD | {max_dd:.1f}% |\n")
                f.write(f"| Max Losing Streak | {max_streak} |\n")
                f.write(f"| Total Return | {total_return:.2f}% |\n\n")
                f.write("---\n\n")
                f.write("## Comparison vs Previous Tests\n\n")
                f.write("**Note:** This is the first complete 2024 test with full year data.\n\n")
                f.write("**Key Findings:**\n\n")
                if expectancy_R > 0:
                    f.write(f"✅ **Positive expectancy:** {expectancy_R:.3f}R suggests strategy has edge in 2024\n\n")
                else:
                    f.write(f"⚠ **Negative expectancy:** {expectancy_R:.3f}R - strategy struggled in 2024\n\n")

                if win_rate >= 33.3:
                    f.write(f"✅ **Win rate above RR2 breakeven:** {win_rate:.1f}% (needed: 33.3%)\n\n")
                else:
                    f.write(f"⚠ **Win rate below breakeven:** {win_rate:.1f}% (needed: 33.3% for RR1.5)\n\n")

                f.write("---\n\n")
                f.write(f"**Report generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            print(f"✓ Report saved to {report_file}")
            print()
            print("="*60)
            print("✅ OOS TEST COMPLETE")
            print("="*60)

        else:
            print("⚠ No trades in 2024")
    else:
        print("⚠ No trades generated")

except Exception as e:
    print(f"❌ Error running backtest: {e}")
    import traceback
    traceback.print_exc()

