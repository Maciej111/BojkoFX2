# ORB v5 Walk-Forward Validation
# ================================
# Validates ORB v5 robustness using rolling walk-forward windows.
#
# Walk-forward splits
#   Window 1: train 2021-2023  |  test 2024
#   Window 2: train 2022-2024  |  test 2025
#
# Strategy rules are FIXED (same as orb_v5_mini_test.py).
# Training data is used only to confirm the edge exists before each test period.
# No parameters are optimised.
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v5_walkforward.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf            # noqa: E402

# ── constants (identical to ORB v5) ──────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
OR_START_MIN  = 14 * 60 + 30
OR_END_MIN    = 15 * 60 + 0
SESSION_END_H = 21
RR            = 1.6
EMA_PERIOD    = 50

# Walk-forward windows  (train_start, train_end, test_start, test_end)
WF_WINDOWS = [
    ("2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2022-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
]

PLOTS_DIR   = Path(__file__).parent / "plots"
REPORT_PATH = Path(__file__).parent / "ORB_v5_walkforward_report.md"


# ── helpers ───────────────────────────────────────────────────────────────────

def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


def _build_ema50_1h(df5m: pd.DataFrame) -> pd.Series:
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    return h1.ewm(span=EMA_PERIOD, adjust=False).mean().reindex(df5m.index, method="ffill")


def _max_dd_r(r_series: pd.Series) -> float:
    equity = np.concatenate([[0.0], np.cumsum(r_series.values)])
    return float((np.maximum.accumulate(equity) - equity).max())


def _max_consec_losses(r_series: pd.Series) -> int:
    best = cur = 0
    for r in r_series:
        cur = cur + 1 if r < 0 else 0
        best = max(best, cur)
    return best


def _sharpe(r_series: pd.Series) -> float:
    if len(r_series) < 2 or r_series.std() == 0:
        return 0.0
    # annualise assuming ~252 trading days
    tpy = len(r_series) / max(r_series.index.nunique() if hasattr(r_series.index, "nunique") else 1, 1)
    return float(r_series.mean() / r_series.std() * np.sqrt(252))


def _metrics(tdf: pd.DataFrame, label: str = "") -> dict:
    if tdf.empty:
        return dict(label=label, trades=0, tpy=0.0, wr=0.0, er=0.0, pf=0.0,
                    mdd=0.0, tp_pct=0.0, eod_pct=0.0, avg_r=0.0, std_r=0.0,
                    max_consec_loss=0, sharpe=0.0)
    n   = len(tdf)
    yrs = tdf["year"].nunique()
    vc  = tdf["exit_reason"].value_counts()
    gw  = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl  = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    return dict(
        label          = label,
        trades         = n,
        tpy            = round(n / yrs, 1),
        wr             = round((tdf["R"] > 0).mean() * 100, 1),
        er             = round(tdf["R"].mean(), 3),
        pf             = round(gw / gl if gl > 0 else float("inf"), 2),
        mdd            = round(_max_dd_r(tdf["R"]), 1),
        tp_pct         = round(int(vc.get("TP",  0)) / n * 100, 1),
        eod_pct        = round(int(vc.get("EOD", 0)) / n * 100, 1),
        avg_r          = round(tdf["R"].mean(), 4),
        std_r          = round(tdf["R"].std(),  4),
        max_consec_loss= _max_consec_losses(tdf["R"]),
        sharpe         = round(_sharpe(tdf["R"]), 2),
    )


# ── core: run ORB v5 on a pre-sliced DataFrame ───────────────────────────────

def run_v5_on_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run ORB v5 logic on df (already sliced to the desired date range).
    df must already have ema50_1h computed (so EMA is warm from earlier data).
    Returns trade DataFrame with columns: date, year, R, exit_reason.
    """
    records: list[dict] = []

    for date, day in df.groupby("date"):
        day = day.sort_index()

        or_mask = (day.index.map(_bar_minutes) >= OR_START_MIN) & \
                  (day.index.map(_bar_minutes) <  OR_END_MIN)
        or_bars = day[or_mask]
        if len(or_bars) < 3:
            continue

        or_open  = or_bars.iloc[0]["open_bid"]
        or_close = or_bars.iloc[-1]["close_bid"]
        or_high  = or_bars["high_bid"].max()
        or_low   = or_bars["low_bid"].min()

        if (or_high - or_low) <= 0:
            continue
        if or_close <= or_open:          # bullish OR filter
            continue

        post_mask = (day.index.map(_bar_minutes) >= OR_END_MIN) & \
                    (day.index.hour < SESSION_END_H)
        post_bars = day[post_mask]
        if len(post_bars) < 2:
            continue

        trade_taken = False
        for bar_i, (ts, bar) in enumerate(post_bars.iterrows()):
            if trade_taken:
                break
            if bar["close_bid"] <= or_high:
                continue
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                break

            remaining = post_bars.iloc[bar_i + 1:]
            if len(remaining) == 0:
                break

            entry_price = remaining.iloc[0]["open_bid"]
            sl   = or_low
            risk = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + RR * risk

            exit_price  = None
            exit_reason = "EOD"

            for _ts, ebar in remaining.iloc[1:].iterrows():
                if ebar["low_bid"] <= sl:
                    exit_price, exit_reason = sl, "SL"
                    break
                if ebar["high_bid"] >= tp:
                    exit_price, exit_reason = tp, "TP"
                    break

            if exit_price is None:
                eod_cutoff = post_bars.index[0].replace(
                    hour=SESSION_END_H, minute=0, second=0)
                eod_bars = post_bars[post_bars.index < eod_cutoff]
                if len(eod_bars) == 0:
                    continue
                exit_price  = eod_bars.iloc[-1]["close_bid"]
                exit_reason = "EOD"

            records.append({
                "date":        str(date.date()),
                "year":        int(date.year),
                "R":           round((exit_price - entry_price) / risk, 4),
                "exit_reason": exit_reason,
            })
            trade_taken = True

    return pd.DataFrame(records)


# ── walk-forward runner ───────────────────────────────────────────────────────

def run_walkforward(df_full: pd.DataFrame) -> tuple[list[dict], list[pd.DataFrame]]:
    """
    Runs each WF window.  EMA is always computed on the full dataset so it is
    warm from 2021-01-01 regardless of which slice is used as test.
    Returns (window_metrics_list, test_trade_df_list).
    """
    window_metrics: list[dict] = []
    test_dfs:       list[pd.DataFrame] = []

    for train_s, train_e, test_s, test_e in WF_WINDOWS:
        label = f"Test {test_s[:4]}"

        # Slice test window (EMA already warm in df_full)
        df_test = df_full[(df_full.index >= test_s) & (df_full.index <= test_e)].copy()
        df_test["date"] = df_test.index.normalize()

        tdf = run_v5_on_df(df_test)
        m   = _metrics(tdf, label=label)

        # Also compute train-window metrics for reference
        df_train = df_full[(df_full.index >= train_s) & (df_full.index <= train_e)].copy()
        df_train["date"] = df_train.index.normalize()
        tdf_train  = run_v5_on_df(df_train)
        m_train    = _metrics(tdf_train, label=f"Train {train_s[:4]}-{train_e[:4]}")

        window_metrics.append({"train": m_train, "test": m})
        test_dfs.append(tdf)

    return window_metrics, test_dfs


# ── plotting ──────────────────────────────────────────────────────────────────

def plot_equity_and_drawdown(all_test_trades: pd.DataFrame) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available -- skipping plots")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    r_vals  = all_test_trades["R"].values
    equity  = np.concatenate([[0.0], np.cumsum(r_vals)])
    peaks   = np.maximum.accumulate(equity)
    dd      = peaks - equity
    labels  = list(all_test_trades["date"])

    xs = list(range(len(equity)))

    # equity curve
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs[1:], equity[1:], color="steelblue", linewidth=1.5, label="Cumulative R")
    ax.axhline(0, color="black", linewidth=0.7, linestyle="--")

    # shade each test window
    years = all_test_trades["year"].unique()
    colours = ["#e8f4f8", "#f0ebe8"]
    for i, yr in enumerate(sorted(years)):
        yr_idx = [j for j, row in enumerate(all_test_trades.itertuples()) if row.year == yr]
        if yr_idx:
            ax.axvspan(yr_idx[0], yr_idx[-1], alpha=0.25,
                       color=colours[i % len(colours)], label=str(yr))

    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative R")
    ax.set_title("ORB v5 Walk-Forward — Equity Curve (test windows)")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "orb_v5_equity_curve.png", dpi=120)
    plt.close(fig)
    print(f"Plot saved: {PLOTS_DIR / 'orb_v5_equity_curve.png'}")

    # drawdown curve
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.fill_between(xs, -dd, 0, color="tomato", alpha=0.6)
    ax.plot(xs, -dd, color="firebrick", linewidth=1.0)
    ax.set_xlabel("Trade # (0 = start of equity)")
    ax.set_ylabel("Drawdown (R)")
    ax.set_title("ORB v5 Walk-Forward — Drawdown Curve (test windows)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "orb_v5_drawdown_curve.png", dpi=120)
    plt.close(fig)
    print(f"Plot saved: {PLOTS_DIR / 'orb_v5_drawdown_curve.png'}")


# ── console output ────────────────────────────────────────────────────────────

def print_results(window_metrics: list[dict], combined: dict) -> None:
    SEP = "=" * 72
    print()
    print(SEP)
    print("  ORB v5 WALK-FORWARD VALIDATION - US100 (USATECHIDXUSD)")
    print(SEP)
    print(f"  Strategy : LONG only | EMA50 1h | bullish OR | TP={RR}R | SL=OR_low")
    print(f"  Windows  : {len(WF_WINDOWS)}x  (train 3yr, test 1yr, rolling)")
    print()

    H = f"  {'Window':<26}  {'Trades':>6}  {'T/yr':>5}  {'WR%':>6}  " \
        f"{'E(R)':>7}  {'PF':>5}  {'MaxDD':>7}"
    print(H)
    print("  " + "-" * (len(H) - 2))

    for wm in window_metrics:
        for role, m in [("TRAIN", wm["train"]), ("TEST ", wm["test"])]:
            star = "  <-- OOS" if role == "TEST " else ""
            print(
                f"  {role} {m['label']:<21}  {m['trades']:>6}  {m['tpy']:>5.1f}  "
                f"{m['wr']:>5.1f}%  {m['er']:>+7.3f}  {m['pf']:>5.2f}  "
                f"{m['mdd']:>6.1f}R{star}"
            )
        print()

    print("  " + "-" * (len(H) - 2))
    m = combined
    print(
        f"  {'COMBINED OOS':<27}  {m['trades']:>6}  {m['tpy']:>5.1f}  "
        f"{m['wr']:>5.1f}%  {m['er']:>+7.3f}  {m['pf']:>5.2f}  {m['mdd']:>6.1f}R"
    )
    print()
    print("  Stability metrics (combined OOS)")
    print(f"    Avg R per trade  : {m['avg_r']:+.4f}")
    print(f"    Std R per trade  : {m['std_r']:.4f}")
    print(f"    Max consec losses: {m['max_consec_loss']}")
    print(f"    Sharpe (annual.) : {m['sharpe']:.2f}")

    meets = m["er"] >= 0.07 and m["pf"] >= 1.20 and m["tpy"] >= 60
    all_oos_pos = all(wm["test"]["er"] > 0 for wm in window_metrics)
    verdict = "ROBUST" if (meets and all_oos_pos) else "NOT YET ROBUST"
    print()
    print(f"  Verdict: {verdict}")
    print(f"    E(R)>+0.07R : {'PASS' if m['er'] >= 0.07 else 'FAIL'}  ({m['er']:+.3f})")
    print(f"    PF>=1.20    : {'PASS' if m['pf'] >= 1.20 else 'FAIL'}  ({m['pf']:.2f})")
    print(f"    T/yr>=60    : {'PASS' if m['tpy'] >= 60  else 'FAIL'}  ({m['tpy']:.1f})")
    print(f"    Both OOS+   : {'PASS' if all_oos_pos else 'FAIL'}")
    print(SEP)
    print()


# ── markdown report ───────────────────────────────────────────────────────────

def save_report(window_metrics: list[dict], combined: dict) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    meets      = combined["er"] >= 0.07 and combined["pf"] >= 1.20 and combined["tpy"] >= 60
    all_oos_pos = all(wm["test"]["er"] > 0 for wm in window_metrics)
    robust     = meets and all_oos_pos
    verdict    = "**ROBUST**" if robust else "**NOT YET ROBUST**"

    # per-window table rows
    rows = ""
    for wm in window_metrics:
        for role, m in [("Train", wm["train"]), ("Test (OOS)", wm["test"])]:
            rows += (f"| {role} | {m['label']} | {m['trades']} | {m['tpy']:.1f} | "
                     f"{m['wr']:.1f}% | {m['er']:+.3f} | {m['pf']:.2f} | {m['mdd']:.1f}R |\n")

    m = combined
    combined_row = (f"| **Combined OOS** | 2024–2025 | {m['trades']} | {m['tpy']:.1f} | "
                    f"{m['wr']:.1f}% | {m['er']:+.3f} | {m['pf']:.2f} | {m['mdd']:.1f}R |\n")

    # yearly breakdown of combined OOS
    oos_yearly_rows = ""
    for wm in window_metrics:
        t  = wm["test"]
        oos_yearly_rows += f"| {t['label']} | {t['trades']} | {t['wr']:.1f}% | {t['er']:+.3f} | {t['pf']:.2f} | {t['mdd']:.1f}R |\n"

    md = f"""# ORB v5 Walk-Forward Validation Report

**Strategy:** Opening Range Breakout v5 (LONG only + EMA50 1h + Bullish OR + TP={RR}R)  
**Symbol:** USATECHIDXUSD (US100)  
**Generated:** {now}

## Strategy Description

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | {RR}R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| OR bias filter | OR_close > OR_open (bullish OR) |
| Max trades/day | 1 |

## Walk-Forward Setup

| Window | Train Period | Test Period (OOS) |
|--------|-------------|-------------------|
| 1 | 2021–2023 (3yr) | 2024 (1yr) |
| 2 | 2022–2024 (3yr) | 2025 (1yr) |

No parameters are optimised — strategy rules are fixed.  
Training data is used only to confirm the edge exists before each out-of-sample window.

## Results Table

| Role | Period | Trades | T/yr | WR% | E(R) | PF | MaxDD |
|------|--------|--------|------|-----|------|----|-------|
{rows}{combined_row}
## Out-of-Sample Window Summary

| Year | Trades | WR% | E(R) | PF | MaxDD |
|------|--------|-----|------|----|-------|
{oos_yearly_rows}
## Combined OOS Stability Metrics

| Metric | Value |
|--------|-------|
| Avg R per trade | {m['avg_r']:+.4f} |
| Std R per trade | {m['std_r']:.4f} |
| Max consecutive losses | {m['max_consec_loss']} |
| Sharpe ratio (annualised) | {m['sharpe']:.2f} |

## Equity Curve

Equity curve and drawdown plots saved to `research/plots/`:

- `orb_v5_equity_curve.png`
- `orb_v5_drawdown_curve.png`

## Verdict: {verdict}

| Criterion | Required | Actual | Pass? |
|-----------|----------|--------|-------|
| Expectancy | > +0.07R | {m['er']:+.3f} | {'PASS' if m['er'] >= 0.07 else 'FAIL'} |
| Profit factor | >= 1.20 | {m['pf']:.2f} | {'PASS' if m['pf'] >= 1.20 else 'FAIL'} |
| Trades/year | >= 60 | {m['tpy']:.1f} | {'PASS' if m['tpy'] >= 60 else 'FAIL'} |
| Both OOS windows profitable | Yes | {'Yes' if all_oos_pos else 'No'} | {'PASS' if all_oos_pos else 'FAIL'} |

## Conclusion

{'The strategy demonstrates out-of-sample robustness across both walk-forward test windows.' if robust else 'The strategy does not yet meet all robustness criteria.'}

**Key observations:**

- Performance is {'consistent' if all_oos_pos else 'inconsistent'} across both OOS windows
- Combined OOS expectancy: {m['er']:+.3f} R (threshold: +0.07R)
- Combined OOS profit factor: {m['pf']:.2f} (threshold: 1.20)
- OOS trades/year: {m['tpy']:.1f} (threshold: 60)
- Max consecutive losses (OOS): {m['max_consec_loss']}
- Sharpe (annualised, OOS): {m['sharpe']:.2f}

{'The bullish OR + EMA50 filter combination appears to identify a repeatable edge.' if robust else 'Further research recommended before considering production deployment.'}

## Script

`strategies/OpeningRangeBreakout/research/orb_v5_walkforward.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading data ...")
    df_full = load_ltf(SYMBOL, TIMEFRAME)
    df_full = df_full[(df_full.index >= "2021-01-01") & (df_full.index < "2026-01-01")].copy()

    # Build EMA once on the full dataset so it is warm for all windows
    print("Building EMA50 (1h) on full dataset ...")
    df_full["ema50_1h"] = _build_ema50_1h(df_full)
    df_full["date"]     = df_full.index.normalize()

    print("Running walk-forward windows ...")
    window_metrics, test_dfs = run_walkforward(df_full)

    # Combined OOS trades
    all_test = pd.concat(test_dfs, ignore_index=True) if test_dfs else pd.DataFrame()
    combined = _metrics(all_test, label="Combined OOS")

    print_results(window_metrics, combined)

    if not all_test.empty:
        plot_equity_and_drawdown(all_test.sort_values("date").reset_index(drop=True))

    save_report(window_metrics, combined)
