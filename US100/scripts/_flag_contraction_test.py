"""
FLAG_CONTRACTION comparative backtest.

Runs BOS-only vs BOS+FLAG_CONTRACTION for each LTF (5m, 15m, 30m, 1h),
full period 2021-2024, and per year 2021-2024.

Usage:
    python -m scripts._flag_contraction_test
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import load_ltf, build_htf_from_ltf, filter_by_date
from src.strategies.trend_following_v1 import run_trend_backtest

SYMBOL   = "usatechidxusd"
HTF      = "4h"
YEARS    = [2021, 2022, 2023, 2024]
TIMEFRAMES = ["5min", "15min", "30min", "1h"]

# ── Base params (BOS, same as run_idx_summary defaults) ──────────────────────
BASE_PARAMS = {
    "pivot_lookback_ltf":    3,
    "pivot_lookback_htf":    5,
    "confirmation_bars":     1,
    "require_close_break":   True,
    "entry_offset_atr_mult": 0.3,
    "pullback_max_bars":     20,
    "sl_anchor":             "last_pivot",
    "sl_buffer_atr_mult":    0.5,
    "risk_reward":           2.0,
    "use_session_filter":    False,
    "use_bos_momentum_filter": True,
    "bos_min_range_atr_mult": 1.2,
    "bos_min_body_to_range_ratio": 0.6,
}

# ── FLAG additions ────────────────────────────────────────────────────────────
FLAG_EXTRAS = {
    "use_flag_contraction_setup":    True,
    "flag_impulse_lookback_bars":    8,
    "flag_contraction_bars":         5,
    "flag_min_impulse_atr_mult":     2.5,
    "flag_max_contraction_atr_mult": 1.2,
    "flag_breakout_buffer_atr_mult": 0.1,
    "flag_sl_buffer_atr_mult":       0.3,
}


def _calc_r_drawdown(trades_df):
    if trades_df is None or len(trades_df) == 0:
        return 0.0
    equity_r = [0.0]
    for r in trades_df["R"]:
        equity_r.append(equity_r[-1] + r)
    peak = equity_r[0]
    max_dd = 0.0
    for val in equity_r:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _run_one(ltf_df, htf_df, start, end, params):
    ltf_filt = filter_by_date(ltf_df, start, end)
    htf_filt = filter_by_date(htf_df, start, end)
    if len(ltf_filt) < 100:
        return None
    trades_df, metrics = run_trend_backtest(
        symbol=SYMBOL,
        ltf_df=ltf_filt,
        htf_df=htf_filt,
        params_dict=params,
        initial_balance=10_000.0,
    )
    if trades_df is None or len(trades_df) == 0:
        return None
    dd = _calc_r_drawdown(trades_df)
    n  = len(trades_df)
    wr = metrics.get("win_rate", 0)
    er = metrics.get("expectancy_R", 0)
    pf = metrics.get("profit_factor", 0)

    # Setup type breakdown
    if "setup_type" in trades_df.columns:
        bos_trades  = int((trades_df["setup_type"] == "BOS").sum())
        flag_trades = int((trades_df["setup_type"] == "FLAG_CONTRACTION").sum())
    else:
        bos_trades  = n
        flag_trades = 0

    return dict(n=n, wr=wr, er=er, pf=pf, dd=dd,
                bos_trades=bos_trades, flag_trades=flag_trades)


def _fmt(r):
    if r is None:
        return "  N/A  "
    return f"E={r['er']:+.3f}R  WR={r['wr']:.0f}%  PF={r['pf']:.2f}  DD={r['dd']:.1f}R  n={r['n']}"


def _fmt_split(r):
    """Show BOS vs FLAG trade count split."""
    if r is None or r['flag_trades'] == 0:
        return ""
    return f"  (BOS:{r['bos_trades']} FLAG:{r['flag_trades']})"


def main():
    print(f"\n{'='*80}")
    print(" FLAG_CONTRACTION COMPARATIVE BACKTEST — USATECHIDXUSD (US100)")
    print(f" BOS params: momentum filter ON (range≥1.2×ATR, body≥60%)")
    print(f" FLAG params: impulse≥2.5×ATR, contraction≤1.2×ATR, lookback=8, contr_bars=5")
    print(f"{'='*80}\n")

    # Pre-load bars (once per TF)
    bars: dict[str, tuple] = {}
    for ltf in TIMEFRAMES:
        try:
            ltf_df = load_ltf(SYMBOL, ltf)
            htf_df = build_htf_from_ltf(ltf_df, HTF)
            bars[ltf] = (ltf_df, htf_df)
        except FileNotFoundError as e:
            print(f"SKIP {ltf}: {e}")

    params_bos  = BASE_PARAMS.copy()
    params_flag = {**BASE_PARAMS, **FLAG_EXTRAS}

    # ── Table header ──────────────────────────────────────────────────────────
    header = f"{'TF':<6} {'Period':<10}  {'BOS-only':<55}  {'BOS+FLAG':<55}  {'ΔE':>8}"
    sep    = "-" * len(header)

    print(header)
    print(sep)

    for ltf in TIMEFRAMES:
        if ltf not in bars:
            continue
        ltf_df, htf_df = bars[ltf]

        # Full period
        r_bos  = _run_one(ltf_df, htf_df, "2021-01-01", "2024-12-31", params_bos)
        r_flag = _run_one(ltf_df, htf_df, "2021-01-01", "2024-12-31", params_flag)

        de = (r_flag['er'] - r_bos['er']) if (r_bos and r_flag) else float('nan')
        sign = "▲" if de > 0 else "▼"
        print(f"{ltf:<6} {'2021-2024':<10}  {_fmt(r_bos):<55}  {_fmt(r_flag):<55}  {sign}{abs(de):.3f}R{_fmt_split(r_flag)}")

        # Per year
        for year in YEARS:
            r_bos  = _run_one(ltf_df, htf_df, f"{year}-01-01", f"{year}-12-31", params_bos)
            r_flag = _run_one(ltf_df, htf_df, f"{year}-01-01", f"{year}-12-31", params_flag)

            de = (r_flag['er'] - r_bos['er']) if (r_bos and r_flag) else float('nan')
            sign = "▲" if de > 0 else ("▼" if de < 0 else " ")
            print(f"{'':6} {year:<10}  {_fmt(r_bos):<55}  {_fmt(r_flag):<55}  {sign}{abs(de):.3f}R{_fmt_split(r_flag)}")

        print(sep)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
