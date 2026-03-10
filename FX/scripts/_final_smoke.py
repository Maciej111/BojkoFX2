"""Final smoke test before full grid — with session filter + flat bar removal."""
import sys
sys.path.insert(0, r'C:\dev\projects\BojkoFx\scripts')
import eurusd_grid_backtest as bt
import numpy as np

print("Loading bars (flat bars auto-removed)...")
ltf_30m = bt.load_bars("m30")
ltf_h1 = ltf_30m.resample("1h").agg({
    "open_bid":"first","high_bid":"max","low_bid":"min","close_bid":"last",
    "open_ask":"first","high_ask":"max","low_ask":"min","close_ask":"last",
}).dropna()
ltf_h1 = ltf_h1[(ltf_h1["high_bid"] - ltf_h1["low_bid"]) > 0]
print(f"  M30: {len(ltf_30m):,} bars | H1: {len(ltf_h1):,} bars")

cfgs = [
    ("H1/4h  RR=1.5 off=0.3 buf=0.5 pmb=40 session=True  [PROOF V2 equiv]",
     dict(ltf="h1",   htf="4h",  risk_reward=1.5, entry_offset_atr_mult=0.3,
          sl_buffer_atr_mult=0.5, pullback_max_bars=40, session_filter=True)),
    ("H1/4h  RR=2.5 off=0.0 buf=0.1 pmb=20 session=True  [Crypto equiv]",
     dict(ltf="h1",   htf="4h",  risk_reward=2.5, entry_offset_atr_mult=0.0,
          sl_buffer_atr_mult=0.1, pullback_max_bars=20, session_filter=True)),
    ("30m/4h RR=2.5 off=0.0 buf=0.1 pmb=20 session=True  [30m Crypto equiv]",
     dict(ltf="30min",htf="4h",  risk_reward=2.5, entry_offset_atr_mult=0.0,
          sl_buffer_atr_mult=0.1, pullback_max_bars=20, session_filter=True)),
    ("H1/D1  RR=2.5 off=0.0 buf=0.1 pmb=20 session=True  [H1/D1 wide HTF]",
     dict(ltf="h1",   htf="1d",  risk_reward=2.5, entry_offset_atr_mult=0.0,
          sl_buffer_atr_mult=0.1, pullback_max_bars=20, session_filter=True)),
    ("H1/4h  RR=2.0 off=0.0 buf=0.3 pmb=20 session=True  [middle ground]",
     dict(ltf="h1",   htf="4h",  risk_reward=2.0, entry_offset_atr_mult=0.0,
          sl_buffer_atr_mult=0.3, pullback_max_bars=20, session_filter=True)),
]

for label, params in cfgs:
    ltf = ltf_30m if params["ltf"] == "30min" else ltf_h1
    cfg = bt.BacktestConfig(**params, **{k:v for k,v in bt.FIXED.items()
                                          if k not in params})
    # OOS
    trades, eq = bt.run_backtest(ltf, cfg, "2023-01-01", "2024-12-31")
    m = bt.calc_metrics(trades, eq, cfg.initial_balance)
    # TRAIN
    tr_t, tr_eq = bt.run_backtest(ltf, cfg, "2021-01-01", "2022-12-31")
    tr_m = bt.calc_metrics(tr_t, tr_eq, cfg.initial_balance)

    print(f"\n{label}")
    print(f"  TRAIN n={tr_m['n_trades']:3d} WR={tr_m['win_rate']:5.1f}% "
          f"ExpR={tr_m['exp_R']:+.4f}R PF={tr_m['profit_factor']:.3f} "
          f"DD={tr_m['max_dd_pct']:5.1f}% Ret={tr_m['return_pct']:+6.1f}%")
    print(f"  OOS   n={m['n_trades']:3d} WR={m['win_rate']:5.1f}% "
          f"ExpR={m['exp_R']:+.4f}R PF={m['profit_factor']:.3f} "
          f"DD={m['max_dd_pct']:5.1f}% Ret={m['return_pct']:+6.1f}%")
    if trades:
        rs = np.array([t.R for t in trades])
        tp_hits = sum(1 for t in trades if t.exit_reason == "TP")
        sl_hits = sum(1 for t in trades if t.exit_reason == "SL")
        print(f"  R: min={rs.min():+.2f} max={rs.max():+.2f} | TP={tp_hits} SL={sl_hits}")

print("\n\nSmoke DONE.")

