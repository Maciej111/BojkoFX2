"""
Batch backtest runner for US100 — collects results across multiple
timeframe combos, RR values and sub-periods.

Usage:
    python scripts/_batch_backtest.py

Results are printed as a summary table and saved to
reports/US100_BATCH_BACKTEST_RESULTS.md
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import run_backtest, load_ltf, build_htf_from_ltf, _calc_r_drawdown

SYMBOL = "usatechidxusd"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

# ── bar cache so we don't reload CSVs repeatedly ──────────────────────────
_bar_cache: dict = {}

def get_bars(ltf: str, htf: str):
    key = (ltf, htf)
    if key not in _bar_cache:
        ltf_df = load_ltf(SYMBOL, ltf)
        htf_df = build_htf_from_ltf(ltf_df, htf)
        _bar_cache[key] = (ltf_df, htf_df)
    return _bar_cache[key]


def _run(label: str, ltf: str, htf: str, rr: float,
         start: str = "2021-01-01", end: str = "2026-03-07",
         session_filter: bool = True,
         bos_filter: bool = True,
         ltf_lb: int = 3, htf_lb: int = 5) -> dict | None:
    """Single backtest run returning a flat metrics dict."""
    params = {
        "pivot_lookback_ltf":          ltf_lb,
        "pivot_lookback_htf":          htf_lb,
        "confirmation_bars":           1,
        "require_close_break":         True,
        "entry_offset_atr_mult":       0.3,
        "pullback_max_bars":           20,
        "sl_anchor":                   "last_pivot",
        "sl_buffer_atr_mult":          0.5,
        "risk_reward":                 rr,
        "use_session_filter":          session_filter,
        "session_start_hour_utc":      13,
        "session_end_hour_utc":        20,
        "use_bos_momentum_filter":     bos_filter,
        "bos_min_range_atr_mult":      1.2,
        "bos_min_body_to_range_ratio": 0.6,
        "use_flag_contraction_setup":  False,
        "flag_impulse_lookback_bars":  8,
        "flag_contraction_bars":       5,
        "flag_min_impulse_atr_mult":   2.5,
        "flag_max_contraction_atr_mult": 1.2,
        "flag_breakout_buffer_atr_mult": 0.1,
        "flag_sl_buffer_atr_mult":     0.3,
    }
    print(f"  [{label}] {ltf}/{htf} RR={rr} {start}->{end} sess={session_filter} bos={bos_filter} ...")
    try:
        trades_df, metrics = run_backtest(
            symbol=SYMBOL,
            start=start,
            end=end,
            params=params,
            ltf=ltf,
            htf=htf,
        )
    except Exception as e:
        print(f"    ERROR: {e}")
        return None

    if trades_df is None or metrics is None:
        return None

    r_dd = _calc_r_drawdown(trades_df)
    n = metrics.get("trades_count", 0)
    wr = metrics.get("win_rate", 0)
    er = metrics.get("expectancy_R", 0)
    pf = metrics.get("profit_factor", 0)
    streak = metrics.get("max_losing_streak", 0)

    long_n = len(trades_df[trades_df["direction"] == "LONG"]) if n else 0
    short_n = len(trades_df[trades_df["direction"] == "SHORT"]) if n else 0
    long_wr = (trades_df[trades_df["direction"] == "LONG"]["R"] > 0).mean() * 100 if long_n else 0
    short_wr = (trades_df[trades_df["direction"] == "SHORT"]["R"] > 0).mean() * 100 if short_n else 0

    return {
        "label":       label,
        "ltf":         ltf,
        "htf":         htf,
        "rr":          rr,
        "period":      f"{start[:7]}-{end[:7]}",
        "session":     session_filter,
        "bos_filter":  bos_filter,
        "trades":      n,
        "win_rate":    round(wr, 1),
        "exp_R":       round(er, 3),
        "pf":          round(pf, 2),
        "max_dd_R":    round(r_dd, 1),
        "streak":      streak,
        "long_n":      long_n,
        "short_n":     short_n,
        "long_wr":     round(long_wr, 1),
        "short_wr":    round(short_wr, 1),
    }


def run_all():
    results = []

    # ── 1. Timeframe matrix (all filters on) ────────────────────────────────
    print("\n=== GROUP 1: Timeframe matrix ===")
    for ltf, htf in [("1h", "4h"), ("30min", "1h"), ("15min", "1h")]:
        for rr in [2.0, 2.5]:
            r = _run(f"{ltf}/{htf} RR{rr}", ltf, htf, rr)
            if r:
                results.append(r)

    # ── 2. Session filter impact (30m/1h, RR 2.0) ────────────────────────────
    print("\n=== GROUP 2: Filter sensitivity (30m/1h) ===")
    for sess, bos in [(True, True), (True, False), (False, True), (False, False)]:
        label = f"sess={sess} bos={bos}"
        r = _run(label, "30min", "1h", 2.0, session_filter=sess, bos_filter=bos)
        if r:
            results.append(r)

    # ── 3. RR grid (30m/1h, all filters on) ─────────────────────────────────
    print("\n=== GROUP 3: RR grid (30m/1h) ===")
    for rr in [1.5, 2.0, 2.5, 3.0]:
        r = _run(f"RR={rr}", "30min", "1h", rr)
        if r:
            results.append(r)

    # ── 4. Sub-period analysis (30m/1h, RR 2.0, all filters on) ─────────────
    print("\n=== GROUP 4: Sub-periods ===")
    sub_periods = [
        ("2021-01-01", "2021-12-31", "2021"),
        ("2022-01-01", "2022-12-31", "2022"),
        ("2023-01-01", "2023-12-31", "2023"),
        ("2024-01-01", "2024-12-31", "2024"),
        ("2025-01-01", "2026-03-07", "2025-26 OOS"),
    ]
    for start, end, period_label in sub_periods:
        r = _run(period_label, "30min", "1h", 2.0, start=start, end=end)
        if r:
            results.append(r)

    # ── 5. Lookback sensitivity (30m/1h, RR 2.0) ────────────────────────────
    print("\n=== GROUP 5: Lookback sensitivity (30m/1h) ===")
    for ltf_lb, htf_lb in [(2, 3), (3, 5), (4, 7)]:
        r = _run(f"lb_ltf={ltf_lb} lb_htf={htf_lb}", "30min", "1h", 2.0,
                 ltf_lb=ltf_lb, htf_lb=htf_lb)
        if r:
            results.append(r)

    return results


def score(r: dict) -> float:
    """Composite score: expectancy * sqrt(trades) — penalises too-few trades."""
    import math
    if r["trades"] < 5:
        return -999.0
    return r["exp_R"] * math.sqrt(r["trades"])


def build_md_report(results: list[dict]) -> str:
    import math, datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def fmt(val, fmt_str=""):
        return format(val, fmt_str) if val is not None else "—"

    lines = [
        "# US100 Backtest Report (Post-Fix)",
        "",
        f"**Generated:** {now}  |  **Symbol:** USATECHIDXUSD  |  **Data:** 2021-01-01 → 2026-03-07",
        "",
        "**Fixes included in this run:**",
        "- BUG-US-01: No lookahead in `precompute_pivots()`",
        "- BUG-US-02: ATR uses Wilder EWM (not rolling mean)",
        "- BUG-US-03: Equity curve is R-compounded (not × 100 000)",
        "- BUG-US-04: Session filter boundary `<= session_end` (inclusive)",
        "- BUG-US-05: State persisted under correct symbol key",
        "",
        "---",
        "",
    ]

    # Score the primary entries (group 1 + RR grid)
    top = sorted([r for r in results if r["trades"] >= 5], key=lambda x: score(x), reverse=True)

    lines += [
        "## 1. Full-Period Results — Timeframe Matrix",
        "",
        "| LTF | HTF | RR | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
        "|-----|-----|----|--------|------|--------|----|-----------|--------|-------|",
    ]
    group1 = [r for r in results if r["label"].startswith(("1h/", "30min/", "15min/")) or "/" in r["label"] and "RR" in r["label"] and "sess" not in r["label"] and "lb" not in r["label"] and "202" not in r["label"]]
    for r in group1:
        sc = score(r)
        sc_str = f"{sc:.2f}" if sc > -900 else "n/a"
        lines.append(
            f"| {r['ltf']} | {r['htf']} | {r['rr']} | {r['trades']} "
            f"| {r['win_rate']}% | {r['exp_R']:+.3f} | {r['pf']:.2f} "
            f"| {r['max_dd_R']:.1f}R | {r['streak']} | {sc_str} |"
        )

    lines += [
        "",
        "## 2. Filter Sensitivity (30m/1h, RR 2.0)",
        "",
        "| Session Filter | BOS Filter | Trades | Win% | Exp(R) | PF | Max DD(R) |",
        "|----------------|------------|--------|------|--------|----|-----------|",
    ]
    group2 = [r for r in results if "sess=" in r["label"]]
    for r in group2:
        lines.append(
            f"| {'on' if r['session'] else 'off'} | {'on' if r['bos_filter'] else 'off'} "
            f"| {r['trades']} | {r['win_rate']}% | {r['exp_R']:+.3f} | {r['pf']:.2f} "
            f"| {r['max_dd_R']:.1f}R |"
        )

    lines += [
        "",
        "## 3. Risk:Reward Grid (30m/1h, all filters on)",
        "",
        "| RR | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
        "|----|--------|------|--------|----|-----------|--------|-------|",
    ]
    group3 = [r for r in results if r["label"].startswith("RR=")]
    for r in group3:
        sc = score(r)
        sc_str = f"{sc:.2f}" if sc > -900 else "n/a"
        lines.append(
            f"| {r['rr']} | {r['trades']} | {r['win_rate']}% | {r['exp_R']:+.3f} "
            f"| {r['pf']:.2f} | {r['max_dd_R']:.1f}R | {r['streak']} | {sc_str} |"
        )

    lines += [
        "",
        "## 4. Year-by-Year Breakdown (30m/1h, RR 2.0)",
        "",
        "| Period | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak |",
        "|--------|--------|------|--------|----|-----------|--------|",
    ]
    group4 = [r for r in results if r["period"] != "2021-01-2026-03" and
              any(r["label"].startswith(p) for p in ["2021", "2022", "2023", "2024", "2025"])]
    for r in group4:
        lines.append(
            f"| {r['label']} | {r['trades']} | {r['win_rate']}% "
            f"| {r['exp_R']:+.3f} | {r['pf']:.2f} | {r['max_dd_R']:.1f}R "
            f"| {r['streak']} |"
        )

    lines += [
        "",
        "## 5. Lookback Sensitivity (30m/1h, RR 2.0)",
        "",
        "| LTF lb | HTF lb | Trades | Win% | Exp(R) | PF | Max DD(R) |",
        "|--------|--------|--------|------|--------|----|-----------|",
    ]
    group5 = [r for r in results if r["label"].startswith("lb_")]
    for r in group5:
        lb_ltf = r["label"].split("lb_ltf=")[1].split(" ")[0]
        lb_htf = r["label"].split("lb_htf=")[1]
        lines.append(
            f"| {lb_ltf} | {lb_htf} | {r['trades']} | {r['win_rate']}% "
            f"| {r['exp_R']:+.3f} | {r['pf']:.2f} | {r['max_dd_R']:.1f}R |"
        )

    # Best config
    if top:
        best = top[0]
        lines += [
            "",
            "## 6. Best Configuration",
            "",
            f"**{best['label']}**  |  LTF: {best['ltf']}  |  HTF: {best['htf']}  "
            f"|  RR: {best['rr']}  |  Score: {score(best):.2f}",
            "",
            f"- Trades: {best['trades']}",
            f"- Win rate: {best['win_rate']}%",
            f"- Expectancy: {best['exp_R']:+.3f}R",
            f"- Profit factor: {best['pf']:.2f}",
            f"- Max R drawdown: {best['max_dd_R']:.1f}R",
            f"- Max losing streak: {best['streak']}",
            f"- LONG: {best['long_n']} trades ({best['long_wr']:.1f}% WR)",
            f"- SHORT: {best['short_n']} trades ({best['short_wr']:.1f}% WR)",
        ]

    lines += [
        "",
        "## 7. Strategy Health Assessment",
        "",
        "| Check | Threshold | Result |",
        "|-------|-----------|--------|",
    ]

    # Best 30m/1h RR2.0
    ref = next((r for r in results if r["label"] == "sess=True bos=True" and r["ltf"] == "30min"), None)
    if ref is None:
        ref = next((r for r in results if r["ltf"] == "30min" and r["rr"] == 2.0), None)

    if ref:
        checks = [
            ("Expectancy > 0", ref["exp_R"] > 0, f"{ref['exp_R']:+.3f}R"),
            ("Profit factor > 1.0", ref["pf"] > 1.0, f"{ref['pf']:.2f}"),
            ("Win rate ≥ 30%", ref["win_rate"] >= 30, f"{ref['win_rate']}%"),
            ("Max DD < 15R", ref["max_dd_R"] < 15, f"{ref['max_dd_R']:.1f}R"),
            ("Max streak ≤ 8", ref["streak"] <= 8, str(ref["streak"])),
            ("Trades ≥ 30 / 5yr", ref["trades"] >= 30, str(ref["trades"])),
        ]
        for name, passed, val in checks:
            icon = "PASS" if passed else "FAIL"
            lines.append(f"| {name} | — | {icon}: {val} |")

    lines += [
        "",
        "---",
        "",
        "_Report generated by `scripts/_batch_backtest.py`_",
    ]

    return "\n".join(lines)


if __name__ == "__main__":
    print("Starting US100 batch backtest...\n")
    results = run_all()

    print("\n\n" + "="*70)
    print("SUMMARY TABLE")
    print("="*70)
    for r in results:
        import math
        sc = score(r)
        sc_str = f"{sc:+.2f}" if sc > -900 else "n/a "
        print(
            f"  [{r['label']:<30}]  "
            f"Trades={r['trades']:>3}  WR={r['win_rate']:>5.1f}%  "
            f"E(R)={r['exp_R']:>+.3f}  PF={r['pf']:.2f}  "
            f"DD={r['max_dd_R']:.1f}R  Score={sc_str}"
        )

    report_md = build_md_report(results)
    out = ROOT / "reports" / "US100_BATCH_BACKTEST_RESULTS.md"
    out.write_text(report_md, encoding="utf-8")
    print(f"\nReport saved -> {out}")
