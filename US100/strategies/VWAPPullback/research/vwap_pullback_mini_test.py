# VWAP Pullback Mini-Test
# =======================
# Quick validation: does a simple VWAP Pullback setup show any edge on US100?
#
# Strategy (LONG only):
#   1. Trend filter: close_bid > EMA50 on 1h bars
#   2. Prior regime: last 3 bars all closed above VWAP
#   3. Pullback: bar low_bid <= VWAP + 0.5*ATR
#   4. Confirmation: bullish candle, close > VWAP, body_ratio >= 0.1
#   5. Entry: next bar open
#   6. SL: pullback_low - 0.3*ATR
#   7. TP: 1.5R
#   8. EOD: close at 21:00 UTC
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\VWAPPullback\research\vwap_pullback_mini_test.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parents[3]          # …/US100
SHARED_ROOT  = ROOT.parent / "shared"
STRATEGY_DIR = Path(__file__).resolve().parents[1]          # …/VWAPPullback/
RESEARCH_DIR = Path(__file__).resolve().parent              # …/research/
OUTPUT_DIR   = RESEARCH_DIR / "output"
PLOTS_DIR    = RESEARCH_DIR / "plots"
REPORT_DIR   = RESEARCH_DIR / "report"

for _p in [str(ROOT), str(SHARED_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.run_backtest_idx import load_ltf                           # noqa: E402
from strategies.VWAPPullback.config import BASE_CONFIG                  # noqa: E402
from strategies.VWAPPullback.strategy import (                          # noqa: E402
    prepare_data, run_backtest, compute_metrics,
)

# ── run parameters ────────────────────────────────────────────────────────────
SYMBOL = "usatechidxusd"
TF     = "5min"
START  = "2021-01-01"
END    = "2025-12-31"

CFG = BASE_CONFIG   # use baseline config unchanged


# ── metrics helpers ───────────────────────────────────────────────────────────

def yearly_breakdown(trades_df: pd.DataFrame) -> list[dict]:
    rows = []
    for yr, grp in trades_df.groupby("year"):
        arr = grp["R"].to_numpy(float)
        n   = len(arr)
        gw  = float(arr[arr > 0].sum())
        gl  = float(abs(arr[arr < 0].sum()))
        rows.append(dict(
            year = int(yr),
            n    = n,
            wr   = round(float((arr > 0).mean()) * 100, 1),
            er   = round(float(arr.mean()), 3),
            pf   = round(gw / gl if gl > 0 else float("inf"), 2),
        ))
    return rows


# ── plotting ──────────────────────────────────────────────────────────────────

def plot_equity(trades_df: pd.DataFrame) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available - skipping plot")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    arr = trades_df["R"].to_numpy(float)
    eq  = np.concatenate([[0.0], np.cumsum(arr)])
    dd  = np.maximum.accumulate(eq) - eq

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax1.plot(np.arange(len(eq)), eq, color="#2196F3", linewidth=1.2)
    ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax1.set_title("VWAP Pullback — Equity Curve (2021-2025)")
    ax1.set_ylabel("Cumulative R")
    ax1.grid(alpha=0.3)

    ax2.fill_between(np.arange(len(dd)), -dd, 0, color="#ef5350", alpha=0.6)
    ax2.plot(np.arange(len(dd)), -dd, color="#c62828", linewidth=0.8)
    ax2.set_title("Drawdown")
    ax2.set_xlabel("Trade #")
    ax2.set_ylabel("Drawdown (R)")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    p = PLOTS_DIR / "vwap_pullback_equity.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  Plot saved: {p}")


# ── report ────────────────────────────────────────────────────────────────────

def _verdict(m: dict) -> str:
    if m["er"] >= 0.10 and m["pf"] >= 1.20 and m["tpy"] >= 30:
        return "**Promising — deserves deeper research.**"
    if m["er"] >= 0.05 and m["pf"] >= 1.10:
        return "**Potentially interesting — marginal edge, needs further validation.**"
    return "**Not convincing at this stage — no clear edge detected.**"


def save_report(trades_df: pd.DataFrame, m: dict, meta: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    yrly = yearly_breakdown(trades_df)

    yrly_md = "| Year | Trades | WR% | E(R) | PF |\n|------|--------|-----|------|----|\n"
    for r in yrly:
        yrly_md += f"| {r['year']} | {r['n']} | {r['wr']:.1f}% | {r['er']:+.3f} | {r['pf']:.2f} |\n"

    md = f"""# VWAP Pullback — Mini-Test Report

**Strategy:** VWAP Pullback (LONG only)  
**Symbol:** USATECHIDXUSD (US100 CFD)  
**Period:** {START} to {END}  
**Generated:** {now}

---

## Strategy Rules

| Parameter | Value |
|-----------|-------|
| Direction | LONG only |
| Trend filter | close_bid > EMA{CFG.ema_period_htf} on 1h bars |
| VWAP anchor | Midnight UTC (equal-weight TP average, daily reset) |
| Prior regime | Last {CFG.min_bars_above_vwap} bars close > VWAP |
| Pullback tolerance | low_bid <= VWAP + {CFG.vwap_tolerance_atr_mult} * ATR |
| Confirmation | Bullish candle, close > VWAP, body_ratio >= {CFG.min_body_ratio} |
| Entry | Next bar open |
| Stop loss | Pullback low - {CFG.stop_buffer_atr_mult} * ATR |
| Take profit | {CFG.take_profit_rr}R |
| EOD close | {CFG.session_end_hour_utc}:00 UTC |
| Max trades/day | {CFG.max_trades_per_day} |
| ATR period | {CFG.atr_period} |

---

## Results Summary

| Metric | Value |
|--------|-------|
| Total trades | {m['n']} |
| Trades/year | {m['tpy']:.1f} |
| Win rate | {m['wr']:.1f}% |
| Expectancy (R) | {m['er']:+.3f} |
| Profit factor | {m['pf']:.2f} |
| Max drawdown | {m['mdd']:.1f} R |
| Max consec. losses | {m['mcl']} |
| TP exits | {m['tp_pct']:.1f}% |
| SL exits | {m['sl_pct']:.1f}% |
| EOD exits | {m['eod_pct']:.1f}% |

Days with a trade setup: {m['n']} out of {meta['days_total']} total trading days  
Days with no setup found: {meta['days_no_setup']}

---

## Yearly Breakdown

{yrly_md}

---

## Equity Curve

`plots/vwap_pullback_equity.png`

---

## Conclusion

{_verdict(m)}

### Notes on this version

- VWAP is anchored at midnight UTC (not US session open). At 14:30 UTC entry window,
  the VWAP already reflects ~14.5 hours of price data, making it a longer-anchored
  reference than a pure session-anchored VWAP. A session-anchored variant (14:30 UTC
  anchor) is a natural next experiment if results are promising.
- No volume data available for NAS100 CFD bars; VWAP uses equal-weight cumulative
  typical price.
- LONG only. Short-side not tested.
- No walk-forward test at this stage.

---

*Script: `strategies/VWAPPullback/research/vwap_pullback_mini_test.py`*
"""
    out = REPORT_DIR / "VWAP_pullback_mini_test_report.md"
    out.write_text(md, encoding="utf-8")
    print(f"  Report saved: {out}")


# ── console output ────────────────────────────────────────────────────────────

def print_results(trades_df: pd.DataFrame, m: dict, meta: dict) -> None:
    SEP = "=" * 65
    print()
    print(SEP)
    print("  VWAP PULLBACK - MINI-TEST RESULTS (2021-2025)")
    print(SEP)
    print(f"  Total trades     : {m['n']}")
    print(f"  Trades/year      : {m['tpy']:.1f}")
    print(f"  Win rate         : {m['wr']:.1f}%")
    print(f"  Expectancy       : {m['er']:+.3f} R")
    print(f"  Profit factor    : {m['pf']:.2f}")
    print(f"  Max drawdown     : {m['mdd']:.1f} R")
    print(f"  Max consec. loss : {m['mcl']}")
    print(f"  Exit breakdown   : TP={m['tp_pct']:.0f}%  SL={m['sl_pct']:.0f}%  EOD={m['eod_pct']:.0f}%")
    print()
    print("  Yearly breakdown:")
    for r in yearly_breakdown(trades_df):
        print(f"    {r['year']}  n={r['n']:3d}  WR={r['wr']:4.1f}%  E(R)={r['er']:+.3f}  PF={r['pf']:.2f}")
    print()
    print(f"  Trading days: {meta['days_total']}  |  Days with no setup: {meta['days_no_setup']}")
    print(SEP)
    print()


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("  VWAP PULLBACK MINI-TEST")
    print("=" * 65)
    print(f"  EMA={CFG.ema_period_htf}  tol={CFG.vwap_tolerance_atr_mult}x ATR  "
          f"body={CFG.min_body_ratio}  TP={CFG.take_profit_rr}R")
    print()

    print("Loading 5m bars ...")
    df = load_ltf(SYMBOL, TF)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()
    print(f"  {len(df):,} bars after date filter")

    print("Computing indicators (VWAP / ATR / EMA) ...")
    df_prep = prepare_data(df, CFG)

    print("Running backtest ...")
    trades_df, meta = run_backtest(df_prep, CFG)
    print(f"  {len(trades_df)} trades")

    if trades_df.empty:
        print("  No trades generated — check parameters.")
        sys.exit(0)

    m = compute_metrics(trades_df)
    print_results(trades_df, m, meta)

    # save CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "vwap_pullback_mini_test_trades.csv"
    trades_df.to_csv(csv_path, index=False)
    print(f"  Trades CSV: {csv_path}")

    plot_equity(trades_df)
    save_report(trades_df, m, meta)

    print()
    print("=" * 65)
    print("  DONE")
    print("=" * 65)
