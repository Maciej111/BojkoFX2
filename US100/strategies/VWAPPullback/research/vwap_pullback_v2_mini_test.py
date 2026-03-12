# VWAP Pullback v2 Mini-Test
# ==========================
# Validates two key fixes over v1:
#   1. Session VWAP: anchor at 14:30 UTC (not midnight)
#   2. Strict pullback: low_bid <= VWAP (no ATR buffer)
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\VWAPPullback\research\vwap_pullback_v2_mini_test.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parents[3]          # …/US100
SHARED_ROOT  = ROOT.parent / "shared"
RESEARCH_DIR = Path(__file__).resolve().parent              # …/research/
OUTPUT_DIR   = RESEARCH_DIR / "output"
PLOTS_DIR    = RESEARCH_DIR / "plots"
REPORT_DIR   = RESEARCH_DIR / "report"

for _p in [str(ROOT), str(SHARED_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.run_backtest_idx import load_ltf                              # noqa: E402
from strategies.VWAPPullback.config import BASE_CONFIG_V2                  # noqa: E402
from strategies.VWAPPullback.strategy import (                             # noqa: E402
    prepare_data_v2, run_backtest_v2, compute_metrics,
)

# ── run parameters ────────────────────────────────────────────────────────────
SYMBOL = "usatechidxusd"
TF     = "5min"
START  = "2021-01-01"
END    = "2025-12-31"

CFG = BASE_CONFIG_V2


# ── helpers ───────────────────────────────────────────────────────────────────

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
    ax1.set_title("VWAP Pullback v2 -- Equity Curve (2021-2025)")
    ax1.set_ylabel("Cumulative R")
    ax1.grid(alpha=0.3)

    ax2.fill_between(np.arange(len(dd)), -dd, 0, color="#ef5350", alpha=0.6)
    ax2.plot(np.arange(len(dd)), -dd, color="#c62828", linewidth=0.8)
    ax2.set_title("Drawdown")
    ax2.set_xlabel("Trade #")
    ax2.set_ylabel("Drawdown (R)")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    p = PLOTS_DIR / "vwap_pullback_v2_equity.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"  Plot saved: {p}")


# ── report ────────────────────────────────────────────────────────────────────

def _verdict(m: dict) -> str:
    if m["er"] >= 0.10 and m["pf"] >= 1.20 and m["tpy"] >= 30:
        return "**Promising -- deserves deeper research (micro-grid, walk-forward).**"
    if m["er"] >= 0.05 and m["pf"] >= 1.10:
        return "**Marginal improvement over v1 -- try further tuning before deeper research.**"
    return "**Not convincing -- session VWAP alone insufficient; further experimentation needed.**"


def save_report(trades_df: pd.DataFrame, m: dict, meta: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    yrly = yearly_breakdown(trades_df)

    yrly_md = "| Year | Trades | WR% | E(R) | PF |\n|------|--------|-----|------|----|\n"
    for r in yrly:
        yrly_md += f"| {r['year']} | {r['n']} | {r['wr']:.1f}% | {r['er']:+.3f} | {r['pf']:.2f} |\n"

    md = f"""# VWAP Pullback v2 -- Mini-Test Report

**Strategy:** VWAP Pullback v2 (LONG only)
**Symbol:** USATECHIDXUSD (US100 CFD)
**Period:** {START} to {END}
**Generated:** {now}

---

## Key Changes vs v1

| Change | v1 | v2 |
|--------|----|----|
| VWAP anchor | Midnight UTC | **14:30 UTC (session open)** |
| Pullback condition | low <= VWAP + 0.5*ATR | **low <= VWAP (strict touch)** |
| Body ratio filter | >= 0.10 | Removed (close > open sufficient) |
| Max trades/day | 1 | **2** |
| Prior regime bars | 3 | 0 (disabled) |

---

## Strategy Rules

| Parameter | Value |
|-----------|-------|
| Direction | LONG only |
| Trend filter | close_bid > EMA{CFG.ema_period_htf} on 1h bars |
| VWAP anchor | {CFG.session_open_hour}:{CFG.session_open_minute:02d} UTC (session open, daily reset) |
| Pullback | low_bid <= VWAP (strict touch) |
| Confirmation | close_bid > open_bid AND close_bid > VWAP |
| Entry | Next bar open |
| Stop loss | Pullback low - {CFG.stop_buffer_atr_mult} * ATR |
| Take profit | {CFG.take_profit_rr}R |
| EOD close | {CFG.session_close_hour}:00 UTC |
| Max trades/day | {CFG.max_trades_per_day} |
| ATR period | {CFG.atr_period} |

---

## Results Summary

| Metric | v2 Value | v1 Value | Change |
|--------|----------|----------|--------|
| Total trades | {m['n']} | 433 | {m['n']-433:+d} |
| Trades/year | {m['tpy']:.1f} | 86.6 | {m['tpy']-86.6:+.1f} |
| Win rate | {m['wr']:.1f}% | 43.0% | {m['wr']-43.0:+.1f}pp |
| **Expectancy (R)** | **{m['er']:+.3f}** | **+0.047** | **{m['er']-0.047:+.3f}** |
| **Profit factor** | **{m['pf']:.2f}** | **1.08** | **{m['pf']-1.08:+.2f}** |
| Max drawdown | {m['mdd']:.1f} R | 20.8 R | {m['mdd']-20.8:+.1f} R |
| Max consec. losses | {m['mcl']} | 8 | {m['mcl']-8:+d} |
| TP exits | {m['tp_pct']:.1f}% | 39.7% | {m['tp_pct']-39.7:+.1f}pp |
| SL exits | {m['sl_pct']:.1f}% | 55.9% | {m['sl_pct']-55.9:+.1f}pp |
| EOD exits | {m['eod_pct']:.1f}% | 4.4% | {m['eod_pct']-4.4:+.1f}pp |

Days with a trade setup: {m['n']} out of {meta['days_total']} total trading days
Days with no setup found: {meta['days_no_setup']}

---

## Yearly Breakdown

{yrly_md}

---

## Equity Curve

`plots/vwap_pullback_v2_equity.png`

---

## Observations

### Session VWAP
The VWAP now resets at 14:30 UTC (US session open). This makes the VWAP a
true intraday equilibrium reference for the current session rather than a
14.5h-old cumulative average. Pullbacks to this level are more meaningful.

### Strict VWAP touch
Requiring `low_bid <= VWAP` (vs `<= VWAP + 0.5*ATR`) filters out signals
where price merely approached but never reached the VWAP level. This reduces
trade count but (ideally) improves signal quality.

---

## Conclusion

{_verdict(m)}

### Next steps if promising
1. Add prior regime filter (e.g., 2 bars closing above VWAP before pullback)
2. Grid search: TP_rr in [1.5, 2.0, 2.5], stop_buffer in [0.2, 0.3, 0.5]
3. Walk-forward validation (2024, 2025 OOS windows)
4. Consider volatility filter (ATR > 20-day median)

---

*Script: `strategies/VWAPPullback/research/vwap_pullback_v2_mini_test.py`*
"""
    out = REPORT_DIR / "VWAP_pullback_v2_mini_test_report.md"
    out.write_text(md, encoding="utf-8")
    print(f"  Report saved: {out}")


# ── console output ────────────────────────────────────────────────────────────

def print_results(trades_df: pd.DataFrame, m: dict, meta: dict) -> None:
    SEP = "=" * 65
    print()
    print(SEP)
    print("  VWAP PULLBACK v2 - MINI-TEST RESULTS (2021-2025)")
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
    print("  --- Comparison to v1 ---")
    print(f"  Expectancy : v1=+0.047  v2={m['er']:+.3f}  delta={m['er']-0.047:+.3f}")
    print(f"  PF         : v1= 1.08   v2= {m['pf']:.2f}    delta={m['pf']-1.08:+.2f}")
    print(f"  MaxDD      : v1=20.8R   v2={m['mdd']:.1f}R    delta={m['mdd']-20.8:+.1f}R")
    print(SEP)
    print()


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("  VWAP PULLBACK v2 MINI-TEST")
    print("=" * 65)
    print(f"  Session VWAP: anchor {CFG.session_open_hour}:{CFG.session_open_minute:02d} UTC")
    print(f"  Pullback    : strict touch (low <= VWAP, no buffer)")
    print(f"  EMA={CFG.ema_period_htf}  TP={CFG.take_profit_rr}R  SL_buf={CFG.stop_buffer_atr_mult}x ATR")
    print()

    print("Loading 5m bars ...")
    df = load_ltf(SYMBOL, TF)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()
    print(f"  {len(df):,} bars after date filter")

    print("Computing indicators (session VWAP / ATR / EMA) ...")
    df_prep = prepare_data_v2(df, CFG)

    print("Running backtest ...")
    trades_df, meta = run_backtest_v2(df_prep, CFG)
    print(f"  {len(trades_df)} trades")

    if trades_df.empty:
        print("  No trades generated -- check parameters.")
        sys.exit(0)

    m = compute_metrics(trades_df)
    print_results(trades_df, m, meta)

    # save CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "vwap_pullback_v2_mini_test_trades.csv"
    trades_df.to_csv(csv_path, index=False)
    print(f"  Trades CSV: {csv_path}")

    plot_equity(trades_df)
    save_report(trades_df, m, meta)

    print()
    print("=" * 65)
    print("  DONE")
    print("=" * 65)
