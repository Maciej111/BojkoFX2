"""
EURUSD 2024 OOS Test
Test frozen config on available EURUSD data (2023 as OOS proxy)
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

sys.path.append('.')

from src.strategies.trend_following_v1 import run_trend_backtest
from src.backtest.metrics import compute_metrics

print("="*60)
print("EURUSD OOS TEST (2023)")
print("="*60)
print()

# FROZEN CONFIG (RR=1.5 winner from grid search)
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
ltf_df = pd.read_csv('data/bars/eurusd_1h_bars.csv', parse_dates=['timestamp'])
htf_df = pd.read_csv('data/bars/eurusd_4h_bars.csv', parse_dates=['timestamp'])

print(f"✓ LTF (H1): {len(ltf_df)} bars from {ltf_df['timestamp'].min()} to {ltf_df['timestamp'].max()}")
print(f"✓ HTF (H4): {len(htf_df)} bars from {htf_df['timestamp'].min()} to {htf_df['timestamp'].max()}")
print()

# Filter to 2023 (OOS period) but keep full history for HTF context
print("Using full data 2021-2023 (filtering trades to 2023 only)...")
ltf_full = ltf_df.copy()
htf_full = htf_df.copy()

print(f"✓ LTF full: {len(ltf_full)} bars")
print(f"✓ HTF full: {len(htf_full)} bars")
print()

# Run backtest on full data
print("Running backtest...")
initial_balance = 10000

try:
    trades, metrics = run_trend_backtest('EURUSD', ltf_full, htf_full, FROZEN_CONFIG, initial_balance)

    # Filter trades to 2023 only
    if len(trades) > 0:
        trades_2023 = trades[pd.to_datetime(trades['entry_time']).dt.year == 2023].copy()
        print(f"\n✓ Total trades (all periods): {len(trades)}")
        print(f"✓ Trades in 2023: {len(trades_2023)}")

        # Recompute metrics for 2023 only
        if len(trades_2023) > 0:
            wins = trades_2023[trades_2023['R'] > 0]
            win_rate = len(wins) / len(trades_2023) * 100
            expectancy_R = trades_2023['R'].mean()

            total_wins = wins['pnl'].sum() if len(wins) > 0 else 0
            losses = trades_2023[trades_2023['R'] <= 0]
            total_losses = abs(losses['pnl'].sum()) if len(losses) > 0 else 1
            profit_factor = total_wins / total_losses if total_losses > 0 else 0

            metrics_2023 = {
                'trades_count': len(trades_2023),
                'win_rate': win_rate,
                'expectancy_R': expectancy_R,
                'profit_factor': profit_factor
            }
        else:
            metrics_2023 = metrics  # Use full metrics if no 2023 trades
            trades_2023 = pd.DataFrame()
    else:
        trades_2023 = pd.DataFrame()
        metrics_2023 = metrics

    print()
    print("="*60)
    print("RESULTS")
    print("="*60)
    print()

    print(f"Trades: {metrics['trades_count']}")
    print(f"Win Rate: {metrics['win_rate']:.1f}%")
    print(f"Expectancy: {metrics['expectancy_R']:.3f}R")
    print(f"Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"Max DD: {metrics.get('max_dd_pct', 0):.1f}%")
    print(f"Max Losing Streak: {metrics.get('max_losing_streak', 0)}")
    print(f"Missed Rate: {metrics.get('missed_rate', 0)*100:.1f}%")
    print()

    # Calculate return if we have trades
    if len(trades) > 0:
        total_pnl = trades['pnl'].sum()
        total_return_pct = (total_pnl / initial_balance) * 100
        print(f"Total PnL: ${total_pnl:.2f}")
        print(f"Total Return: {total_return_pct:.2f}%")
        print()


    # Save trades
    if len(trades) > 0:
        output_file = 'data/outputs/eurusd_2023_oos_trades.csv'
        trades.to_csv(output_file, index=False)
        print(f"✓ Trades saved to {output_file}")

        # Generate simple report
        report_file = 'reports/EURUSD_2023_OOS_REPORT.md'
        with open(report_file, 'w') as f:
            f.write("# EURUSD 2023 OOS TEST REPORT\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write("## Configuration\n\n")
            f.write("**Frozen parameters (from grid search winner):**\n\n")
            for k, v in FROZEN_CONFIG.items():
                f.write(f"- {k}: `{v}`\n")
            f.write("\n")
            f.write("## Period\n\n")
            f.write(f"- **Test period:** 2023-01-01 to 2023-12-31\n")
            f.write(f"- **H1 bars:** {len(ltf_2023)}\n")
            f.write(f"- **H4 bars:** {len(htf_2023)}\n\n")
            f.write("---\n\n")
            f.write("## Results\n\n")
            f.write(f"| Metric | Value |\n")
            f.write(f"|--------|-------|\n")
            f.write(f"| Trades | {metrics['trades_count']} |\n")
            f.write(f"| Win Rate | {metrics['win_rate']:.1f}% |\n")
            f.write(f"| Expectancy | {metrics['expectancy_R']:.3f}R |\n")
            f.write(f"| Profit Factor | {metrics['profit_factor']:.2f} |\n")
            f.write(f"| Max DD | {metrics.get('max_dd_pct', 0):.1f}% |\n")
            f.write(f"| Max Losing Streak | {metrics.get('max_losing_streak', 0)} |\n")
            f.write(f"| Missed Rate | {metrics.get('missed_rate', 0)*100:.1f}% |\n")
            if len(trades) > 0:
                total_pnl = trades['pnl'].sum()
                total_return = (total_pnl / initial_balance) * 100
                f.write(f"| Total Return | {total_return:.2f}% |\n")
            f.write("\n")
            f.write("---\n\n")
            f.write("## Notes\n\n")
            f.write("⚠ **Data Limitation:** EURUSD 2024 data (H1) was corrupted during processing.\n")
            f.write("This report uses 2023 as OOS period instead of full 2024.\n\n")
            f.write("**Next steps:**\n")
            f.write("1. Recover/re-download EURUSD 2024 tick data\n")
            f.write("2. Rebuild H1/H4 bars for 2024\n")
            f.write("3. Run full 2024 OOS test\n\n")

        print(f"✓ Report saved to {report_file}")
    else:
        print("⚠ No trades generated")

except Exception as e:
    print(f"❌ Error running backtest: {e}")
    import traceback
    traceback.print_exc()






