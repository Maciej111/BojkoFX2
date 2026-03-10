"""Deep statistical analysis for US100 backtests."""
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')
from scripts.run_backtest_idx import run_backtest

params = dict(pivot_lookback_ltf=3, pivot_lookback_htf=5, confirmation_bars=1,
    require_close_break=True, entry_offset_atr_mult=0.3, pullback_max_bars=20,
    sl_anchor='last_pivot', sl_buffer_atr_mult=0.5, risk_reward=2.0)


def analyze(df, label):
    n = len(df)
    total_r = df['R'].sum()
    print(f"\n{'='*60}")
    print(f"=== {label} ===")
    print(f"{'='*60}")
    print(f"Trades: {n}, Total R: {total_r:.2f}")
    print(f"Mean R: {df['R'].mean():.4f}")
    print(f"Median R: {df['R'].median():.4f}")
    print(f"Std R: {df['R'].std():.4f}")
    print(f"Min R: {df['R'].min():.4f}")
    print(f"Max R: {df['R'].max():.4f}")

    print("\nR Distribution:")
    buckets = [
        ('<-2', df['R'] < -2),
        ('-2to-1', (df['R'] >= -2) & (df['R'] < -1)),
        ('-1to0', (df['R'] >= -1) & (df['R'] < 0)),
        ('0to1', (df['R'] >= 0) & (df['R'] < 1)),
        ('1to2', (df['R'] >= 1) & (df['R'] < 2)),
        ('2to3', (df['R'] >= 2) & (df['R'] < 3)),
        ('>3', df['R'] >= 3),
    ]
    for lbl, mask in buckets:
        c = mask.sum()
        print(f"  {lbl}: {c} ({c/n*100:.1f}%)")

    print("\nOutlier Concentration:")
    sr = df['R'].sort_values(ascending=False)
    for top in [1, 3, 5, 10, 20]:
        top_r = sr.head(top).sum()
        pct = top_r / total_r * 100 if total_r != 0 else 0
        print(f"  Top {top:2d} trades: {top_r:8.1f}R  = {pct:.1f}% of total")
    bottom5 = sr.tail(5).sum()
    bottom10 = sr.tail(10).sum()
    print(f"  Bottom 5 trades: {bottom5:.1f}R")
    print(f"  Bottom 10 trades: {bottom10:.1f}R")

    print("\nLong vs Short:")
    for direction in ['LONG', 'SHORT']:
        sub = df[df['direction'] == direction]
        wr = 100 * (sub['R'] > 0).mean()
        exp = sub['R'].mean()
        print(f"  {direction}: n={len(sub)} WR={wr:.1f}% Exp={exp:.3f}R")

    print("\nExit Reasons:")
    print(df['exit_reason'].value_counts().to_string())

    if 'risk_distance' in df.columns and 'atr' in df.columns:
        df = df.copy()
        df['sl_atr'] = df['risk_distance'] / df['atr']
        print("\nSL Distance in ATR:")
        for thresh, lbl in [(1, '<1'), (2, '1-2'), (3, '2-3'), (4, '3-4')]:
            if thresh == 1:
                c = (df['sl_atr'] < 1).sum()
            else:
                c = ((df['sl_atr'] >= thresh - 1) & (df['sl_atr'] < thresh)).sum()
            print(f"  {lbl} ATR: {c} ({c/n*100:.1f}%)")
        c_gt4 = (df['sl_atr'] >= 4).sum()
        print(f"  >4 ATR: {c_gt4} ({c_gt4/n*100:.1f}%)")
        print(f"  Mean SL: {df['sl_atr'].mean():.2f} ATR")
        print(f"  Median SL: {df['sl_atr'].median():.2f} ATR")
    else:
        print("\nColumns available:", list(df.columns))

    # Yearly breakdown if datetime available
    if 'entry_time' in df.columns:
        df2 = df.copy()
        df2['year'] = pd.to_datetime(df2['entry_time']).dt.year
        print("\nYearly Breakdown:")
        for yr, sub in df2.groupby('year'):
            wr = 100 * (sub['R'] > 0).mean()
            exp = sub['R'].mean()
            pf_wins = sub.loc[sub['R'] > 0, 'R'].sum()
            pf_loss = abs(sub.loc[sub['R'] < 0, 'R'].sum())
            pf = pf_wins / pf_loss if pf_loss > 0 else float('inf')
            sr_yr = sub['R'].sort_values(ascending=False)
            top1_pct = sr_yr.head(1).sum() / sub['R'].sum() * 100 if sub['R'].sum() != 0 else 0
            top5_pct = sr_yr.head(5).sum() / sub['R'].sum() * 100 if sub['R'].sum() != 0 else 0
            print(f"  {yr}: n={len(sub)} WR={wr:.1f}% Exp={exp:.3f}R PF={pf:.2f} Top1={top1_pct:.0f}% Top5={top5_pct:.0f}%")


# ===== 5m FULL =====
print("Running 5m 2021-2024...")
t5, m5 = run_backtest('usatechidxusd', '2021-01-01', '2024-12-31',
    params=params, initial_balance=10000, ltf='5min', htf='4h')
analyze(t5, "5m/4H - 2021-2024 FULL")

# ===== 15m FULL =====
print("\nRunning 15m 2021-2024...")
t15, m15 = run_backtest('usatechidxusd', '2021-01-01', '2024-12-31',
    params=params, initial_balance=10000, ltf='15min', htf='4h')
analyze(t15, "15m/4H - 2021-2024 FULL")

# ===== 15m 2024 only (anomalous -87R MaxRDD) =====
print("\nRunning 15m 2024 only...")
t15_24, m15_24 = run_backtest('usatechidxusd', '2024-01-01', '2024-12-31',
    params=params, initial_balance=10000, ltf='15min', htf='4h')
analyze(t15_24, "15m/4H - 2024 ONLY")

print("\nDone.")
