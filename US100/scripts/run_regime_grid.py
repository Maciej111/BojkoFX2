"""
Regime filter grid test — scrive i risultati in reports/regime_grid_results.txt
Usa run unico full-period + split trades per IS/OOS (3x più veloce).
"""
import sys, os
sys.path.insert(0, r"c:\dev\projects\BojkoFX2\US100")
sys.path.insert(0, r"c:\dev\projects\BojkoFX2\shared")
os.chdir(r"c:\dev\projects\BojkoFX2\US100")
import warnings; warnings.filterwarnings("ignore")

from scripts.run_backtest_idx import load_ltf, build_htf_from_ltf, filter_by_date, _calc_r_drawdown
from src.strategies.trend_following_v1 import run_trend_backtest
import pandas as pd

OUT_PATH = r"c:\dev\projects\BojkoFX2\US100\reports\regime_grid_results.txt"
out = open(OUT_PATH, "w", encoding="utf-8", buffering=1)

IS_END   = pd.Timestamp("2023-06-30 23:59", tz="UTC")
OOS_START= pd.Timestamp("2023-07-01 00:00", tz="UTC")

def log(msg=""):
    print(msg, flush=True)
    out.write(msg + "\n")
    out.flush()

def calc_metrics(trades):
    """Wylicz metryki z listy trade dict."""
    if not trades:
        return {"n": 0, "wr": 0.0, "ev": 0.0, "pf": 0.0, "dd": 0.0}
    wins = [t for t in trades if t.get("pnl_r", 0) > 0]
    wr = len(wins) / len(trades) * 100
    avg_win  = sum(t["pnl_r"] for t in wins) / len(wins) if wins else 0.0
    losses   = [t for t in trades if t.get("pnl_r", 0) <= 0]
    avg_loss = abs(sum(t["pnl_r"] for t in losses) / len(losses)) if losses else 1.0
    ev = (wr/100) * avg_win - (1 - wr/100) * avg_loss
    gross_win  = sum(t["pnl_r"] for t in wins)
    gross_loss = abs(sum(t["pnl_r"] for t in losses)) if losses else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
    dd = _calc_r_drawdown(trades)
    return {"n": len(trades), "wr": wr, "ev": ev, "pf": pf, "dd": dd}

def run_cfg(params, label):
    """Run full 2021-2025, split trades into IS/OOS."""
    p = dict(params)
    trades_full, m_full = run_trend_backtest("usatechidxusd", ltf_full.copy(), htf_full.copy(), p)
    
    is_trades  = [t for t in trades_full if pd.Timestamp(t.get("entry_time", "2000-01-01"), tz="UTC") <= IS_END]
    oos_trades = [t for t in trades_full if pd.Timestamp(t.get("entry_time", "2000-01-01"), tz="UTC") >= OOS_START]
    
    mf = calc_metrics(trades_full)
    mi = calc_metrics(is_trades)
    mo = calc_metrics(oos_trades)
    
    ok = "OK " if (mi["ev"] > 0 and mo["ev"] >= 0.50) else ("IS-" if mi["ev"] <= 0 else "OOS")
    log(f"  [{ok}] {label}: n={mf['n']}({mi['n']}/{mo['n']}) "
        f"WR={mf['wr']:.0f}% E={mf['ev']:+.3f} PF={mf['pf']:.2f} DD={mf['dd']:.1f}R  "
        f"IS={mi['ev']:+.3f}(n={mi['n']}) OOS={mo['ev']:+.3f}(n={mo['n']})")
    return {"label": label, **mf, "ev_is": mi["ev"], "ev_oos": mo["ev"],
            "n_is": mi["n"], "n_oos": mo["n"], "ok": ok}

log("=== REGIME FILTER GRID TEST ===")
log(f"Started: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
log()

log("Loading data...")
ltf5  = load_ltf("usatechidxusd", "5min")
htf4h = build_htf_from_ltf(ltf5, "4h")
log(f"LTF={len(ltf5)} HTF={len(htf4h)}")

ltf_full = filter_by_date(ltf5,  "2021-01-01", "2025-12-31")
htf_full = filter_by_date(htf4h, "2021-01-01", "2025-12-31")
log(f"Full window: LTF={len(ltf_full)} HTF={len(htf_full)}")
log()

PROD = dict(pivot_lookback_ltf=3, pivot_lookback_htf=5, confirmation_bars=1,
    require_close_break=True, entry_offset_atr_mult=0.3, pullback_max_bars=20,
    sl_anchor="last_pivot", sl_buffer_atr_mult=0.5, risk_reward=2.0,
    use_session_filter=True, session_start_hour_utc=13, session_end_hour_utc=20,
    use_bos_momentum_filter=True, bos_min_range_atr_mult=1.2,
    bos_min_body_to_range_ratio=0.6, use_flag_contraction_setup=False,
    flag_impulse_lookback_bars=8, flag_contraction_bars=5,
    flag_min_impulse_atr_mult=2.5, flag_max_contraction_atr_mult=1.2,
    flag_breakout_buffer_atr_mult=0.1, flag_sl_buffer_atr_mult=0.3)
BASE = dict(PROD, pivot_lookback_htf=4, risk_reward=2.5)

results = []

log("=== BASELINE (bez filtru rezimu) ===")
results.append(run_cfg(dict(PROD),  "PROD htf=5 rr=2.0"))
results.append(run_cfg(dict(BASE),  "BASE htf=4 rr=2.5"))

log()
log("=== KANDYDAT A: ADX threshold (HTF 4h, period=14) ===")
for thr in [15, 20, 25, 30]:
    p = dict(BASE, use_regime_filter=True, regime_method="A", regime_adx_threshold=float(thr))
    results.append(run_cfg(p, f"A: ADX>={thr}"))

log()
log("=== KANDYDAT B: ATR ratio 14/100 (HTF 4h) ===")
for thr in [0.8, 1.0, 1.2, 1.5]:
    p = dict(BASE, use_regime_filter=True, regime_method="B", regime_atr_ratio_threshold=float(thr))
    results.append(run_cfg(p, f"B: ATRratio>={thr}"))

log()
log("=== KANDYDAT C: EMA slope lookback (HTF 4h) ===")
for lb in [2, 3, 5]:
    p = dict(BASE, use_regime_filter=True, regime_method="C", regime_ema_lookback=int(lb))
    results.append(run_cfg(p, f"C: EMAslope lb={lb}"))

log()
log("=== PODSUMOWANIE (konfigi OK) ===")
ok_list = [r for r in results if r["ok"].strip() == "OK"]
if ok_list:
    for r in sorted(ok_list, key=lambda x: x["ev_oos"], reverse=True):
        log(f"  [OK] {r['label']}: IS={r['ev_is']:+.3f} OOS={r['ev_oos']:+.3f}")
else:
    log("  Brak konfiguracji spelniajacych kryterium IS>0 AND OOS>=0.50")

log()
log("=== ROCZNY BREAKDOWN (top 4 konfigi) ===")
top_configs = [
    ("A: ADX>=20", dict(BASE, use_regime_filter=True, regime_method="A", regime_adx_threshold=20.0)),
    ("A: ADX>=25", dict(BASE, use_regime_filter=True, regime_method="A", regime_adx_threshold=25.0)),
    ("B: ATRr>=1.0", dict(BASE, use_regime_filter=True, regime_method="B", regime_atr_ratio_threshold=1.0)),
    ("C: EMA lb=3", dict(BASE, use_regime_filter=True, regime_method="C", regime_ema_lookback=3)),
]
for cfg_label, params in top_configs:
    log(f"\n  --- {cfg_label} ---")
    for yr in [2021, 2022, 2023, 2024, 2025]:
        lt = filter_by_date(ltf5,  f"{yr}-01-01", f"{yr}-12-31")
        ht = filter_by_date(htf4h, f"{yr}-01-01", f"{yr}-12-31")
        p = dict(params)
        tr, m = run_trend_backtest("usatechidxusd", lt, ht, p)
        n   = m.get("trades_count", 0)
        ev  = m.get("expectancy_R", 0)
        wr  = m.get("win_rate", 0)
        dd  = _calc_r_drawdown(tr) if n > 0 else 0.0
        log(f"    {yr}: n={n:2d}  WR={wr:.0f}%  E={ev:+.3f}  DD={dd:.1f}R")

log()
log(f"=== DONE {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
out.close()
print("Script finished. Results in:", OUT_PATH)
