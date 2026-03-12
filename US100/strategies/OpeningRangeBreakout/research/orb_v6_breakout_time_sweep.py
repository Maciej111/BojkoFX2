# ORB v6 – Breakout Time Sweep
# =============================
# Base: ORB v5 (LONG only + EMA50 1h + bullish OR + TP=1.6R)
# New:  Vary the breakout entry cutoff hour to test if earlier breakouts
#       produce better results.
#
# Strategy: build all ORB v5 trade candidates in one pass (recording the
# breakout bar hour), then sweep cutoff hours without re-running the loop.
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v6_breakout_time_sweep.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf           # noqa: E402

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

# 21:00 = v5 baseline (no effective restriction within the session)
CUTOFFS = [16, 17, 18, 19, 21]   # hours UTC; 16 → entry bar close must be <=16:00

# v5 full-period reference
V5 = dict(trades=426, wr=54.5, er=+0.093, pf=1.25, mdd=9.5, tp_pct=15.0, eod_pct=51.9)

RESEARCH_DIR = Path(__file__).parent
OUTPUT_DIR   = RESEARCH_DIR / "output"
PLOTS_DIR    = RESEARCH_DIR / "plots"
CSV_PATH     = OUTPUT_DIR / "orb_v6_breakout_time_sweep_results.csv"
REPORT_PATH  = RESEARCH_DIR / "ORB_v6_breakout_time_sweep_report.md"


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


def _metrics(tdf: pd.DataFrame, cutoff: int) -> dict:
    if tdf.empty:
        return dict(cutoff=cutoff, trades=0, tpy=0.0, wr=0.0, er=0.0, pf=0.0,
                    mdd=0.0, tp_pct=0.0, eod_pct=0.0, avg_r=0.0, std_r=0.0, mcl=0)
    n   = len(tdf)
    yrs = tdf["year"].nunique()
    vc  = tdf["exit_reason"].value_counts()
    gw  = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl  = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    return dict(
        cutoff  = cutoff,
        trades  = n,
        tpy     = round(n / yrs, 1),
        wr      = round((tdf["R"] > 0).mean() * 100, 1),
        er      = round(tdf["R"].mean(), 3),
        pf      = round(gw / gl if gl > 0 else float("inf"), 2),
        mdd     = round(_max_dd_r(tdf["R"]), 1),
        tp_pct  = round(int(vc.get("TP",  0)) / n * 100, 1),
        eod_pct = round(int(vc.get("EOD", 0)) / n * 100, 1),
        avg_r   = round(tdf["R"].mean(),  4),
        std_r   = round(tdf["R"].std(),   4),
        mcl     = _max_consec_losses(tdf["R"]),
    )


# ── one-pass candidate builder (ORB v5 logic + breakout hour recorded) ────────

def build_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run ORB v5 logic on the full dataset, recording breakout_hour for each
    trade.  The sweep then filters candidates by cutoff without another loop.
    """
    df["ema50_1h"] = _build_ema50_1h(df)
    df["date"]     = df.index.normalize()

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

        for bar_i, (ts, bar) in enumerate(post_bars.iterrows()):
            if bar["close_bid"] <= or_high:
                continue
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                break  # EMA blocked — no trade today

            breakout_hour = ts.hour   # hour of the breakout signal bar

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
                eod_cutoff_ts = post_bars.index[0].replace(
                    hour=SESSION_END_H, minute=0, second=0)
                eod_bars = post_bars[post_bars.index < eod_cutoff_ts]
                if len(eod_bars) == 0:
                    break
                exit_price  = eod_bars.iloc[-1]["close_bid"]
                exit_reason = "EOD"

            records.append({
                "date":         str(date.date()),
                "year":         int(date.year),
                "breakout_hour": breakout_hour,
                "R":            round((exit_price - entry_price) / risk, 4),
                "exit_reason":  exit_reason,
            })
            break   # max 1 trade per day

    return pd.DataFrame(records)


# ── sweep ─────────────────────────────────────────────────────────────────────

def run_sweep(candidates: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    rows:    list[dict]         = []
    subsets: dict[int, pd.DataFrame] = {}
    for co in CUTOFFS:
        sub = candidates[candidates["breakout_hour"] <= co].copy()
        rows.append(_metrics(sub, co))
        subsets[co] = sub
    return pd.DataFrame(rows), subsets


# ── best cutoff selection ─────────────────────────────────────────────────────

def select_best(summary: pd.DataFrame) -> pd.Series:
    viable = summary[summary["tpy"] >= 60].copy()
    if viable.empty:
        viable = summary.copy()
    return viable.sort_values(["er", "pf"], ascending=False).iloc[0]


# ── console output ────────────────────────────────────────────────────────────

def print_table(summary: pd.DataFrame, best_co: int) -> None:
    SEP = "=" * 92
    print()
    print(SEP)
    print("  ORB v6 BREAKOUT TIME SWEEP - US100 (USATECHIDXUSD)")
    print(SEP)
    print(f"  Base   : ORB v5 (LONG + EMA50 1h + bullish OR + TP={RR}R)")
    print(f"  Filter : breakout bar hour <= cutoff  |  cutoffs: {[f'{c:02d}:00' for c in CUTOFFS]}")
    print()
    H = (f"  {'Cutoff':>8}  {'Trades':>6}  {'T/yr':>5}  {'WR%':>6}  "
         f"{'E(R)':>7}  {'PF':>5}  {'MaxDD':>7}  {'TP%':>6}  {'MCL':>4}")
    print(H)
    print("  " + "-" * (len(H) - 2))
    for _, row in summary.iterrows():
        co    = int(row["cutoff"])
        marker = " *" if co == best_co else "  "
        base_m = " <- v5 baseline" if co == 21 else ""
        print(
            f"  {co:02d}:00{marker}  {int(row['trades']):>6}  {row['tpy']:>5.1f}  "
            f"{row['wr']:>5.1f}%  {row['er']:>+7.3f}  {row['pf']:>5.2f}  "
            f"{row['mdd']:>6.1f}R  {row['tp_pct']:>5.1f}%  {int(row['mcl']):>4}{base_m}"
        )
    print()
    print(f"  (* best cutoff by expectancy with T/yr >= 60)")
    print()
    b = summary[summary["cutoff"] == best_co].iloc[0]
    print(f"  Best practical cutoff: {best_co:02d}:00 UTC")
    print(f"    E(R)={b['er']:+.3f}  PF={b['pf']:.2f}  T/yr={b['tpy']:.1f}  MaxDD={b['mdd']:.1f}R  MCL={int(b['mcl'])}")
    meets = b["er"] >= 0.10 and b["pf"] >= 1.30 and b["tpy"] >= 60
    print(f"    Verdict: {'PASS' if meets else 'FAIL'} "
          f"(E(R)>+0.10R, PF>=1.30, T/yr>=60)")
    print(SEP)
    print()


# ── plots ─────────────────────────────────────────────────────────────────────

CUTOFF_COLORS = {16: "#1f77b4", 17: "#2ca02c", 18: "#ff7f0e",
                 19: "#9467bd", 21: "#d62728"}
CUTOFF_LABELS = {16: "16:00", 17: "17:00", 18: "18:00", 19: "19:00", 21: "21:00 (v5)"}


def plot_combined(subsets: dict[int, pd.DataFrame], best_co: int) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available -- skipping plots")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1 – combined equity curves
    fig, ax = plt.subplots(figsize=(11, 5))
    for co in CUTOFFS:
        tdf = subsets[co]
        if tdf.empty:
            continue
        eq = np.concatenate([[0.0], np.cumsum(tdf["R"].values)])
        lw  = 2.0 if co == best_co else 1.0
        ax.plot(eq, label=CUTOFF_LABELS[co], color=CUTOFF_COLORS[co], linewidth=lw)
    ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative R")
    ax.set_title("ORB v6 Breakout Time Sweep – Equity Curves")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = PLOTS_DIR / "orb_v6_equity_curves.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    print(f"Plot saved: {p}")

    # 2 – combined drawdown curves
    fig, ax = plt.subplots(figsize=(11, 4))
    for co in CUTOFFS:
        tdf = subsets[co]
        if tdf.empty:
            continue
        eq   = np.concatenate([[0.0], np.cumsum(tdf["R"].values)])
        dd   = np.maximum.accumulate(eq) - eq
        lw   = 2.0 if co == best_co else 1.0
        ax.plot(-dd, label=CUTOFF_LABELS[co], color=CUTOFF_COLORS[co], linewidth=lw)
    ax.axhline(0, color="black", linewidth=0.7, linestyle="--")
    ax.set_xlabel("Trade # (0 = equity start)")
    ax.set_ylabel("Drawdown (R)")
    ax.set_title("ORB v6 Breakout Time Sweep – Drawdown Curves")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = PLOTS_DIR / "orb_v6_drawdown_curves.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    print(f"Plot saved: {p}")

    # 3 – best cutoff: separate equity + drawdown
    tdf_best = subsets[best_co]
    if not tdf_best.empty:
        eq_best = np.concatenate([[0.0], np.cumsum(tdf_best["R"].values)])
        dd_best = np.maximum.accumulate(eq_best) - eq_best

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7),
                                        gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(eq_best, color=CUTOFF_COLORS[best_co], linewidth=1.8)
        ax1.axhline(0, color="black", linewidth=0.7, linestyle="--")
        ax1.set_ylabel("Cumulative R")
        ax1.set_title(f"ORB v6 Best Cutoff ({best_co:02d}:00 UTC) – Equity & Drawdown")
        ax1.grid(alpha=0.3)

        ax2.fill_between(range(len(dd_best)), -dd_best, 0,
                         color="tomato", alpha=0.6)
        ax2.plot(-dd_best, color="firebrick", linewidth=1.0)
        ax2.axhline(0, color="black", linewidth=0.7, linestyle="--")
        ax2.set_xlabel("Trade #")
        ax2.set_ylabel("Drawdown (R)")
        ax2.grid(alpha=0.3)

        fig.tight_layout()
        p = PLOTS_DIR / "orb_v6_best_equity_curve.png"
        fig.savefig(p, dpi=120)
        plt.close(fig)
        print(f"Plot saved: {p}")


# ── CSV ───────────────────────────────────────────────────────────────────────

def save_csv(summary: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = summary.rename(columns={
        "cutoff": "cutoff_hour_utc",
        "tpy":    "trades_per_year",
        "wr":     "win_rate",
        "er":     "expectancy_r",
        "pf":     "profit_factor",
        "mdd":    "max_dd_r",
        "tp_pct": "tp_hit_rate",
        "eod_pct":"eod_exit_rate",
        "mcl":    "max_consecutive_losses",
    })
    out.to_csv(CSV_PATH, index=False)
    print(f"CSV saved:  {CSV_PATH}")


# ── markdown report ───────────────────────────────────────────────────────────

def save_report(summary: pd.DataFrame, subsets: dict, best_co: int) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    b     = summary[summary["cutoff"] == best_co].iloc[0]
    v5_row = summary[summary["cutoff"] == 21].iloc[0]
    meets = b["er"] >= 0.10 and b["pf"] >= 1.30 and b["tpy"] >= 60
    verdict = "**Promising**" if meets else "**Not yet convincing**"

    # result table
    tbl  = "| Cutoff | Trades | T/yr | WR% | E(R) | PF | MaxDD | TP% | EOD% | MCL |\n"
    tbl += "|--------|--------|------|-----|------|----|-------|-----|------|-----|\n"
    for _, row in summary.iterrows():
        co = int(row["cutoff"])
        tag = " (v5 base)" if co == 21 else (" ← best" if co == best_co else "")
        tbl += (f"| {co:02d}:00{tag} | {int(row['trades'])} | {row['tpy']:.1f} | "
                f"{row['wr']:.1f}% | {row['er']:+.3f} | {row['pf']:.2f} | "
                f"{row['mdd']:.1f}R | {row['tp_pct']:.1f}% | {row['eod_pct']:.1f}% | "
                f"{int(row['mcl'])} |\n")

    # comparison vs v5
    delta_er  = b["er"]  - V5["er"]
    delta_pf  = b["pf"]  - V5["pf"]
    delta_mdd = b["mdd"] - V5["mdd"]
    delta_n   = int(b["trades"]) - V5["trades"]
    cmp_tbl = (
        "| Metric | ORB v5 | ORB v6 best | Delta |\n"
        "|--------|--------|-------------|-------|\n"
        f"| Trades | {V5['trades']} | {int(b['trades'])} | {delta_n:+d} |\n"
        f"| Win rate | {V5['wr']:.1f}% | {b['wr']:.1f}% | {b['wr']-V5['wr']:+.1f}pp |\n"
        f"| Expectancy R | {V5['er']:+.3f} | {b['er']:+.3f} | {delta_er:+.3f} |\n"
        f"| Profit factor | {V5['pf']:.2f} | {b['pf']:.2f} | {delta_pf:+.2f} |\n"
        f"| Max DD (R) | {V5['mdd']:.1f}R | {b['mdd']:.1f}R | {delta_mdd:+.1f}R |\n"
        f"| TP hit rate | {V5['tp_pct']:.1f}% | {b['tp_pct']:.1f}% | {b['tp_pct']-V5['tp_pct']:+.1f}pp |\n"
        f"| EOD exits | {V5['eod_pct']:.1f}% | {b['eod_pct']:.1f}% | {b['eod_pct']-V5['eod_pct']:+.1f}pp |\n"
    )

    # yearly table for best cutoff
    tdf_best = subsets[best_co]
    yr_tbl = ""
    if not tdf_best.empty:
        yr_tbl = "| Year | Trades | WR% | E(R) | PF |\n|------|--------|-----|------|----|  \n"
        for yr, g in tdf_best.groupby("year"):
            gw = g.loc[g["R"] > 0, "R"].sum()
            gl = abs(g.loc[g["R"] < 0, "R"].sum())
            pf_yr = round(gw / gl if gl > 0 else float("inf"), 2)
            yr_tbl += (f"| {yr} | {len(g)} | {(g['R']>0).mean()*100:.1f}% | "
                       f"{g['R'].mean():+.3f} | {pf_yr:.2f} |\n")

    # stability obs
    mdd_trend = "improves" if b["mdd"] < V5["mdd"] else "worsens"
    er_trend  = "improves" if b["er"]  > V5["er"]  else "does not improve"

    replace_v5 = meets and delta_er > 0 and delta_pf > 0 and delta_mdd <= 0

    md = f"""# ORB v6 Breakout Time Sweep – Research Report

**Strategy:** Opening Range Breakout v5 + breakout time cutoff filter  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** {START} → {END}  
**Generated:** {now}

## Strategy Description

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after breakout close ≤ cutoff hour |
| Stop loss | OR_low |
| Take profit | {RR}R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| OR bias filter | OR_close > OR_open (bullish OR) |
| **Breakout cutoff** | **varied — see below** |

## Tested Cutoffs

`{[f"{c:02d}:00 UTC" for c in CUTOFFS]}`

Breakout signal bar (the 5-min bar whose close exceeds OR_high) must have a
timestamp **≤ cutoff hour**.  21:00 = ORB v5 baseline (no effective restriction).

## Results Table

{tbl}
## Best Cutoff

**Recommended: {best_co:02d}:00 UTC** — {verdict}

Success criteria: E(R) > +0.10R, PF ≥ 1.30, T/yr ≥ 60

| Metric | Value |
|--------|-------|
| Trades | {int(b['trades'])} |
| T/yr | {b['tpy']:.1f} |
| Win rate | {b['wr']:.1f}% |
| Expectancy | {b['er']:+.3f} R |
| Profit factor | {b['pf']:.2f} |
| Max DD | {b['mdd']:.1f} R |
| MCL | {int(b['mcl'])} |

### Yearly breakdown (best cutoff)

{yr_tbl}

## Equity Curve Summary

Plots saved to `research/plots/`:

| File | Description |
|------|-------------|
| `orb_v6_equity_curves.png` | All cutoffs overlaid |
| `orb_v6_drawdown_curves.png` | All cutoffs overlaid |
| `orb_v6_best_equity_curve.png` | Best cutoff only (equity + DD) |

## Comparison vs ORB v5

{cmp_tbl}

## Stability Observations

- Expectancy {er_trend} with a {best_co:02d}:00 cutoff vs ORB v5 baseline
- Max drawdown {mdd_trend} with the restriction in place
- Earlier cutoffs capture higher-conviction early breakouts
  (they trade only days where price moves away from OR quickly)
- EOD exit rate {'falls' if b['eod_pct'] < V5['eod_pct'] else 'rises'} with tighter cutoffs,
  indicating shorter hold times when breakouts are early

## Conclusion

**Should ORB v6 replace ORB v5 as new baseline?**  
{'Yes — the best breakout cutoff materially improves all key metrics.' if replace_v5 else 'Not conclusively — further investigation or a different cutoff range may be needed.'}

| Criterion | Pass? |
|-----------|-------|
| E(R) > +0.10R | {'PASS' if b['er'] >= 0.10 else 'FAIL'} ({b['er']:+.3f}) |
| PF ≥ 1.30 | {'PASS' if b['pf'] >= 1.30 else 'FAIL'} ({b['pf']:.2f}) |
| T/yr ≥ 60 | {'PASS' if b['tpy'] >= 60 else 'FAIL'} ({b['tpy']:.1f}) |
| Lower DD than v5 | {'PASS' if b['mdd'] < V5['mdd'] else 'FAIL'} ({b['mdd']:.1f}R vs {V5['mdd']:.1f}R) |

## Script

`strategies/OpeningRangeBreakout/research/orb_v6_breakout_time_sweep.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading data ...")
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    print("Building ORB v5 trade candidates (one pass) ...")
    candidates = build_candidates(df)
    print(f"  Base candidates (v5): {len(candidates)} trades")
    if not candidates.empty:
        dist = candidates["breakout_hour"].value_counts().sort_index()
        print("  Breakout hour distribution:")
        for h, cnt in dist.items():
            print(f"    {h:02d}:xx UTC  {cnt:4d} trades")

    print("\nRunning cutoff sweep ...")
    summary, subsets = run_sweep(candidates)

    best = select_best(summary)
    best_co = int(best["cutoff"])

    print_table(summary, best_co)
    plot_combined(subsets, best_co)
    save_csv(summary)
    save_report(summary, subsets, best_co)
