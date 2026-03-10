"""
Generates a single combined summary report for all timeframes tested on US100.

Runs: 5m / 15m / 30m / 1h  ×  2021 / 2022 / 2023 / 2024  +  full 2021-2024
Saves: reports/IDX_USATECHIDXUSD_SUMMARY.md

Usage:
    python -m scripts.run_idx_summary
    python -m scripts.run_idx_summary --symbol usatechidxusd --rr 2.0
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import run_backtest, _calc_r_drawdown

REPORTS_DIR = ROOT / "reports"
YEARS = [2021, 2022, 2023, 2024]
TIMEFRAMES = [("5min", "4h"), ("15min", "4h"), ("30min", "4h"), ("1h", "4h")]


def _slug(tf: str) -> str:
    return tf.replace("min", "m").replace("T", "m")


def _run_one(symbol, ltf, htf, start, end, params):
    trades, m = run_backtest(
        symbol=symbol, ltf=ltf, htf=htf,
        start=start, end=end,
        params=params, initial_balance=10_000.0,
    )
    if m is None:
        return None
    r_dd = _calc_r_drawdown(trades) if trades is not None and len(trades) else 0.0
    return {
        "trades":    m.get("trades_count", 0),
        "win_rate":  m.get("win_rate", 0.0),        # already %
        "exp_r":     m.get("expectancy_R", 0.0),
        "pf":        m.get("profit_factor", 0.0),
        "r_dd":      r_dd,
        "streak":    m.get("max_losing_streak", 0),
        "setups":    m.get("total_setups", 0),
        "missed":    m.get("missed_rate", 0.0),     # 0-1
    }


def _fmt_exp(v):
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.3f}"


def _rating(exp_r, pf):
    """Simple traffic-light rating."""
    if exp_r > 0.2 and pf >= 1.3:
        return "✅"
    if exp_r > 0 and pf >= 1.0:
        return "🟡"
    return "❌"


def build_summary_report(symbol: str, rr: float, all_results: dict) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# US100 Index Backtest — Multi-Timeframe Summary",
        f"",
        f"**Symbol:** {symbol.upper()}  |  **HTF:** H4  |  **RR:** {rr}  |  **Generated:** {now}",
        f"**Strategy:** BOS + Pullback (trend_following_v1)",
        f"",
        f"---",
        f"",
        f"## 1. Full Period 2021–2024 Overview",
        f"",
        f"| TF | Trades | Win Rate | Exp(R) | PF | Max R-DD | Rating |",
        f"|----|--------|----------|--------|----|----------|--------|",
    ]

    for ltf, htf in TIMEFRAMES:
        key = ("full", ltf)
        r = all_results.get(key)
        if r:
            lines.append(
                f"| **{_slug(ltf)}** | {r['trades']} | {r['win_rate']:.1f}% | "
                f"{_fmt_exp(r['exp_r'])} | {r['pf']:.2f} | {r['r_dd']:.1f}R | "
                f"{_rating(r['exp_r'], r['pf'])} |"
            )

    lines += [
        f"",
        f"---",
        f"",
        f"## 2. Per-Year Breakdown",
        f"",
    ]

    for ltf, htf in TIMEFRAMES:
        slug = _slug(ltf)
        lines += [
            f"### {slug} LTF / 4h HTF",
            f"",
            f"| Year | Trades | Win Rate | Exp(R) | PF | Max R-DD | Lose Streak |",
            f"|------|--------|----------|--------|----|----------|-------------|",
        ]
        for year in YEARS:
            key = (year, ltf)
            r = all_results.get(key)
            if r:
                lines.append(
                    f"| {year} | {r['trades']} | {r['win_rate']:.1f}% | "
                    f"{_fmt_exp(r['exp_r'])} | {r['pf']:.2f} | {r['r_dd']:.1f}R | {r['streak']} |"
                )
        # Full period row
        key = ("full", ltf)
        r = all_results.get(key)
        if r:
            lines.append(
                f"| **2021–2024** | **{r['trades']}** | **{r['win_rate']:.1f}%** | "
                f"**{_fmt_exp(r['exp_r'])}** | **{r['pf']:.2f}** | **{r['r_dd']:.1f}R** | **{r['streak']}** |"
            )
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## 3. Expectancy Heatmap (R per trade)",
        f"",
        f"| TF \\ Year | 2021 | 2022 | 2023 | 2024 | **AVG** |",
        f"|------------|------|------|------|------|---------|",
    ]

    for ltf, htf in TIMEFRAMES:
        slug = _slug(ltf)
        row_vals = []
        for year in YEARS:
            r = all_results.get((year, ltf))
            row_vals.append(r["exp_r"] if r else None)
        valid = [v for v in row_vals if v is not None]
        avg = sum(valid) / len(valid) if valid else 0.0
        cells = " | ".join(_fmt_exp(v) if v is not None else "—" for v in row_vals)
        lines.append(f"| **{slug}** | {cells} | **{_fmt_exp(avg)}** |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 4. Profit Factor Heatmap",
        f"",
        f"| TF \\ Year | 2021 | 2022 | 2023 | 2024 | **AVG** |",
        f"|------------|------|------|------|------|---------|",
    ]

    for ltf, htf in TIMEFRAMES:
        slug = _slug(ltf)
        row_vals = []
        for year in YEARS:
            r = all_results.get((year, ltf))
            row_vals.append(r["pf"] if r else None)
        valid = [v for v in row_vals if v is not None]
        avg = sum(valid) / len(valid) if valid else 0.0
        cells = " | ".join(f"{v:.2f}" if v is not None else "—" for v in row_vals)
        lines.append(f"| **{slug}** | {cells} | **{avg:.2f}** |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 5. Setup Statistics",
        f"",
        f"| TF | Total Setups/yr | Missed Rate | Avg Trades/yr |",
        f"|----|-----------------|-------------|---------------|",
    ]

    for ltf, htf in TIMEFRAMES:
        slug = _slug(ltf)
        r = all_results.get(("full", ltf))
        if r:
            avg_setups = r["setups"] / len(YEARS)
            avg_trades = r["trades"] / len(YEARS)
            lines.append(
                f"| **{slug}** | {avg_setups:.0f} | {r['missed'] * 100:.1f}% | {avg_trades:.0f} |"
            )

    lines += [
        f"",
        f"---",
        f"",
        f"## 6. Strategy Parameters",
        f"",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| pivot_lookback_ltf | 3 |",
        f"| pivot_lookback_htf | 5 |",
        f"| confirmation_bars | 1 |",
        f"| require_close_break | True |",
        f"| entry_offset_atr_mult | 0.3 |",
        f"| pullback_max_bars | 20 |",
        f"| sl_anchor | last_pivot |",
        f"| sl_buffer_atr_mult | 0.5 |",
        f"| risk_reward | {rr} |",
        f"",
        f"---",
        f"",
        f"## 7. Conclusions",
        f"",
    ]

    # Auto-generate conclusions based on data
    best_full = max(
        [(ltf, all_results[("full", ltf)]) for ltf, _ in TIMEFRAMES if ("full", ltf) in all_results],
        key=lambda x: x[1]["exp_r"],
    )
    most_stable = max(
        [(ltf, all_results[("full", ltf)]) for ltf, _ in TIMEFRAMES if ("full", ltf) in all_results],
        key=lambda x: sum(1 for y in YEARS if all_results.get((y, x[0]), {}).get("exp_r", -1) > 0),
    )

    lines += [
        f"- **Best overall expectancy:** {_slug(best_full[0])} ({_fmt_exp(best_full[1]['exp_r'])}R, PF {best_full[1]['pf']:.2f})",
        f"- **Most consistent:** {_slug(most_stable[0])} — positive expectancy in "
        f"{sum(1 for y in YEARS if all_results.get((y, most_stable[0]), {}).get('exp_r', -1) > 0)}/{len(YEARS)} years",
        f"- All TFs tested use default BOS+Pullback parameters tuned for FX — index-specific optimisation (session filter, ATR filter) could improve further.",
        f"- Data source: Dukascopy 1M bid bars, constant spread {1.0} pt applied.",
    ]

    return "\n".join(lines)


def run_summary(symbol: str = "usatechidxusd", rr: float = 2.0):
    params = {
        "pivot_lookback_ltf":    3,
        "pivot_lookback_htf":    5,
        "confirmation_bars":     1,
        "require_close_break":   True,
        "entry_offset_atr_mult": 0.3,
        "pullback_max_bars":     20,
        "sl_anchor":             "last_pivot",
        "sl_buffer_atr_mult":    0.5,
        "risk_reward":           rr,
    }

    all_results = {}
    total_runs = len(TIMEFRAMES) * (len(YEARS) + 1)
    run_num = 0

    for ltf, htf in TIMEFRAMES:
        slug = _slug(ltf)
        # Full period
        run_num += 1
        print(f"\n[{run_num}/{total_runs}] {slug} / full 2021-2024 ...")
        r = _run_one(symbol, ltf, htf, "2021-01-01", "2024-12-31", params)
        if r:
            all_results[("full", ltf)] = r

        # Per year
        for year in YEARS:
            run_num += 1
            print(f"[{run_num}/{total_runs}] {slug} / {year} ...")
            r = _run_one(symbol, ltf, htf, f"{year}-01-01", f"{year}-12-31", params)
            if r:
                all_results[(year, ltf)] = r

    print("\n\nGenerating summary report...")
    report_md = build_summary_report(symbol, rr, all_results)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"IDX_{symbol.upper()}_SUMMARY.md"
    out_path.write_text(report_md, encoding="utf-8")
    print(f"Saved → {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-TF summary report for index backtest")
    parser.add_argument("--symbol", default="usatechidxusd")
    parser.add_argument("--rr", type=float, default=2.0, help="Risk:Reward (default: 2.0)")
    args = parser.parse_args()
    run_summary(symbol=args.symbol, rr=args.rr)
