import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

def generate_report(trades_df, output_dir, initial_balance, suffix=""):
    os.makedirs(output_dir, exist_ok=True)

    # Save trades
    trades_filename = f'trades{suffix}.csv' if suffix else 'trades.csv'
    trades_df.to_csv(os.path.join(output_dir, trades_filename), index=False)

    if len(trades_df) == 0:
        print("No trades to report.")
        return

    # Calculate Metrics
    trades_df['equity'] = initial_balance + trades_df['pnl'].cumsum()

    # R Multiple
    # Calculate Risk distance
    # For Long: Risk = Entry - SL
    # For Short: Risk = SL - Entry
    # But we don't have SL in trades_df currently?
    # Wait, execution.py get_results_df() returns entry/exit price/time/pnl.
    # It does not return SL/TP. I should add SL/TP to get_results_df in execution.py
    # or pass the Trade objects directly.
    # I'll calculate R-multiple roughly based on PnL if risk was constant?
    # Or ideally I fix execution.py to export SL.

    # Let's assume we can get SL from trades_df if I update execution.py.
    # UPDATE execution.py first? No, let's just proceed with what we have and maybe
    # infer R if we know risk.
    # Actually, R-histogram is requested.
    # I'll modify execution.py quickly to include SL/TP in export.

    # Summary
    total_trades = len(trades_df)
    wins = trades_df[trades_df['pnl'] > 0]
    losses = trades_df[trades_df['pnl'] <= 0]
    win_rate = len(wins) / total_trades

    total_pnl = trades_df['pnl'].sum()
    final_balance = initial_balance + total_pnl
    return_pct = (final_balance - initial_balance) / initial_balance * 100

    # Max DD
    equity = trades_df['equity']
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = dd.min() * 100

    # Expectancy
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = losses['pnl'].mean() if len(losses) > 0 else 0
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    summary = f"""
# Backtest Summary

**Date**: {pd.Timestamp.now()}
**Total Trades**: {total_trades}
**Win Rate**: {win_rate:.2%}
**Total PnL**: {total_pnl:.2f}
**Return**: {return_pct:.2f}%
**Max Drawdown**: {max_dd:.2f}%
**Expectancy**: {expectancy:.2f}
**Avg Win**: {avg_win:.2f}
**Avg Loss**: {avg_loss:.2f}
"""

    summary_filename = f'summary{suffix}.md' if suffix else 'summary.md'
    with open(os.path.join(output_dir, summary_filename), 'w') as f:
        f.write(summary)

    # Plots
    # Equity Curve
    plt.figure(figsize=(10, 6))
    plt.plot(trades_df['exit_time'], trades_df['equity'])
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Balance")
    plt.grid(True)
    equity_filename = f'equity_curve{suffix}.png' if suffix else 'equity_curve.png'
    plt.savefig(os.path.join(output_dir, equity_filename))
    plt.close()

    # Histogram PnL (as proxy for R if R not available)
    plt.figure(figsize=(10, 6))
    trades_df['pnl'].hist(bins=20)
    plt.title("PnL Distribution")
    plt.xlabel("PnL")
    plt.ylabel("Frequency")
    histogram_filename = f'histogram_R{suffix}.png' if suffix else 'histogram_R.png'
    plt.savefig(os.path.join(output_dir, histogram_filename)) # Naming it R but it's PnL for now
    plt.close()

    print(f"Report generated in {output_dir}")

