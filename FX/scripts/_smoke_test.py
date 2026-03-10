"""Quick sanity check before full grid run."""
import sys
sys.path.insert(0, r'C:\dev\projects\BojkoFx\scripts')
import eurusd_grid_backtest as bt

print("Loading M30 bars...")
ltf_30m = bt.load_bars("m30")
print(f"  M30: {len(ltf_30m):,} bars | {ltf_30m.index[0]} -> {ltf_30m.index[-1]}")
print(f"  Cols: {list(ltf_30m.columns)}")
print(f"  Spread sample (open): {(ltf_30m['open_ask'] - ltf_30m['open_bid']).mean()*10000:.2f} pips avg")

print("\nBuilding H1 from M30...")
import pandas as pd
ltf_h1 = ltf_30m.resample("1h").agg({
    "open_bid":"first","high_bid":"max","low_bid":"min","close_bid":"last",
    "open_ask":"first","high_ask":"max","low_ask":"min","close_ask":"last",
}).dropna()
print(f"  H1: {len(ltf_h1):,} bars")

# --- Smoke test 1: Baseline PROOF V2 equivalent ---
print("\n[1] Baseline H1/4h RR=1.5 off=0.3 buf=0.5 pmb=40 (PROOF V2 equivalent)...")
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
    rs = [t.R for t in t1]
    print(f"  R stats: min={min(rs):.2f}  max={max(rs):.2f}  mean={sum(rs)/len(rs):.4f}")
    print(f"  Sample exits: {[(t.exit_reason, round(t.R,2)) for t in t1[:5]]}")

# --- Smoke test 2: Crypto v1 FX equivalent ---
print("\n[2] Crypto equiv 30m/4h RR=2.5 off=0.0 buf=0.1 pmb=20...")
cfg2 = bt.BacktestConfig(
    ltf="30min", htf="4h", risk_reward=2.5,
    entry_offset_atr_mult=0.0, sl_buffer_atr_mult=0.1, pullback_max_bars=20,
    **{k:v for k,v in bt.FIXED.items()}
)
t2, eq2 = bt.run_backtest(ltf_30m, cfg2, "2023-01-01", "2024-12-31")
m2 = bt.calc_metrics(t2, eq2, cfg2.initial_balance)
print(f"  OOS n={m2['n_trades']}  WR={m2['win_rate']}%  ExpR={m2['exp_R']:+.4f}R  "
      f"PF={m2['profit_factor']}  DD={m2['max_dd_pct']}%  Ret={m2['return_pct']}%")

# --- Smoke test 3: TRAIN period check ---
print("\n[3] TRAIN 2021-2022 H1/4h RR=1.5 off=0.3 buf=0.5 pmb=40...")
t3, eq3 = bt.run_backtest(ltf_h1, cfg1, "2021-01-01", "2022-12-31")
m3 = bt.calc_metrics(t3, eq3, cfg1.initial_balance)
print(f"  TRAIN n={m3['n_trades']}  WR={m3['win_rate']}%  ExpR={m3['exp_R']:+.4f}R  "
      f"PF={m3['profit_factor']}  DD={m3['max_dd_pct']}%  Ret={m3['return_pct']}%")

print("\nSmoke test complete.")
