"""Run Trend Following v1 Backtest"""
import sys
import os
import argparse
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.strategies.trend_following_v1 import run_trend_following_backtest
from src.backtest.metrics import compute_metrics, add_R_column

def main():
    parser = argparse.ArgumentParser(description='Run Trend Following Backtest')
    parser.add_argument('--symbol', type=str, default='EURUSD')
    parser.add_argument('--ltf', type=str, default='H1')
    parser.add_argument('--htf', type=str, default='H4')
    parser.add_argument('--start', type=str, default='2021-01-01')
    parser.add_argument('--end', type=str, default='2024-12-31')
    parser.add_argument('--config', type=str, default='config/config.yaml')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("TREND FOLLOWING V1 BACKTEST")
    print(f"{'='*60}\n")
    print(f"Symbol: {args.symbol}")
    print(f"LTF: {args.ltf}, HTF: {args.htf}")
    print(f"Period: {args.start} to {args.end}\n")

    # Load config
    config = load_config(args.config)
    initial_balance = config['execution']['initial_balance']

    # Load LTF bars (H1)
    ltf_file = f"data/bars/{args.symbol.lower()}_h1_bars.csv"
    if not os.path.exists(ltf_file):
        print(f"✗ LTF bars not found: {ltf_file}")
        return

    ltf_df = pd.read_csv(ltf_file, index_col='timestamp', parse_dates=True)
    ltf_df = ltf_df[(ltf_df.index >= args.start) & (ltf_df.index <= args.end)]
    print(f"✓ Loaded {len(ltf_df)} LTF (H1) bars")

    # Build HTF bars (H4) from LTF
    htf_df = ltf_df.resample('4h').agg({
        'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
        'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
    }).dropna()
    print(f"✓ Built {len(htf_df)} HTF (H4) bars\n")

    # Run backtest
    trades_df, setup_stats = run_trend_following_backtest(ltf_df, htf_df, config, initial_balance)

    print(f"\n✓ Backtest Complete:")
    print(f"  Trades: {len(trades_df)}")
    print(f"  Setups Created: {setup_stats['total_setups']}")
    print(f"  Missed Setups: {setup_stats['missed_setups']} ({setup_stats['missed_rate']*100:.1f}%)")
    print(f"  Avg Bars to Fill: {setup_stats['avg_bars_to_fill']:.1f}")

    # Calculate metrics
    if len(trades_df) > 0:
        trades_df = add_R_column(trades_df)
        metrics = compute_metrics(trades_df, initial_balance)

        print(f"  Win Rate: {metrics['win_rate']:.2f}%")
        print(f"  Expectancy: {metrics['expectancy_R']:.3f}R")
        print(f"  Return: {((initial_balance + metrics['total_pnl']) / initial_balance - 1) * 100:.2f}%")

        # Save outputs
        output_file = f"data/outputs/trades_trend_{args.symbol}_{args.ltf}_{args.start}_{args.end}.csv"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        trades_df.to_csv(output_file, index=False)
        print(f"\n✓ Saved: {output_file}")
    else:
        print("\n⚠ No trades generated")

if __name__ == "__main__":
    main()


