"""Diagnoza silnika — analiza trade R-values i SL distances."""
import sys
sys.path.insert(0, r'C:\dev\projects\BojkoFx\scripts')
import eurusd_grid_backtest as bt
import numpy as np
import pandas as pd

print("Loading data...")
ltf_30m = bt.load_bars("m30")

# Filter flat bars (zero range — weekends/holidays)
ltf_30m_clean = ltf_30m[(ltf_30m["high_bid"] - ltf_30m["low_bid"]) > 0].copy()
print(f"  M30 all: {len(ltf_30m):,}  after removing flat bars: {len(ltf_30m_clean):,}")

ltf_h1 = ltf_30m_clean.resample("1h").agg({
    "open_bid":"first","high_bid":"max","low_bid":"min","close_bid":"last",
    "open_ask":"first","high_ask":"max","low_ask":"min","close_ask":"last",
}).dropna()
# Remove H1 flat bars
ltf_h1 = ltf_h1[(ltf_h1["high_bid"] - ltf_h1["low_bid"]) > 0].copy()
print(f"  H1 after removing flat: {len(ltf_h1):,}")

# Quick ATR stats
atr = bt.calc_atr(ltf_h1)
print(f"\n  ATR(14) H1 stats: mean={atr.mean()*10000:.1f}pip  "
      f"min={atr.min()*10000:.1f}pip  max={atr.max()*10000:.1f}pip")

# Check pivot arrays
ph_lv, pl_lv, ph_mask, pl_mask = bt.build_pivot_arrays(ltf_h1, 3, 1)
n_ph = ph_mask.sum()
n_pl = pl_mask.sum()
print(f"  LTF H1 pivots: {n_ph} highs, {n_pl} lows")

# Run test with clean data
print("\n[1] H1/4h RR=1.5 off=0.3 buf=0.5 pmb=40 OOS (clean data)...")
cfg1 = bt.BacktestConfig(
    ltf="h1", htf="4h", risk_reward=1.5,
    entry_offset_atr_mult=0.3, sl_buffer_atr_mult=0.5, pullback_max_bars=40,
    **{k:v for k,v in bt.FIXED.items()}
)
t1, eq1 = bt.run_backtest(ltf_h1, cfg1, "2023-01-01", "2024-12-31")
m1 = bt.calc_metrics(t1, eq1, cfg1.initial_balance)
print(f"  OOS n={m1['n_trades']}  WR={m1['win_rate']}%  ExpR={m1['exp_R']:+.4f}R  "
      f"PF={m1['profit_factor']}  DD={m1['max_dd_pct']}%  Ret={m1['return_pct']}%")
if t1:
    rs = np.array([t.R for t in t1])
    # R histogram buckets
    buckets = [(-10,-3),(-3,-2),(-2,-1.5),(-1.5,-0.5),(-0.5,0),(0,0.5),(0.5,1.5),(1.5,2.5),(2.5,4)]
    print("  R distribution:")
    for lo, hi in buckets:
        cnt = ((rs >= lo) & (rs < hi)).sum()
        print(f"    [{lo:+.1f},{hi:+.1f}): {cnt}")
    print(f"  Outlier R<-3: {(rs < -3).sum()} trades")
    print(f"  Risk dist stats (pips): mean={np.mean([t.risk_dist for t in t1])*10000:.1f} "
          f"max={np.max([t.risk_dist for t in t1])*10000:.1f}")

    # show worst trades
    worst = sorted(t1, key=lambda x: x.R)[:5]
    print(f"  Worst 5 trades: {[(round(t.R,2), t.exit_reason, round(t.risk_dist*10000,1),'pips') for t in worst]}")

print("\n[2] 30m/4h RR=2.5 off=0.0 buf=0.1 pmb=20 OOS (clean M30)...")
cfg2 = bt.BacktestConfig(
    ltf="30min", htf="4h", risk_reward=2.5,
    entry_offset_atr_mult=0.0, sl_buffer_atr_mult=0.1, pullback_max_bars=20,
    **{k:v for k,v in bt.FIXED.items()}
)
t2, eq2 = bt.run_backtest(ltf_30m_clean, cfg2, "2023-01-01", "2024-12-31")
m2 = bt.calc_metrics(t2, eq2, cfg2.initial_balance)
print(f"  OOS n={m2['n_trades']}  WR={m2['win_rate']}%  ExpR={m2['exp_R']:+.4f}R  "
      f"PF={m2['profit_factor']}  DD={m2['max_dd_pct']}%  Ret={m2['return_pct']}%")
if t2:
    rs2 = np.array([t.R for t in t2])
    print(f"  R stats: min={rs2.min():.2f}  max={rs2.max():.2f}")
    print(f"  Risk dist stats (pips): mean={np.mean([t.risk_dist for t in t2])*10000:.1f}")

print("\nDiagnosis complete.")

