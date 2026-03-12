# ORB GAP Threshold Sweep
# ========================
# Tests gap_ratio thresholds [0.0 (baseline), 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
# where gap_ratio = abs(14:30 open - prev 21:00 close) / ATR(14)
#
# Base: ORB v3 (LONG only + EMA50 1h + TP=1.6R)
#
# Key design: pre-build all v3 trade candidates once, then filter by threshold
# so the main loop runs only once regardless of how many thresholds are tested.
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_gap_threshold_sweep.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]   # .../US100
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf                   # noqa: E402
from bojkofx_shared.indicators.atr import calculate_atr         # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
START         = "2021-01-01"
END           = "2025-12-31"
OR_START_MIN  = 14 * 60 + 30
OR_END_MIN    = 15 * 60 + 0
SESSION_END_H = 21
RR            = 1.6
EMA_PERIOD    = 50
ATR_PERIOD    = 14

# 0.0 = no filter / v3 baseline
THRESHOLDS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

RESEARCH_DIR = Path(__file__).parent
OUTPUT_DIR   = RESEARCH_DIR / "output"
PLOTS_DIR    = RESEARCH_DIR / "plots"
CSV_PATH     = OUTPUT_DIR / "orb_gap_threshold_sweep_results.csv"
REPORT_PATH  = RESEARCH_DIR / "ORB_gap_threshold_sweep_report.md"


# ── helpers ───────────────────────────────────────────────────────────────────

def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _max_dd_r(r_series: pd.Series) -> float:
    equity = np.concatenate([[0.0], np.cumsum(r_series.values)])
    peaks  = np.maximum.accumulate(equity)
    return float((peaks - equity).max())


def _build_ema50_1h(df5m: pd.DataFrame) -> pd.Series:
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    return _ema(h1, EMA_PERIOD).reindex(df5m.index, method="ffill")


# ── core: build trade candidates in one pass ──────────────────────────────────

def build_trade_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run ORB v3 logic (EMA50 filter, no gap filter) over the full dataset.
    Returns one row per trade taken, enriched with gap_ratio for each day.

    All threshold variants can then be evaluated by simply filtering
      candidates[candidates["gap_ratio"] >= threshold]
    without re-running the loop.
    """
    df["ema50_1h"] = _build_ema50_1h(df)
    df["atr"]      = calculate_atr(df, period=ATR_PERIOD)
    df["date"]     = df.index.normalize()

    # Session close: last bar strictly before 21:00 UTC
    session_close = (
        df[df.index.hour < SESSION_END_H]
        .groupby("date")["close_bid"]
        .last()
    )

    records: list[dict] = []
    dates_sorted = sorted(df["date"].unique())

    for day_i, date in enumerate(dates_sorted):
        if day_i == 0:
            continue

        prev_date = dates_sorted[day_i - 1]
        if prev_date not in session_close.index:
            continue
        prev_close = session_close[prev_date]

        day = df[df["date"] == date].sort_index()

        # gap_ratio: use first bar at/after 14:30 as session open proxy
        or_open_bars = day[day.index.map(_bar_minutes) >= OR_START_MIN]
        if len(or_open_bars) == 0:
            continue
        current_open = or_open_bars.iloc[0]["open_bid"]

        atr_vals = day["atr"].dropna()
        if len(atr_vals) == 0:
            continue
        atr_val = atr_vals.iloc[0]
        if pd.isna(atr_val) or atr_val <= 0:
            continue

        gap_ratio = abs(current_open - prev_close) / atr_val

        # Opening range bars [14:30, 15:00)
        or_mask = (day.index.map(_bar_minutes) >= OR_START_MIN) & \
                  (day.index.map(_bar_minutes) <  OR_END_MIN)
        or_bars = day[or_mask]
        if len(or_bars) < 3:
            continue

        or_high = or_bars["high_bid"].max()
        or_low  = or_bars["low_bid"].min()
        if (or_high - or_low) <= 0:
            continue

        # Post-OR bars [15:00, 21:00)
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

            # EMA trend filter
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                break  # EMA blocked — skip rest of day

            remaining = post_bars.iloc[bar_i + 1:]
            if len(remaining) == 0:
                break

            entry_price = remaining.iloc[0]["open_bid"]
            sl          = or_low
            risk        = entry_price - sl
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
                eod_bars   = post_bars[post_bars.index < eod_cutoff]
                if len(eod_bars) == 0:
                    continue
                exit_price  = eod_bars.iloc[-1]["close_bid"]
                exit_reason = "EOD"

            records.append({
                "date":        str(date.date()),
                "year":        int(date.year),
                "gap_ratio":   round(gap_ratio, 4),
                "R":           round((exit_price - entry_price) / risk, 4),
                "exit_reason": exit_reason,
            })
            trade_taken = True

    return pd.DataFrame(records)


# ── metrics & sweep ───────────────────────────────────────────────────────────

def _metrics(tdf: pd.DataFrame) -> dict:
    if tdf.empty:
        return dict(trades=0, tpy=0.0, wr=0.0, er=0.0, pf=0.0,
                    mdd=0.0, tp_pct=0.0, eod_pct=0.0)
    n     = len(tdf)
    tpy   = n / tdf["year"].nunique()
    wr    = (tdf["R"] > 0).mean() * 100
    er    = tdf["R"].mean()
    gw    = tdf.loc[tdf["R"] > 0,  "R"].sum()
    gl    = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    pf    = gw / gl if gl > 0 else float("inf")
    mdd   = _max_dd_r(tdf["R"])
    vc    = tdf["exit_reason"].value_counts()
    return dict(
        trades   = n,
        tpy      = round(tpy,  1),
        wr       = round(wr,   1),
        er       = round(er,   3),
        pf       = round(pf,   2),
        mdd      = round(mdd,  1),
        tp_pct   = round(int(vc.get("TP",  0)) / n * 100, 1),
        eod_pct  = round(int(vc.get("EOD", 0)) / n * 100, 1),
    )


def run_sweep(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t in THRESHOLDS:
        sub = candidates[candidates["gap_ratio"] >= t]
        m   = _metrics(sub)
        rows.append({"threshold": t, **m})
    return pd.DataFrame(rows)


# ── console output ────────────────────────────────────────────────────────────

def print_table(summary: pd.DataFrame) -> None:
    SEP = "=" * 88
    print()
    print(SEP)
    print("  ORB GAP THRESHOLD SWEEP - US100 (USATECHIDXUSD)")
    print(SEP)
    print(f"  Period    : {START} -> {END}  |  Direction: LONG only  |  TP: {RR}R")
    print(f"  GAP def   : abs(14:30 open - prev 21:00 close) / ATR({ATR_PERIOD})")
    print(f"  thresholds: {THRESHOLDS}")
    print()
    H = f"  {'Threshold':>10}  {'Trades':>6}  {'T/yr':>5}  {'WR%':>6}  " \
        f"{'E(R)':>7}  {'PF':>5}  {'MaxDD':>7}  {'TP%':>6}  {'EOD%':>6}"
    print(H)
    print("  " + "-" * (len(H) - 2))
    for _, row in summary.iterrows():
        t_label = f"{row['threshold']:.1f}" + (" *" if row["threshold"] == 0.0 else "  ")
        print(
            f"  {t_label:>10}  {int(row['trades']):>6}  {row['tpy']:>5.1f}  "
            f"{row['wr']:>5.1f}%  {row['er']:>+7.3f}  {row['pf']:>5.2f}  "
            f"{row['mdd']:>6.1f}R  {row['tp_pct']:>5.1f}%  {row['eod_pct']:>5.1f}%"
        )
    print()
    print("  (* = 0.0 is v3 baseline, no gap filter)")
    print(SEP)
    print()


# ── best threshold selection ──────────────────────────────────────────────────

def select_best(summary: pd.DataFrame) -> pd.Series | None:
    # Exclude baseline (threshold=0.0)
    candidates = summary[summary["threshold"] > 0.0].copy()
    # Prefer trades/year >= 40
    viable = candidates[candidates["tpy"] >= 40]
    if viable.empty:
        viable = candidates
    # Sort: primary = expectancy, secondary = profit factor
    viable = viable.sort_values(["er", "pf"], ascending=False)
    return viable.iloc[0] if len(viable) > 0 else None


# ── plots ─────────────────────────────────────────────────────────────────────

def plot_results(summary: pd.DataFrame) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available -- skipping plots")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    # Split baseline vs thresholds
    base = summary[summary["threshold"] == 0.0].iloc[0]
    num  = summary[summary["threshold"] > 0.0].copy()
    xs   = [f"{t:.1f}" for t in num["threshold"]]

    # chart 1 – expectancy
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(xs, num["er"], color="steelblue", alpha=0.85)
    ax.axhline(base["er"], color="darkorange", linestyle="--", linewidth=1.5,
               label=f"v3 baseline ({base['er']:+.3f})")
    ax.axhline(0.08, color="green", linestyle=":", linewidth=1.0, label="target 0.08R")
    ax.set_xlabel("GAP threshold (ATR multiples)")
    ax.set_ylabel("Expectancy (R)")
    ax.set_title("ORB GAP Threshold Sweep – Expectancy per Threshold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, num["er"]):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + (0.001 if val >= 0 else -0.004),
                f"{val:+.3f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    p1 = PLOTS_DIR / "orb_gap_threshold_expectancy.png"
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    print(f"Plot saved: {p1}")

    # chart 2 – profit factor
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(xs, num["pf"], color="seagreen", alpha=0.85)
    ax.axhline(base["pf"], color="darkorange", linestyle="--", linewidth=1.5,
               label=f"v3 baseline ({base['pf']:.2f})")
    ax.axhline(1.20, color="green", linestyle=":", linewidth=1.0, label="target 1.20")
    ax.set_xlabel("GAP threshold (ATR multiples)")
    ax.set_ylabel("Profit Factor")
    ax.set_title("ORB GAP Threshold Sweep – Profit Factor per Threshold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, num["pf"]):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.005,
                f"{val:.2f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    p2 = PLOTS_DIR / "orb_gap_threshold_pf.png"
    fig.savefig(p2, dpi=120)
    plt.close(fig)
    print(f"Plot saved: {p2}")


# ── CSV + report ──────────────────────────────────────────────────────────────

def save_csv(summary: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(CSV_PATH, index=False)
    print(f"CSV saved:  {CSV_PATH}")


def save_report(summary: pd.DataFrame, best: pd.Series | None) -> None:
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    base = summary[summary["threshold"] == 0.0].iloc[0]

    # markdown table
    tbl  = "| Threshold | Trades | T/yr | WR% | E(R) | PF | MaxDD | TP% | EOD% |\n"
    tbl += "|-----------|--------|------|-----|------|----|-------|-----|------|\n"
    for _, row in summary.iterrows():
        label = f"{row['threshold']:.1f} (v3 base)" if row["threshold"] == 0.0 \
                else f"{row['threshold']:.1f} ATR"
        tbl += (f"| {label} | {int(row['trades'])} | {row['tpy']:.1f} | "
                f"{row['wr']:.1f}% | {row['er']:+.3f} | {row['pf']:.2f} | "
                f"{row['mdd']:.1f}R | {row['tp_pct']:.1f}% | {row['eod_pct']:.1f}% |\n")

    # best section
    if best is not None:
        meets = best["er"] >= 0.08 and best["pf"] >= 1.20 and best["tpy"] >= 40
        result_tag = "PASS" if meets else "FAIL"
        best_md = (
            f"## Best Threshold\n\n"
            f"**Recommended: {best['threshold']:.1f} ATR**  "
            f"({result_tag} – success criteria: E(R)>+0.08R, PF>=1.20, T/yr>=40)\n\n"
            f"| Metric | Value |\n|--------|-------|\n"
            f"| Trades | {int(best['trades'])} |\n"
            f"| T/yr | {best['tpy']:.1f} |\n"
            f"| Win rate | {best['wr']:.1f}% |\n"
            f"| Expectancy | {best['er']:+.3f} R |\n"
            f"| Profit factor | {best['pf']:.2f} |\n"
            f"| Max DD | {best['mdd']:.1f} R |\n"
        )
    else:
        best_md = "## Best Threshold\n\nInsufficient data to recommend a threshold.\n"

    # interpretation
    improved = summary[(summary["threshold"] > 0.0) & (summary["er"] > base["er"])]
    if len(improved) > 0:
        best_improved_er = improved["er"].max()
        interp_improve = (
            f"- **{len(improved)}/{len(THRESHOLDS)-1}** tested thresholds exceed "
            f"v3 baseline expectancy ({base['er']:+.3f} R); "
            f"best: E(R)={best_improved_er:+.3f}"
        )
    else:
        interp_improve = (
            f"- **No threshold** outperforms the v3 baseline expectancy ({base['er']:+.3f} R)"
        )

    # trade count trend note
    min_tpy = float(summary[summary["threshold"] > 0.0]["tpy"].min())
    max_tpy = float(summary[summary["threshold"] == 0.0]["tpy"].iloc[0])
    interp_count = (
        f"- Trades/year range: {min_tpy:.0f}–{max_tpy:.0f} across tested thresholds"
    )

    note_gap_dist = (
        "- Note: session-gap distribution on this dataset — P25≈0.07, P33≈2.0, P50≈6.5 ATR.  \n"
        "  Thresholds 0.1–0.6 primarily filter out the ~25% of days with near-zero overnight gap."
    )

    md = f"""# ORB GAP Threshold Sweep – Research Report

**Strategy:** Opening Range Breakout + GAP filter  
**Symbol:** USATECHIDXUSD (US100) | **Period:** {START} → {END} | **Timeframe:** 5min  
**Generated:** {now}

## Strategy Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR high |
| Stop loss | OR low |
| Take profit | {RR}R |
| EOD close | 21:00 UTC |
| Trend filter | close > EMA50 (1h bars) |
| GAP definition | abs(14:30 open − prev 21:00 close) / ATR({ATR_PERIOD}) |
| Max trades/day | 1 |

## Thresholds Tested

`{THRESHOLDS}` (0.0 = no filter / v3 baseline)

## Results Table

{tbl}

{best_md}

## Interpretation

{interp_improve}  
{interp_count}  
{note_gap_dist}

### Does a moderate GAP filter improve ORB?

Based on the sweep, small thresholds (0.1–0.6 ATR multiples) filter only the
~25% of days with near-zero overnight session gaps.  Effectiveness depends on
whether those low-gap days are systematically worse for ORB setups.

### Should this filter be kept for the next ORB iteration?

Only if at least one tested threshold shows clear improvement over v3 on both
expectancy (+0.08R) and profit factor (1.20) while maintaining ≥40 trades/year.
See best-threshold section above for the verdict.

## Outputs

| File | Description |
|------|-------------|
| `research/output/orb_gap_threshold_sweep_results.csv` | Full numeric results |
| `research/plots/orb_gap_threshold_expectancy.png` | Expectancy bar chart |
| `research/plots/orb_gap_threshold_pf.png` | Profit factor bar chart |

## Script

`strategies/OpeningRangeBreakout/research/orb_gap_threshold_sweep.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading data ...")
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    print("Building ORB v3 trade candidates (one pass) ...")
    candidates = build_trade_candidates(df)
    print(f"  Base candidates (v3, no gap filter): {len(candidates)} trades")

    print("Running sweep ...")
    summary = run_sweep(candidates)

    print_table(summary)

    best = select_best(summary)
    if best is not None:
        t = best["threshold"]
        meets = best["er"] >= 0.08 and best["pf"] >= 1.20 and best["tpy"] >= 40
        print(f"Best practical threshold: {t:.1f} ATR"
              f"  [E(R)={best['er']:+.3f}  PF={best['pf']:.2f}  T/yr={best['tpy']:.1f}]"
              f"  -> {'PASS' if meets else 'FAIL'}")
        print()

    plot_results(summary)
    save_csv(summary)
    save_report(summary, best)
