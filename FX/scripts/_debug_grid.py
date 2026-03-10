import sys, traceback
sys.stdout.reconfigure(line_buffering=True)

try:
    print("START", flush=True)
    sys.path.insert(0, r'C:\dev\projects\BojkoFx\scripts')
    import multisym_grid_backtest as m
    print("import OK", flush=True)

    symbols = ["eurusd", "gbpusd", "audusd", "nzdusd", "usdchf", "usdcad", "usdjpy"]
    for sym in symbols:
        print(f"  Loading {sym}...", flush=True)
        ltf_30m = m.load_bars(sym)
        ltf_h1  = m.resample_h1(ltf_30m)
        print(f"    M30={len(ltf_30m):,}  H1={len(ltf_h1):,}", flush=True)

        print(f"  Testing 1 config for {sym}...", flush=True)
        sp  = m.SYMBOL_PARAMS[sym]
        cfg = m.Config(
            ltf="h1", htf="1d", risk_reward=2.5,
            entry_offset_atr_mult=0.3, sl_buffer_atr_mult=0.1,
            pullback_max_bars=40,
            **m.BASE_CFG,
            commission   = sp["commission_pips"] * sp["pip"],
            min_risk     = sp["min_risk_pips"]   * sp["pip"],
            session_filter = sp["session_filter"],
        )
        trades, eq = m.run_backtest(ltf_h1, cfg, "2023-01-01", "2024-12-31")
        met = m.calc_metrics(trades, eq)
        print(f"    n={met['n_trades']} ExpR={met['exp_R']:+.4f}R WR={met['win_rate']}% DD={met['max_dd_pct']}%", flush=True)

    print("\nAll symbols OK — running full grid...", flush=True)
    import importlib, runpy
    runpy.run_path(r'C:\dev\projects\BojkoFx\scripts\multisym_grid_backtest.py', run_name='__main__')

except Exception as e:
    print(f"\nERROR: {e}", flush=True)
    traceback.print_exc()

