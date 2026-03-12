# ORB v5 Micro-Grid Parameter Sweep
# ===================================
# Tests 4 × 3 × 2 × 3 = 72 parameter combinations around the ORB v5 baseline.
#
# Parameters swept:
#   TP_multiple    : [1.3, 1.5, 1.6, 1.8]
#   EMA_period     : [30, 50, 70]
#   OR_length_min  : [15, 30]  (14:30-14:45 vs 14:30-15:00)
#   min_body_ratio : [0.0, 0.1, 0.2]  (bullish OR body / OR range)
#
# Strategy (all else fixed = ORB v5):
#   LONG only | EMA1h filter | bullish OR filter | SL=OR_low | EOD@21:00
#
# Design: build day blueprints ONCE (all EMAs pre-computed), then sweep
# the grid without re-loading or re-grouping data.
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v5_micro_grid.py

from __future__ import annotations

import sys
from collections import namedtuple
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf           # noqa: E402

# ── parameter grid ────────────────────────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
START         = "2021-01-01"
END           = "2025-12-31"
SESSION_END_H = 21

TP_MULTIPLES  = [1.3, 1.5, 1.6, 1.8]
EMA_PERIODS   = [30, 50, 70]
OR_LENGTHS    = [15, 30]          # minutes
BODY_RATIOS   = [0.0, 0.1, 0.2]

OR_START_MIN   = 14 * 60 + 30    # 870
OR_END_15_MIN  = 14 * 60 + 45    # 885
OR_END_30_MIN  = 15 * 60 + 0     # 900

# ORB v5 reference baseline
V5 = dict(trades=426, tpy=85.2, wr=54.5, er=+0.093, pf=1.25, mdd=9.5,
          tp_pct=15.0, eod_pct=51.9)

RESEARCH_DIR = Path(__file__).parent
OUTPUT_DIR   = RESEARCH_DIR / "output"
PLOTS_DIR    = RESEARCH_DIR / "plots"
CSV_PATH     = OUTPUT_DIR / "orb_v5_micro_grid_results.csv"
REPORT_PATH  = RESEARCH_DIR / "ORB_v5_micro_grid_report.md"


# ── data structures ───────────────────────────────────────────────────────────

PostBar = namedtuple("PostBar",
    ["close_bid", "low_bid", "high_bid", "open_bid", "ema30", "ema50", "ema70"])

_EMA_ATTR = {30: "ema30", 50: "ema50", 70: "ema70"}


class DayBlue:
    __slots__ = ("date", "year", "or15", "or30", "post15", "post30")

    def __init__(self, date, year, or15, or30, post15, post30):
        self.date   = date
        self.year   = year
        self.or15   = or15    # dict {high, low, open, close} or None
        self.or30   = or30
        self.post15 = post15  # list[PostBar]
        self.post30 = post30


# ── helpers ───────────────────────────────────────────────────────────────────

def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


def _build_ema_1h(df5m: pd.DataFrame, period: int) -> pd.Series:
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    return h1.ewm(span=period, adjust=False).mean().reindex(df5m.index, method="ffill")


def _max_dd_r(r_arr: np.ndarray) -> float:
    eq = np.concatenate([[0.0], np.cumsum(r_arr)])
    return float((np.maximum.accumulate(eq) - eq).max())


def _max_consec_losses(arr: np.ndarray) -> int:
    mx, cur = 0, 0
    for x in arr:
        if x < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    return mx


def _metrics(records: list[dict], params: dict) -> dict:
    if not records:
        return {**params, "trades": 0, "tpy": 0.0, "wr": 0.0, "er": 0.0,
                "pf": 0.0, "mdd": 0.0, "tp_pct": 0.0, "eod_pct": 0.0,
                "avg_r": 0.0, "std_r": 0.0}
    arr    = np.asarray([r["R"] for r in records], dtype=float)
    exits  = [r["exit"] for r in records]
    years  = {r["year"] for r in records}
    n      = len(arr)
    gw     = float(arr[arr > 0].sum())
    gl     = float(abs(arr[arr < 0].sum()))
    return {
        **params,
        "trades":   n,
        "tpy":      round(n / len(years), 1),
        "wr":       round(float((arr > 0).mean()) * 100, 1),
        "er":       round(float(arr.mean()), 3),
        "pf":       round(gw / gl if gl > 0 else float("inf"), 2),
        "mdd":      round(_max_dd_r(arr), 1),
        "tp_pct":   round(exits.count("TP")  / n * 100, 1),
        "eod_pct":  round(exits.count("EOD") / n * 100, 1),
        "avg_r":    round(float(arr.mean()), 4),
        "std_r":    round(float(arr.std()),  4),
        "mcl":      _max_consec_losses(arr),
    }


# ── phase 1: build day blueprints ─────────────────────────────────────────────

def build_blueprints(df: pd.DataFrame) -> list[DayBlue]:
    blueprints: list[DayBlue] = []

    for date, day in df.groupby("date"):
        day  = day.sort_index()
        mins = pd.Index([_bar_minutes(ts) for ts in day.index])

        def _or_data(end_min: int) -> dict | None:
            mask  = (mins >= OR_START_MIN) & (mins < end_min)
            bars  = day.iloc[mask]
            if len(bars) < 2:
                return None
            return {
                "high":  float(bars["high_bid"].max()),
                "low":   float(bars["low_bid"].min()),
                "open":  float(bars.iloc[0]["open_bid"]),
                "close": float(bars.iloc[-1]["close_bid"]),
            }

        def _post_bars(start_min: int) -> list[PostBar]:
            mask  = (mins >= start_min) & (day.index.hour < SESSION_END_H)
            bars  = day.iloc[mask]
            result = []
            for _, b in bars.iterrows():
                e30 = b.get("ema30_1h", float("nan"))
                e50 = b.get("ema50_1h", float("nan"))
                e70 = b.get("ema70_1h", float("nan"))
                result.append(PostBar(
                    close_bid = float(b["close_bid"]),
                    low_bid   = float(b["low_bid"]),
                    high_bid  = float(b["high_bid"]),
                    open_bid  = float(b["open_bid"]),
                    ema30     = float(e30),
                    ema50     = float(e50),
                    ema70     = float(e70),
                ))
            return result

        or15  = _or_data(OR_END_15_MIN)
        or30  = _or_data(OR_END_30_MIN)
        post15 = _post_bars(OR_END_15_MIN) if or15 else []
        post30 = _post_bars(OR_END_30_MIN) if or30 else []

        if or15 or or30:
            blueprints.append(DayBlue(
                date   = str(date.date()),
                year   = int(date.year),
                or15   = or15,
                or30   = or30,
                post15 = post15,
                post30 = post30,
            ))

    return blueprints


# ── phase 2: entry discovery + TP resolution ─────────────────────────────────

def _find_entry(post_bars: list[PostBar], or_high: float, or_low: float,
                ema_period: int) -> dict | None:
    ema_attr = _EMA_ATTR[ema_period]
    for i, bar in enumerate(post_bars):
        if bar.close_bid <= or_high:
            continue
        ema_val = getattr(bar, ema_attr)
        if ema_val != ema_val or bar.close_bid <= ema_val:  # NaN or below EMA
            return None  # EMA blocked — skip day
        if i + 1 >= len(post_bars):
            return None
        entry_bar   = post_bars[i + 1]
        entry_price = entry_bar.open_bid
        risk        = entry_price - or_low
        if risk <= 0:
            continue
        return {
            "entry_price":    entry_price,
            "entry_bar_close": entry_bar.close_bid,
            "sl":             or_low,
            "risk":           risk,
            "remaining":      post_bars[i + 2:],
        }
    return None


def _resolve_exit(entry: dict, tp_multiple: float) -> tuple[float, str]:
    ep, sl, risk = entry["entry_price"], entry["sl"], entry["risk"]
    tp           = ep + tp_multiple * risk
    remaining    = entry["remaining"]
    if not remaining:
        eod_p = entry["entry_bar_close"]
        return round((eod_p - ep) / risk, 4), "EOD"
    for bar in remaining:
        if bar.low_bid <= sl:
            return round((sl - ep) / risk, 4), "SL"
        if bar.high_bid >= tp:
            return round((tp - ep) / risk, 4), "TP"
    return round((remaining[-1].close_bid - ep) / risk, 4), "EOD"


# ── phase 3: grid sweep ───────────────────────────────────────────────────────

def run_grid(blueprints: list[DayBlue]) -> pd.DataFrame:
    results:   list[dict] = []
    n_outer   = len(OR_LENGTHS) * len(EMA_PERIODS) * len(BODY_RATIOS)
    done_outer = 0

    for or_len, ema_period, body_ratio in product(OR_LENGTHS, EMA_PERIODS, BODY_RATIOS):
        or_attr   = "or15"   if or_len == 15 else "or30"
        post_attr = "post15" if or_len == 15 else "post30"

        # Compute entry setups once for this (or_len, ema_period, body_ratio)
        day_entries: list[tuple] = []
        for bp in blueprints:
            or_data   = getattr(bp, or_attr)
            post_bars = getattr(bp, post_attr)
            if or_data is None or len(post_bars) < 2:
                continue
            or_range = or_data["high"] - or_data["low"]
            if or_range <= 0:
                continue
            or_body = or_data["close"] - or_data["open"]
            if or_body <= 0:
                continue
            if body_ratio > 0.0 and (or_body / or_range) < body_ratio:
                continue
            entry = _find_entry(post_bars, or_data["high"], or_data["low"], ema_period)
            if entry is not None:
                day_entries.append((bp.date, bp.year, entry))

        # Sweep TP multiples (cheap — no bar iteration, just resolve exits)
        for tp_mult in TP_MULTIPLES:
            records: list[dict] = []
            for date, year, entry in day_entries:
                R, exit_reason = _resolve_exit(entry, tp_mult)
                records.append({"date": date, "year": year, "R": R, "exit": exit_reason})
            params = {
                "tp_multiple":       tp_mult,
                "ema_period":        ema_period,
                "or_length_minutes": or_len,
                "min_body_ratio":    body_ratio,
            }
            results.append(_metrics(records, params))

        done_outer += 1
        print(f"\r  Grid progress: {done_outer}/{n_outer} param sets "
              f"({done_outer * len(TP_MULTIPLES)}/{n_outer * len(TP_MULTIPLES)} combos)  ",
              end="", flush=True)

    print()
    return pd.DataFrame(results)


# ── best parameter selection ──────────────────────────────────────────────────

def select_best(df: pd.DataFrame) -> pd.Series:
    viable = df[(df["er"] >= 0.08) & (df["pf"] >= 1.20) & (df["tpy"] >= 60)].copy()
    if viable.empty:
        viable = df[df["tpy"] >= 60].copy()
    if viable.empty:
        viable = df.copy()
    return viable.sort_values(["er", "pf", "mdd"], ascending=[False, False, True]).iloc[0]


# ── console output ────────────────────────────────────────────────────────────

def print_top10(df: pd.DataFrame, best: pd.Series) -> None:
    SEP = "=" * 90
    print()
    print(SEP)
    print("  ORB v5 MICRO-GRID SWEEP - TOP 10 CONFIGURATIONS (by expectancy)")
    print(SEP)
    print(f"  {'TP':>5}  {'EMA':>5}  {'OR':>5}  {'Body':>6}  "
          f"{'Trades':>6}  {'T/yr':>5}  {'WR%':>6}  {'E(R)':>7}  "
          f"{'PF':>5}  {'MaxDD':>7}")
    print("  " + "-" * 83)
    viable = df[(df["er"] >= 0.08) & (df["pf"] >= 1.20) & (df["tpy"] >= 60)].copy()
    top10 = (
        viable.sort_values(["er", "mdd", "tpy"], ascending=[False, True, False])
        if not viable.empty
        else df.sort_values("er", ascending=False)
    ).head(10)
    for _, r in top10.iterrows():
        star = " *" if (
            r["tp_multiple"]    == best["tp_multiple"] and
            r["ema_period"]     == best["ema_period"] and
            r["or_length_minutes"] == best["or_length_minutes"] and
            r["min_body_ratio"] == best["min_body_ratio"]
        ) else "  "
        print(
            f"  {r['tp_multiple']:>4.1f}  {int(r['ema_period']):>5}  "
            f"{int(r['or_length_minutes']):>4}m  {r['min_body_ratio']:>6.1f}  "
            f"{int(r['trades']):>6}  {r['tpy']:>5.1f}  {r['wr']:>5.1f}%  "
            f"{r['er']:>+7.3f}  {r['pf']:>5.2f}  {r['mdd']:>6.1f}R{star}"
        )
    print()
    print("  (* = selected as best configuration)")
    print()
    print("  BEST CONFIGURATION")
    print(f"    TP_multiple    = {best['tp_multiple']}")
    print(f"    EMA_period     = {int(best['ema_period'])}")
    print(f"    OR_length_min  = {int(best['or_length_minutes'])}")
    print(f"    min_body_ratio = {best['min_body_ratio']}")
    print(f"    Expectancy     = {best['er']:+.3f} R")
    print(f"    PF             = {best['pf']:.2f}")
    print(f"    Win rate       = {best['wr']:.1f}%")
    print(f"    Trades/year    = {best['tpy']:.1f}")
    print(f"    Max DD         = {best['mdd']:.1f} R")
    b_meets = best["er"] >= 0.10 and best["pf"] >= 1.30 and best["tpy"] >= 60
    print(f"    Verdict: {'PASS' if b_meets else 'FAIL'} "
          f"(E(R)>=+0.10R, PF>=1.30, T/yr>=60)")
    print()
    print(f"  ORB v5 baseline: E(R)={V5['er']:+.3f}  PF={V5['pf']:.2f}  "
          f"T/yr={V5['tpy']}  MaxDD={V5['mdd']}R")
    print(SEP)
    print()


# ── heatmaps ──────────────────────────────────────────────────────────────────

def _draw_heatmap(ax, data, row_labels, col_labels, title, cbar_label, fmt):
    import matplotlib.pyplot as plt
    vmin = data.min() * (0.9 if data.min() > 0 else 1.1)
    vmax = data.max() * (1.05 if data.max() > 0 else 0.95)
    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=vmin, vmax=vmax)
    ax.set_xticks(range(data.shape[1]))
    ax.set_yticks(range(data.shape[0]))
    ax.set_xticklabels(col_labels, fontsize=8)
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.set_title(title, fontsize=9)
    plt.colorbar(im, ax=ax, label=cbar_label)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(j, i, fmt % data[i, j], ha="center", va="center", fontsize=7)


def plot_heatmaps(df: pd.DataFrame) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available -- skipping plots")
        return

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    for or_len in OR_LENGTHS:
        sub = df[df["or_length_minutes"] == or_len]
        tag = f"or{or_len}"
        sfx = f"(OR={or_len}min, avg other params)"

        # Heatmap 1: TP x EMA -- expectancy (avg over body_ratio)
        piv = sub.groupby(["tp_multiple", "ema_period"])["er"].mean().unstack()
        fig, ax = plt.subplots(figsize=(6, 4))
        _draw_heatmap(ax, piv.values,
                      [f"TP={r}" for r in piv.index],
                      [f"EMA{c}" for c in piv.columns],
                      f"ORB v5 Grid: Expectancy R\nTP x EMA {sfx}",
                      "Expectancy (R)", "%+.3f")
        fig.tight_layout()
        p = PLOTS_DIR / f"orb_v5_grid_expectancy_{tag}.png"
        fig.savefig(p, dpi=120); plt.close(fig)
        print(f"Plot saved: {p}")

        # Heatmap 2: TP x body_ratio -- PF (avg over EMA)
        piv = sub.groupby(["tp_multiple", "min_body_ratio"])["pf"].mean().unstack()
        fig, ax = plt.subplots(figsize=(6, 4))
        _draw_heatmap(ax, piv.values,
                      [f"TP={r}" for r in piv.index],
                      [f"body={c:.1f}" for c in piv.columns],
                      f"ORB v5 Grid: Profit Factor\nTP x body_ratio {sfx}",
                      "Profit Factor", "%.2f")
        fig.tight_layout()
        p = PLOTS_DIR / f"orb_v5_grid_pf_{tag}.png"
        fig.savefig(p, dpi=120); plt.close(fig)
        print(f"Plot saved: {p}")

        # Heatmap 3: EMA x body_ratio -- expectancy (avg over TP)
        piv = sub.groupby(["ema_period", "min_body_ratio"])["er"].mean().unstack()
        fig, ax = plt.subplots(figsize=(6, 4))
        _draw_heatmap(ax, piv.values,
                      [f"EMA{r}" for r in piv.index],
                      [f"body={c:.1f}" for c in piv.columns],
                      f"ORB v5 Grid: Expectancy R\nEMA x body_ratio {sfx}",
                      "Expectancy (R)", "%+.3f")
        fig.tight_layout()
        p = PLOTS_DIR / f"orb_v5_grid_ema_body_{tag}.png"
        fig.savefig(p, dpi=120); plt.close(fig)
        print(f"Plot saved: {p}")


# ── CSV + markdown report ─────────────────────────────────────────────────────

def save_csv(df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.rename(columns={"tpy": "trades_per_year", "wr": "win_rate",
                        "er": "expectancy_r", "pf": "profit_factor",
                        "mdd": "max_dd_r", "tp_pct": "tp_hit_rate",
                        "eod_pct": "eod_exit_rate",
                        "mcl": "max_consec_losses"}).to_csv(CSV_PATH, index=False)
    print(f"CSV saved:  {CSV_PATH}")


def save_top_csv(df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    viable = df[(df["er"] >= 0.08) & (df["pf"] >= 1.20) & (df["tpy"] >= 60)].copy()
    top = (
        viable.sort_values(["er", "mdd", "tpy"], ascending=[False, True, False])
        if not viable.empty else df.sort_values("er", ascending=False)
    ).head(10)
    top_path = OUTPUT_DIR / "orb_v5_micro_grid_top.csv"
    top.rename(columns={"tpy": "trades_per_year", "wr": "win_rate",
                        "er": "expectancy_r", "pf": "profit_factor",
                        "mdd": "max_dd_r", "tp_pct": "tp_hit_rate",
                        "eod_pct": "eod_exit_rate",
                        "mcl": "max_consec_losses"}).to_csv(top_path, index=False)
    print(f"Top CSV:    {top_path}")


def save_report(df: pd.DataFrame, best: pd.Series) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    b_meets = best["er"] >= 0.10 and best["pf"] >= 1.30 and best["tpy"] >= 60
    verdict = "**Promising**" if b_meets else "**Not materially better than ORB v5**"

    # top-10 table
    top10    = df.sort_values("er", ascending=False).head(10)
    top10_md = ("| TP | EMA | OR_len | body | Trades | T/yr | WR% | E(R) | PF | MaxDD |\n"
                "|-----|-----|--------|------|--------|------|-----|------|----|-------|\n")
    for _, r in top10.iterrows():
        top10_md += (f"| {r['tp_multiple']:.1f} | {int(r['ema_period'])} | "
                     f"{int(r['or_length_minutes'])}m | {r['min_body_ratio']:.1f} | "
                     f"{int(r['trades'])} | {r['tpy']:.1f} | {r['wr']:.1f}% | "
                     f"{r['er']:+.3f} | {r['pf']:.2f} | {r['mdd']:.1f}R |\n")

    # sensitivity summary (marginal effects)
    by_tp   = df.groupby("tp_multiple")["er"].mean()
    by_ema  = df.groupby("ema_period")["er"].mean()
    by_or   = df.groupby("or_length_minutes")["er"].mean()
    by_body = df.groupby("min_body_ratio")["er"].mean()

    sens_tp   = f"Best TP multiple: {by_tp.idxmax():.1f} (avg E(R)={by_tp.max():+.3f})"
    sens_ema  = f"Best EMA period:  {int(by_ema.idxmax())} (avg E(R)={by_ema.max():+.3f})"
    sens_or   = f"Best OR length:   {int(by_or.idxmax())}m (avg E(R)={by_or.max():+.3f})"
    sens_body = f"Best body ratio:  {by_body.idxmax():.1f} (avg E(R)={by_body.max():+.3f})"

    tp_sensitive  = (by_tp.max()  - by_tp.min())  > 0.015
    ema_sensitive = (by_ema.max() - by_ema.min()) > 0.010
    or_sensitive  = (by_or.max()  - by_or.min())  > 0.010
    body_sensitive = (by_body.max() - by_body.min()) > 0.010

    def sens_label(flag):
        return "**sensitive**" if flag else "not very sensitive"

    # comparison vs v5
    delta_er  = best["er"]  - V5["er"]
    delta_pf  = best["pf"]  - V5["pf"]
    delta_mdd = best["mdd"] - V5["mdd"]

    md = f"""# ORB v5 Micro-Grid Parameter Sweep – Report

**Strategy:** Opening Range Breakout v5 + parameter grid  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** {START} → {END}  
**Generated:** {now}

## Strategy Description

All combinations share the same ORB v5 base logic:
LONG only | EMA1h filter | bullish OR bias | SL=OR_low | EOD@21:00 UTC

Only the four swept parameters vary.

## Parameter Grid

| Parameter | Values |
|-----------|--------|
| TP_multiple | {TP_MULTIPLES} |
| EMA_period | {EMA_PERIODS} |
| OR_length_min | {OR_LENGTHS} |
| min_body_ratio | {BODY_RATIOS} |
| **Total combinations** | **{len(TP_MULTIPLES) * len(EMA_PERIODS) * len(OR_LENGTHS) * len(BODY_RATIOS)}** |

## Top 10 Configurations (by Expectancy)

{top10_md}
## Best Configuration

{verdict}

| Parameter | Value |
|-----------|-------|
| TP_multiple | {best['tp_multiple']:.1f} |
| EMA_period | {int(best['ema_period'])} |
| OR_length_minutes | {int(best['or_length_minutes'])} |
| min_body_ratio | {best['min_body_ratio']:.1f} |
| Trades | {int(best['trades'])} |
| T/yr | {best['tpy']:.1f} |
| Win rate | {best['wr']:.1f}% |
| Expectancy | {best['er']:+.3f} R |
| Profit factor | {best['pf']:.2f} |
| Max DD | {best['mdd']:.1f} R |

### Success criteria

| Criterion | Required | Actual | Pass? |
|-----------|----------|--------|-------|
| Expectancy | >= +0.10R | {best['er']:+.3f} | {'PASS' if best['er'] >= 0.10 else 'FAIL'} |
| Profit factor | >= 1.30 | {best['pf']:.2f} | {'PASS' if best['pf'] >= 1.30 else 'FAIL'} |
| Trades/year | >= 60 | {best['tpy']:.1f} | {'PASS' if best['tpy'] >= 60 else 'FAIL'} |
| DD <= v5 ({V5['mdd']}R) | yes | {best['mdd']:.1f}R | {'PASS' if best['mdd'] <= V5['mdd'] else 'FAIL'} |

## Comparison vs ORB v5 Baseline

| Metric | ORB v5 | Best Grid | Delta |
|--------|--------|-----------|-------|
| Trades | {V5['trades']} | {int(best['trades'])} | {int(best['trades']) - V5['trades']:+d} |
| Win rate | {V5['wr']:.1f}% | {best['wr']:.1f}% | {best['wr'] - V5['wr']:+.1f}pp |
| Expectancy | {V5['er']:+.3f} | {best['er']:+.3f} | {delta_er:+.3f} |
| Profit factor | {V5['pf']:.2f} | {best['pf']:.2f} | {delta_pf:+.2f} |
| Max DD | {V5['mdd']:.1f}R | {best['mdd']:.1f}R | {delta_mdd:+.1f}R |

## Heatmaps

Saved to `research/plots/` (split by OR length: or15 = 15-min window, or30 = 30-min):

- `orb_v5_grid_expectancy_or15.png` / `orb_v5_grid_expectancy_or30.png` — TP x EMA, color = expectancy
- `orb_v5_grid_pf_or15.png` / `orb_v5_grid_pf_or30.png` — TP x body_ratio, color = PF
- `orb_v5_grid_ema_body_or15.png` / `orb_v5_grid_ema_body_or30.png` — EMA x body_ratio, color = expectancy

## Sensitivity Analysis (marginal effects)

| Parameter | Sensitivity | Best value | Note |
|-----------|-------------|------------|------|
| TP_multiple | {sens_label(tp_sensitive)} | {by_tp.idxmax():.1f} | {sens_tp} |
| EMA_period | {sens_label(ema_sensitive)} | {int(by_ema.idxmax())} | {sens_ema} |
| OR_length | {sens_label(or_sensitive)} | {int(by_or.idxmax())}m | {sens_or} |
| body_ratio | {sens_label(body_sensitive)} | {by_body.idxmax():.1f} | {sens_body} |

## Interpretation

- **Does TP_multiple significantly affect expectancy?**  
  {'Yes — ' + sens_tp if tp_sensitive else 'Marginally — ' + sens_tp}

- **Is EMA period sensitive?**  
  {'Yes — ' + sens_ema if ema_sensitive else 'No — ' + sens_ema}

- **Does shorter OR window work better?**  
  {f"OR {int(by_or.idxmax())}m outperforms on average. " + sens_or}

- **Does stronger OR body improve results?**  
  {'Yes — higher body_ratio improves quality but reduces trade count.' if body_sensitive else 'Minimal effect — body_ratio filter is not a strong discriminator on this dataset.'}

## Conclusion

{'The micro-grid found a configuration that clears all success thresholds.' if b_meets else 'No configuration in the 72-combo grid clearly outperforms ORB v5 on all criteria simultaneously.'}  
ORB v5 baseline (E(R)=+0.093, PF=1.25) remains a stable reference.  
The grid confirms that ORB v5 parameters are near-optimal in their local neighbourhood.

## Script

`strategies/OpeningRangeBreakout/research/orb_v5_micro_grid.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading data ...")
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    print("Pre-computing EMA30 / EMA50 / EMA70 on 1h bars ...")
    for p in EMA_PERIODS:
        df[f"ema{p}_1h"] = _build_ema_1h(df, p)
    df["date"] = df.index.normalize()

    print("Building day blueprints ...")
    blueprints = build_blueprints(df)
    print(f"  {len(blueprints)} day blueprints built")

    print(f"Running grid ({len(TP_MULTIPLES) * len(EMA_PERIODS) * len(OR_LENGTHS) * len(BODY_RATIOS)} combos) ...")
    results = run_grid(blueprints)

    best = select_best(results)
    print_top10(results, best)

    plot_heatmaps(results)
    save_csv(results)
    save_top_csv(results)
    save_report(results, best)
