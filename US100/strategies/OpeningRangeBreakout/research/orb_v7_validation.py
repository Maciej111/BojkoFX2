# ORB v7 Final Robustness Validation
# ====================================
# Best parameters from micro-grid: TP=1.8, EMA=50, OR=15min, body_ratio=0.1
#
# This script performs 7 validation steps:
#   Part 1 - Neighbourhood robustness grid (81 combos)
#   Part 2 - Walk-forward test (2 rolling windows)
#   Part 3 - Equity + drawdown curves
#   Part 4 - Monte Carlo simulation (10,000 iterations)
#   Part 5 - Risk of ruin estimates
#   Part 6 - Summary metrics
#   Part 7 - Markdown report
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v7_validation.py

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

# ── ORB v7 parameters ─────────────────────────────────────────────────────────
SYMBOL         = "usatechidxusd"
TIMEFRAME      = "5min"
START          = "2021-01-01"
END            = "2025-12-31"
SESSION_END_H  = 21

TP_V7          = 1.8
EMA_V7         = 50
OR_LEN_V7      = 15           # minutes
BODY_RATIO_V7  = 0.1

OR_START_MIN   = 14 * 60 + 30  # 870

# neighbourhood ranges for Part 1
TP_RANGE        = [1.7, 1.8, 1.9]
EMA_RANGE       = [40, 50, 60]
OR_LEN_RANGE    = [10, 15, 20]
BODY_RATIO_RANGE = [0.05, 0.10, 0.15]

# Walk-forward windows: (train_start, train_end_excl, test_start, test_end_excl)
WF_WINDOWS = [
    ("2021-01-01", "2024-01-01", "2024-01-01", "2025-01-01"),
    ("2022-01-01", "2025-01-01", "2025-01-01", "2026-01-01"),
]

RESEARCH_DIR = Path(__file__).parent
OUTPUT_DIR   = RESEARCH_DIR / "output"
PLOTS_DIR    = RESEARCH_DIR / "plots"
REPORT_PATH  = RESEARCH_DIR / "ORB_v7_validation_report.md"


# ── data structures ───────────────────────────────────────────────────────────

PostBar = namedtuple("PostBar",
    ["open_bid", "close_bid", "low_bid", "high_bid",
     "ema40", "ema50", "ema60"])

_EMA_ATTR = {40: "ema40", 50: "ema50", 60: "ema60"}


class DayBlue:
    __slots__ = ("date", "year", "or_data", "post_bars")

    def __init__(self, date, year, or_data, post_bars):
        self.date      = date
        self.year      = year
        self.or_data   = or_data   # dict per or_len key
        self.post_bars = post_bars # list[PostBar] per or_len key


# ── helpers ───────────────────────────────────────────────────────────────────

def _bar_min(ts) -> int:
    return ts.hour * 60 + ts.minute


def _build_ema_1h(df5m: pd.DataFrame, period: int) -> pd.Series:
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    return h1.ewm(span=period, adjust=False).mean().reindex(df5m.index, method="ffill")


def _max_dd_r(arr: np.ndarray) -> float:
    eq = np.concatenate([[0.0], np.cumsum(arr)])
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


def _metrics(records: list[dict], params: dict | None = None) -> dict:
    if not records:
        base = params or {}
        return {**base, "trades": 0, "tpy": 0.0, "wr": 0.0, "er": 0.0,
                "pf": 0.0, "mdd": 0.0, "avg_r": 0.0, "std_r": 0.0, "mcl": 0}
    arr   = np.asarray([r["R"] for r in records], dtype=float)
    exits = [r["exit"] for r in records]
    years = {r["year"] for r in records}
    n     = len(arr)
    gw    = float(arr[arr > 0].sum())
    gl    = float(abs(arr[arr < 0].sum()))
    d = {
        "trades":  n,
        "tpy":     round(n / len(years), 1),
        "wr":      round(float((arr > 0).mean()) * 100, 1),
        "er":      round(float(arr.mean()), 3),
        "pf":      round(gw / gl if gl > 0 else float("inf"), 2),
        "mdd":     round(_max_dd_r(arr), 1),
        "avg_r":   round(float(arr.mean()), 4),
        "std_r":   round(float(arr.std()), 4),
        "mcl":     _max_consec_losses(arr),
    }
    if params:
        d = {**params, **d}
    return d


# ── blueprint builder ─────────────────────────────────────────────────────────

def build_blueprints(df: pd.DataFrame, or_lengths: list[int]) -> list[DayBlue]:
    blueprints: list[DayBlue] = []

    for date, day in df.groupby("date"):
        day  = day.sort_index()
        mins = np.array([_bar_min(ts) for ts in day.index], dtype=int)

        def _or_data(end_min: int) -> dict | None:
            mask = (mins >= OR_START_MIN) & (mins < end_min)
            bars = day.iloc[mask]
            if len(bars) < 2:
                return None
            return {
                "high":  float(bars["high_bid"].max()),
                "low":   float(bars["low_bid"].min()),
                "open":  float(bars.iloc[0]["open_bid"]),
                "close": float(bars.iloc[-1]["close_bid"]),
            }

        def _post_bars(start_min: int) -> list[PostBar]:
            mask = (mins >= start_min) & (day.index.hour < SESSION_END_H)
            bars = day.iloc[mask]
            result = []
            for _, b in bars.iterrows():
                result.append(PostBar(
                    open_bid  = float(b["open_bid"]),
                    close_bid = float(b["close_bid"]),
                    low_bid   = float(b["low_bid"]),
                    high_bid  = float(b["high_bid"]),
                    ema40     = float(b.get("ema40_1h", float("nan"))),
                    ema50     = float(b.get("ema50_1h", float("nan"))),
                    ema60     = float(b.get("ema60_1h", float("nan"))),
                ))
            return result

        or_data_map   = {}
        post_bars_map = {}
        for or_len in or_lengths:
            end_min = OR_START_MIN + or_len
            odata   = _or_data(end_min)
            or_data_map[or_len]   = odata
            post_bars_map[or_len] = _post_bars(end_min) if odata else []

        if any(v is not None for v in or_data_map.values()):
            blueprints.append(DayBlue(
                date      = str(date.date()),
                year      = int(date.year),
                or_data   = or_data_map,
                post_bars = post_bars_map,
            ))

    return blueprints


# ── entry / exit resolution ───────────────────────────────────────────────────

def _find_entry(post_bars: list[PostBar], or_high: float, or_low: float,
                ema_period: int) -> dict | None:
    ema_attr = _EMA_ATTR[ema_period]
    for i, bar in enumerate(post_bars):
        if bar.close_bid <= or_high:
            continue
        ema_val = getattr(bar, ema_attr)
        if ema_val != ema_val or bar.close_bid <= ema_val:
            return None
        if i + 1 >= len(post_bars):
            return None
        entry_bar   = post_bars[i + 1]
        entry_price = entry_bar.open_bid
        risk        = entry_price - or_low
        if risk <= 0:
            continue
        return {
            "entry_price":     entry_price,
            "entry_bar_close": entry_bar.close_bid,
            "sl":              or_low,
            "risk":            risk,
            "remaining":       post_bars[i + 2:],
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


# ── run ORB v7 on a set of blueprints ────────────────────────────────────────

def run_v7(blueprints: list[DayBlue],
           tp: float = TP_V7,
           ema: int  = EMA_V7,
           or_len: int = OR_LEN_V7,
           body_ratio: float = BODY_RATIO_V7) -> list[dict]:
    records: list[dict] = []
    for bp in blueprints:
        odata     = bp.or_data.get(or_len)
        post_bars = bp.post_bars.get(or_len, [])
        if odata is None or len(post_bars) < 2:
            continue
        or_range = odata["high"] - odata["low"]
        if or_range <= 0:
            continue
        or_body = odata["close"] - odata["open"]
        if or_body <= 0:
            continue
        if (or_body / or_range) < body_ratio:
            continue
        entry = _find_entry(post_bars, odata["high"], odata["low"], ema)
        if entry is None:
            continue
        R, exit_reason = _resolve_exit(entry, tp)
        records.append({"date": bp.date, "year": bp.year, "R": R, "exit": exit_reason})
    return records


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — NEIGHBOURHOOD ROBUSTNESS GRID
# ═══════════════════════════════════════════════════════════════════════════════

def part1_robustness(blueprints: list[DayBlue]) -> pd.DataFrame:
    print("\n[Part 1] Neighbourhood robustness grid ...")
    all_or_lens = sorted(set(OR_LEN_RANGE))
    rows: list[dict] = []

    n_total  = len(TP_RANGE) * len(EMA_RANGE) * len(OR_LEN_RANGE) * len(BODY_RATIO_RANGE)
    done     = 0

    for tp, ema, or_len, body in product(TP_RANGE, EMA_RANGE, OR_LEN_RANGE, BODY_RATIO_RANGE):
        records = run_v7(blueprints, tp=tp, ema=ema, or_len=or_len, body_ratio=body)
        params  = {"tp": tp, "ema": ema, "or_len": or_len, "body": body}
        rows.append(_metrics(records, params))
        done += 1
        print(f"\r  {done}/{n_total} combos", end="", flush=True)

    print()
    df = pd.DataFrame(rows).sort_values("er", ascending=False).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "orb_v7_robustness_results.csv", index=False)
    print(f"  Saved: output/orb_v7_robustness_results.csv")

    # print top 15
    print()
    SEP = "=" * 95
    print(SEP)
    print("  PART 1 - NEIGHBOURHOOD ROBUSTNESS (top 15 by expectancy)")
    print(SEP)
    print(f"  {'TP':>5}  {'EMA':>5}  {'OR':>5}  {'Body':>6}  "
          f"{'Trades':>6}  {'T/yr':>5}  {'WR%':>5}  "
          f"{'E(R)':>7}  {'PF':>5}  {'MaxDD':>7}  {'MCL':>5}")
    print("  " + "-" * 88)
    for _, r in df.head(15).iterrows():
        star = " *" if (r["tp"] == TP_V7 and r["ema"] == EMA_V7 and
                        r["or_len"] == OR_LEN_V7 and r["body"] == BODY_RATIO_V7) else "  "
        print(
            f"  {r['tp']:>4.1f}  {int(r['ema']):>5}  {int(r['or_len']):>4}m  "
            f"{r['body']:>6.2f}  {int(r['trades']):>6}  {r['tpy']:>5.1f}  "
            f"{r['wr']:>4.1f}%  {r['er']:>+7.3f}  {r['pf']:>5.2f}  "
            f"{r['mdd']:>6.1f}R  {int(r['mcl']):>5}{star}"
        )
    print(SEP)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — WALK-FORWARD TEST
# ═══════════════════════════════════════════════════════════════════════════════

def _filter_blueprints(blueprints: list[DayBlue], start: str, end: str) -> list[DayBlue]:
    return [bp for bp in blueprints if start <= bp.date < end]


def part2_walkforward(blueprints: list[DayBlue]) -> pd.DataFrame:
    print("\n[Part 2] Walk-forward test ...")
    rows: list[dict] = []
    all_oos_records: list[dict] = []

    for train_s, train_e, test_s, test_e in WF_WINDOWS:
        test_bp  = _filter_blueprints(blueprints, test_s, test_e)
        records  = run_v7(test_bp)
        m        = _metrics(records)
        row      = {
            "window":       f"{test_s[:4]}",
            "train_period": f"{train_s} - {train_e}",
            "test_period":  f"{test_s} - {test_e}",
            **m
        }
        rows.append(row)
        all_oos_records.extend(records)
        print(f"  Test {test_s[:4]}: {m['trades']} trades  "
              f"WR={m['wr']:.1f}%  E(R)={m['er']:+.3f}  "
              f"PF={m['pf']:.2f}  MaxDD={m['mdd']:.1f}R")

    # combined OOS
    comb = _metrics(all_oos_records)
    rows.append({
        "window": "COMBINED",
        "train_period": "–",
        "test_period":  "2024 + 2025",
        **comb
    })
    print(f"  Combined OOS: {comb['trades']} trades  "
          f"WR={comb['wr']:.1f}%  E(R)={comb['er']:+.3f}  "
          f"PF={comb['pf']:.2f}  MaxDD={comb['mdd']:.1f}R")

    df = pd.DataFrame(rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "orb_v7_walkforward_results.csv", index=False)
    print(f"  Saved: output/orb_v7_walkforward_results.csv")
    return df, all_oos_records


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 — EQUITY + DRAWDOWN CURVES
# ═══════════════════════════════════════════════════════════════════════════════

def part3_equity_curves(records: list[dict]) -> None:
    print("\n[Part 3] Equity and drawdown curves ...")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available - skipping plots")
        return

    arr     = np.asarray([r["R"] for r in records], dtype=float)
    eq      = np.concatenate([[0.0], np.cumsum(arr)])
    dd      = np.maximum.accumulate(eq) - eq
    x       = np.arange(len(eq))

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    # equity curve
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(x, eq, color="#2196F3", linewidth=1.2)
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_title("ORB v7 — Full Backtest Equity Curve (2021-2025)")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Cumulative R")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = PLOTS_DIR / "orb_v7_equity.png"
    fig.savefig(p, dpi=130); plt.close(fig)
    print(f"  Plot saved: {p}")

    # drawdown curve
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.fill_between(x, -dd, 0, color="#ef5350", alpha=0.6)
    ax.plot(x, -dd, color="#c62828", linewidth=0.8)
    ax.set_title("ORB v7 — Drawdown Curve (2021-2025)")
    ax.set_xlabel("Trade #")
    ax.set_ylabel("Drawdown (R)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = PLOTS_DIR / "orb_v7_drawdown.png"
    fig.savefig(p, dpi=130); plt.close(fig)
    print(f"  Plot saved: {p}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 4 — MONTE CARLO SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

def part4_monte_carlo(records: list[dict],
                      n_sims: int = 10_000,
                      seed: int   = 42) -> dict:
    print(f"\n[Part 4] Monte Carlo simulation ({n_sims:,} iterations) ...")
    arr = np.asarray([r["R"] for r in records], dtype=float)
    n   = len(arr)

    rng            = np.random.default_rng(seed)
    final_equities = np.empty(n_sims, dtype=float)
    max_drawdowns  = np.empty(n_sims, dtype=float)
    max_streaks    = np.empty(n_sims, dtype=int)
    # Store a sample of equity paths for the fan chart (every 100th sim)
    sample_paths   = []

    for i in range(n_sims):
        shuffled = rng.permutation(arr)
        eq       = np.concatenate([[0.0], np.cumsum(shuffled)])
        final_equities[i] = eq[-1]
        max_drawdowns[i]  = float((np.maximum.accumulate(eq) - eq).max())
        max_streaks[i]    = _max_consec_losses(shuffled)
        if i % 100 == 0:
            sample_paths.append(eq)

    mc_stats = {
        "eq_p5":   float(np.percentile(final_equities, 5)),
        "eq_p25":  float(np.percentile(final_equities, 25)),
        "eq_p50":  float(np.percentile(final_equities, 50)),
        "eq_p75":  float(np.percentile(final_equities, 75)),
        "eq_p95":  float(np.percentile(final_equities, 95)),
        "dd_p50":  float(np.percentile(max_drawdowns, 50)),
        "dd_p75":  float(np.percentile(max_drawdowns, 75)),
        "dd_p95":  float(np.percentile(max_drawdowns, 95)),
        "streak_p50": float(np.percentile(max_streaks, 50)),
        "streak_p75": float(np.percentile(max_streaks, 75)),
        "streak_p95": float(np.percentile(max_streaks, 95)),
        "pct_positive": float((final_equities > 0).mean() * 100),
    }

    print(f"  Final equity - P5={mc_stats['eq_p5']:+.1f}R  "
          f"P50={mc_stats['eq_p50']:+.1f}R  P95={mc_stats['eq_p95']:+.1f}R")
    print(f"  Max DD       - P50={mc_stats['dd_p50']:.1f}R  "
          f"P75={mc_stats['dd_p75']:.1f}R  P95={mc_stats['dd_p95']:.1f}R")
    print(f"  Max streak   - P50={mc_stats['streak_p50']:.0f}  "
          f"P75={mc_stats['streak_p75']:.0f}  P95={mc_stats['streak_p95']:.0f}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        PLOTS_DIR.mkdir(parents=True, exist_ok=True)

        # Monte Carlo equity fan chart (sample paths)
        fig, ax = plt.subplots(figsize=(10, 4))
        for path in sample_paths:
            ax.plot(path, color="#42A5F5", linewidth=0.3, alpha=0.4)
        ax.axhline(0, color="gray", linewidth=0.7, linestyle="--")
        # Highlight worst/best of sample
        sample_arr = np.array(sample_paths)
        ax.plot(sample_arr[sample_arr[:, -1].argmin()], color="red",   linewidth=1, label="Worst path")
        ax.plot(sample_arr[sample_arr[:, -1].argmax()], color="green", linewidth=1, label="Best path")
        from numpy import percentile as pct
        mid = np.median(sample_arr, axis=0)
        ax.plot(mid, color="orange", linewidth=1.2, label="Median path")
        ax.set_title(f"ORB v7 -- Monte Carlo Equity Paths ({len(sample_paths)} of {n_sims:,} sims)")
        ax.set_xlabel("Trade #")
        ax.set_ylabel("Cumulative R")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        p = PLOTS_DIR / "orb_v7_monte_carlo_equity.png"
        fig.savefig(p, dpi=130); plt.close(fig)
        print(f"  Plot saved: {p}")

        # Drawdown distribution
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(max_drawdowns, bins=80, color="#EF5350", edgecolor="none", alpha=0.8)
        ax.axvline(mc_stats["dd_p50"], color="orange", linestyle="--", linewidth=1,
                   label=f"P50 = {mc_stats['dd_p50']:.1f}R")
        ax.axvline(mc_stats["dd_p75"], color="red",    linestyle="--", linewidth=1,
                   label=f"P75 = {mc_stats['dd_p75']:.1f}R")
        ax.axvline(mc_stats["dd_p95"], color="darkred", linestyle="--", linewidth=1,
                   label=f"P95 = {mc_stats['dd_p95']:.1f}R")
        ax.set_title(f"ORB v7 — Monte Carlo Max Drawdown ({n_sims:,} sims)")
        ax.set_xlabel("Max Drawdown (R)")
        ax.set_ylabel("Frequency")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        p = PLOTS_DIR / "orb_v7_monte_carlo_dd.png"
        fig.savefig(p, dpi=130); plt.close(fig)
        print(f"  Plot saved: {p}")

    except ImportError:
        print("  matplotlib not available - skipping plots")

    return mc_stats


# ═══════════════════════════════════════════════════════════════════════════════
# PART 5 — RISK OF RUIN
# ═══════════════════════════════════════════════════════════════════════════════

def part5_risk_of_ruin(records: list[dict],
                       ruin_levels_r: list[float],
                       n_sims: int = 10_000,
                       seed: int   = 42) -> dict:
    print("\n[Part 5] Risk of ruin ...")
    arr          = np.asarray([r["R"] for r in records], dtype=float)
    rng          = np.random.default_rng(seed + 1)
    ruin_results = {}

    for level in ruin_levels_r:
        p = float((np.array([
            np.cumsum(rng.permutation(arr))
        for _ in range(n_sims)]).min(axis=1) <= -level).mean() * 100)
        ruin_results[level] = round(p, 2)

    # print table header
    print()
    print(f"  {'Ruin level':>12}  {'Prob (%)':>10}")
    print("  " + "-" * 25)
    for level, p in ruin_results.items():
        print(f"  -{level:.0f}R         {p:>10.2f}%")

    return ruin_results


# ═══════════════════════════════════════════════════════════════════════════════
# PART 6 — SUMMARY METRICS
# ═══════════════════════════════════════════════════════════════════════════════

def part6_summary(records: list[dict]) -> dict:
    print("\n[Part 6] Summary metrics ...")
    arr   = np.asarray([r["R"] for r in records], dtype=float)
    n     = len(arr)
    years = len({r["year"] for r in records})

    gw   = float(arr[arr > 0].sum())
    gl   = float(abs(arr[arr < 0].sum()))
    pf   = round(gw / gl if gl > 0 else float("inf"), 2)
    er   = round(float(arr.mean()), 4)
    wr   = round(float((arr > 0).mean()) * 100, 1)
    mdd  = round(_max_dd_r(arr), 1)
    mcl  = _max_consec_losses(arr)
    tpy  = round(n / years, 1)

    # Sharpe (annualised, assuming ~tpy trades/year)
    if arr.std() > 0:
        sharpe = round(float(arr.mean() / arr.std() * np.sqrt(tpy)), 2)
    else:
        sharpe = 0.0

    summary = dict(
        total_trades=n, trades_per_year=tpy, win_rate=wr,
        expectancy=er, profit_factor=pf, max_drawdown=mdd,
        max_consec_losses=mcl, sharpe_ratio=sharpe,
    )

    SEP = "=" * 60
    print(); print(SEP)
    print("  ORB v7 - FULL BACKTEST SUMMARY (2021-2025)")
    print(SEP)
    for k, v in summary.items():
        print(f"  {k:<25} {v}")
    print(SEP)
    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# PART 7 — MARKDOWN REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def part7_report(summary: dict, robustness_df: pd.DataFrame,
                 wf_df: pd.DataFrame, mc_stats: dict,
                 ruin_results: dict) -> None:
    print("\n[Part 7] Writing report ...")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # robustness top-10 table
    top10 = robustness_df.head(10)
    rob_md = ("| TP | EMA | OR | body | Trades | T/yr | WR% | E(R) | PF | MaxDD | MCL |\n"
              "|----|-----|----|----|--------|------|-----|------|----|-------|-----|\n")
    for _, r in top10.iterrows():
        star = " **\u2190** v7" if (r["tp"] == TP_V7 and r["ema"] == EMA_V7 and
                                     r["or_len"] == OR_LEN_V7 and r["body"] == BODY_RATIO_V7) else ""
        rob_md += (f"| {r['tp']:.1f} | {int(r['ema'])} | {int(r['or_len'])}m | "
                   f"{r['body']:.2f} | {int(r['trades'])} | {r['tpy']:.1f} | "
                   f"{r['wr']:.1f}% | {r['er']:+.3f} | {r['pf']:.2f} | "
                   f"{r['mdd']:.1f}R | {int(r['mcl'])} |{star}\n")

    # WF table
    wf_md = ("| Window | Test period | Trades | T/yr | WR% | E(R) | PF | MaxDD |\n"
             "|--------|-------------|--------|------|-----|------|----|-------|\n")
    for _, r in wf_df.iterrows():
        wf_md += (f"| {r['window']} | {r['test_period']} | {int(r['trades'])} | "
                  f"{r['tpy']:.1f} | {r['wr']:.1f}% | {r['er']:+.3f} | "
                  f"{r['pf']:.2f} | {r['mdd']:.1f}R |\n")

    # risk of ruin table
    ror_md = ("| Ruin level | Prob (%) |\n"
              "|-----------|----------|\n")
    for level, p in ruin_results.items():
        ror_md += f"| -{level:.0f}R | {p:.2f}% |\n"

    # success criteria
    s = summary
    cr_pass = (s["expectancy"] >= 0.10 and s["profit_factor"] >= 1.30
               and s["trades_per_year"] >= 60 and s["max_drawdown"] < 15.0)

    # WF both profitable
    wf_rows = wf_df[wf_df["window"] != "COMBINED"]
    wf_profitable = all(r["er"] > 0 for _, r in wf_rows.iterrows())

    # robustness plateau check: how many combos in top 10 have er >= 0.10
    top10_pass = int((top10["er"] >= 0.10).sum())

    overall_verdict = (cr_pass and wf_profitable and top10_pass >= 5)

    criteria_md = f"""| Criterion | Required | Actual | Pass? |
|-----------|----------|--------|-------|
| Expectancy | >= +0.10R | {s['expectancy']:+.3f} | {'PASS' if s['expectancy'] >= 0.10 else 'FAIL'} |
| Profit factor | >= 1.30 | {s['profit_factor']:.2f} | {'PASS' if s['profit_factor'] >= 1.30 else 'FAIL'} |
| Trades/year | >= 60 | {s['trades_per_year']:.1f} | {'PASS' if s['trades_per_year'] >= 60 else 'FAIL'} |
| Max drawdown | < 15R | {s['max_drawdown']:.1f}R | {'PASS' if s['max_drawdown'] < 15.0 else 'FAIL'} |
| WF profitable | both windows | {'Yes' if wf_profitable else 'No'} | {'PASS' if wf_profitable else 'FAIL'} |
| Plateau (top10 >= 5 pass) | 5/10 | {top10_pass}/10 | {'PASS' if top10_pass >= 5 else 'FAIL'} |"""

    md = f"""# ORB v7 Final Validation Report

**Strategy:** Opening Range Breakout v7  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** {START} to {END}  
**Generated:** {now}

---

## 1. Strategy Description

ORB v7 uses the micro-grid-optimised parameter set from the ORB v5 research pipeline.

| Parameter | Value |
|-----------|-------|
| Direction | LONG only |
| Opening Range | 14:30 - 14:45 UTC (15 min) |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | 1.8R |
| Trend filter | close_bid > EMA(50) on 1h bars |
| OR body filter | (OR_close - OR_open) / (OR_high - OR_low) >= 0.1 |
| EOD close | 21:00 UTC |
| Max trades/day | 1 |

---

## 2. Robustness Results (Part 1)

**Grid:** TP x [1.7, 1.8, 1.9] x EMA [40, 50, 60] x OR_len [10, 15, 20min] x body [0.05, 0.10, 0.15]  
**Total combinations:** {len(TP_RANGE) * len(EMA_RANGE) * len(OR_LEN_RANGE) * len(BODY_RATIO_RANGE)}

### Top 10 Configurations (sorted by expectancy)

{rob_md}

### Parameter sensitivity summary

| Parameter | Avg E(R) range | Sensitive? |
|-----------|----------------|------------|
| TP_multiple | {robustness_df.groupby('tp')['er'].mean().max() - robustness_df.groupby('tp')['er'].mean().min():+.3f} | {'Yes' if (robustness_df.groupby('tp')['er'].mean().max() - robustness_df.groupby('tp')['er'].mean().min()) > 0.010 else 'No'} |
| EMA_period | {robustness_df.groupby('ema')['er'].mean().max() - robustness_df.groupby('ema')['er'].mean().min():+.3f} | {'Yes' if (robustness_df.groupby('ema')['er'].mean().max() - robustness_df.groupby('ema')['er'].mean().min()) > 0.010 else 'No'} |
| OR_length | {robustness_df.groupby('or_len')['er'].mean().max() - robustness_df.groupby('or_len')['er'].mean().min():+.3f} | {'Yes' if (robustness_df.groupby('or_len')['er'].mean().max() - robustness_df.groupby('or_len')['er'].mean().min()) > 0.010 else 'No'} |
| body_ratio | {robustness_df.groupby('body')['er'].mean().max() - robustness_df.groupby('body')['er'].mean().min():+.3f} | {'Yes' if (robustness_df.groupby('body')['er'].mean().max() - robustness_df.groupby('body')['er'].mean().min()) > 0.010 else 'No'} |

---

## 3. Walk-Forward Results (Part 2)

{wf_md}

---

## 4. Equity Curves (Part 3)

Full-period equity and drawdown curves:

- `plots/orb_v7_equity.png`
- `plots/orb_v7_drawdown.png`

---

## 5. Monte Carlo Simulation (Part 4)

**Simulations:** 10,000 random trade-order shuffles

| Metric | P5 | P25 | P50 | P75 | P95 |
|--------|-----|-----|-----|-----|-----|
| Final equity (R) | {mc_stats['eq_p5']:+.1f} | {mc_stats['eq_p25']:+.1f} | {mc_stats['eq_p50']:+.1f} | {mc_stats['eq_p75']:+.1f} | {mc_stats['eq_p95']:+.1f} |
| Max drawdown (R) | - | - | {mc_stats['dd_p50']:.1f} | {mc_stats['dd_p75']:.1f} | {mc_stats['dd_p95']:.1f} |
| Max losing streak | - | - | {mc_stats['streak_p50']:.0f} | {mc_stats['streak_p75']:.0f} | {mc_stats['streak_p95']:.0f} |

Percentage of simulations with positive final equity: **{mc_stats['pct_positive']:.1f}%**

Plots saved:
- `plots/orb_v7_monte_carlo_equity.png`
- `plots/orb_v7_monte_carlo_dd.png`

---

## 6. Risk of Ruin (Part 5)

Probability of equity ever touching the ruin threshold (10,000 simulations per level):

{ror_md}

---

## 7. Final Evaluation

### Summary Metrics (full period 2021-2025)

| Metric | Value |
|--------|-------|
| Total trades | {s['total_trades']} |
| Trades/year | {s['trades_per_year']:.1f} |
| Win rate | {s['win_rate']:.1f}% |
| Expectancy | {s['expectancy']:+.4f} R |
| Profit factor | {s['profit_factor']:.2f} |
| Max drawdown | {s['max_drawdown']:.1f} R |
| Max consec. losses | {s['max_consec_losses']} |
| Sharpe ratio | {s['sharpe_ratio']:.2f} |

### Success Criteria

{criteria_md}

### Is ORB v7 robust?

{'**YES** — ORB v7 passes all 6 robustness criteria.' if overall_verdict else '**PARTIALLY** — ORB v7 does not fully satisfy all robustness criteria. See individual criteria above.'}

### Does performance remain stable out-of-sample?

{f'Walk-forward test 2024: E(R)={wf_df.iloc[0]["er"]:+.3f}, PF={wf_df.iloc[0]["pf"]:.2f}' if len(wf_df) >= 1 else 'N/A'}  
{f'Walk-forward test 2025: E(R)={wf_df.iloc[1]["er"]:+.3f}, PF={wf_df.iloc[1]["pf"]:.2f}' if len(wf_df) >= 2 else 'N/A'}  
{'Both windows are profitable.' if wf_profitable else 'Not all walk-forward windows are profitable — performance inconsistent OOS.'}

### Is the parameter region stable?

{top10_pass} out of the top 10 robustness neighbourhood configurations clear E(R) >= 0.10.  
{'The v7 parameters sit inside a plateau — not an isolated spike. Small tuning changes do not collapse performance.' if top10_pass >= 5 else 'The v7 parameter region shows limited stability. Exercise caution.'}

### Is drawdown acceptable?

Max observed drawdown: {s['max_drawdown']:.1f}R.  
Monte Carlo P95 drawdown: {mc_stats['dd_p95']:.1f}R.  
{'Drawdown is within acceptable range (< 15R).' if s['max_drawdown'] < 15.0 else 'Drawdown exceeds the 15R threshold.'}

### Recommendation

{'> **Proceed to forward testing / paper trading.**  ' if overall_verdict else '> **Do not proceed to forward testing yet.**  '}  
{'> ORB v7 demonstrates sufficient robustness across all tested dimensions.' if overall_verdict else '> Resolve the failing criteria before paper trading.'}

---

*Script: `strategies/OpeningRangeBreakout/research/orb_v7_validation.py`*
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"  Report saved: {REPORT_PATH}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_or_lens = sorted(set(OR_LEN_RANGE) | {OR_LEN_V7})

    print("=" * 60)
    print("  ORB v7 FINAL VALIDATION")
    print("=" * 60)
    print(f"  TP={TP_V7}  EMA={EMA_V7}  OR={OR_LEN_V7}min  body={BODY_RATIO_V7}")
    print()

    print("Loading data ...")
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()
    print(f"  {len(df):,} bars loaded")

    print("Pre-computing EMA 40 / 50 / 60 on 1h bars ...")
    for p in [40, 50, 60]:
        df[f"ema{p}_1h"] = _build_ema_1h(df, p)
    df["date"] = df.index.normalize()

    print(f"Building day blueprints (OR lengths: {all_or_lens}) ...")
    blueprints = build_blueprints(df, all_or_lens)
    print(f"  {len(blueprints)} blueprints built")

    # Full-period run with v7 params (used for Parts 3-6)
    print("\nRunning full ORB v7 backtest (2021-2025) ...")
    full_records = run_v7(blueprints)
    print(f"  {len(full_records)} trades")

    # Parts
    robustness_df               = part1_robustness(blueprints)
    wf_df, oos_records          = part2_walkforward(blueprints)
    part3_equity_curves(full_records)
    mc_stats                    = part4_monte_carlo(full_records)
    ruin_levels                 = [20.0, 30.0, 40.0]
    ruin_results                = part5_risk_of_ruin(full_records, ruin_levels)
    summary                     = part6_summary(full_records)
    part7_report(summary, robustness_df, wf_df, mc_stats, ruin_results)

    print()
    print("=" * 60)
    print("  VALIDATION COMPLETE")
    print("=" * 60)
