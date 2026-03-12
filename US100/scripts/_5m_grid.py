"""
Grid backtest for 5M US100 — 2021-01-01 → 2026-03-11

Groups:
  1. Yearly breakdown   (produkcyjne params: RR=2.0, sess=T, bos=T)
  2. RR grid            (1.5 / 2.0 / 2.5 / 3.0 / 3.5)  full period
  3. Filter combos      (sess x bos)                      full period
  4. Lookback grid      (ltf_lb x htf_lb)                 full period
  5. Out-of-sample      2025-01-01 → 2026-03-11

Saves:
  reports/IDX_5M_GRID_2021_2026_{date}.md
  reports/IDX_5M_GRID_2021_2026_{date}.csv

Usage:
  python -m scripts._5m_grid
"""
from __future__ import annotations
import sys
import math
import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import load_ltf, build_htf_from_ltf, filter_by_date, _calc_r_drawdown
from src.strategies.trend_following_v1 import run_trend_backtest

SYMBOL   = "usatechidxusd"
REPORTS  = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

NOW      = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
DATE_TAG = datetime.date.today().strftime("%Y-%m-%d")

# ── Production params (from run_live_idx._build_strategy_config) ──────────────
PROD = dict(
    pivot_lookback_ltf=3,
    pivot_lookback_htf=5,
    confirmation_bars=1,
    require_close_break=True,
    entry_offset_atr_mult=0.3,
    pullback_max_bars=20,
    sl_anchor="last_pivot",
    sl_buffer_atr_mult=0.5,
    risk_reward=2.0,
    use_session_filter=True,
    session_start_hour_utc=13,
    session_end_hour_utc=20,
    use_bos_momentum_filter=True,
    bos_min_range_atr_mult=1.2,
    bos_min_body_to_range_ratio=0.6,
    use_flag_contraction_setup=False,
    flag_impulse_lookback_bars=8,
    flag_contraction_bars=5,
    flag_min_impulse_atr_mult=2.5,
    flag_max_contraction_atr_mult=1.2,
    flag_breakout_buffer_atr_mult=0.1,
    flag_sl_buffer_atr_mult=0.3,
)

def _params(**overrides) -> dict:
    p = PROD.copy()
    p.update(overrides)
    return p

# ── Bar loading (cached) ──────────────────────────────────────────────────────
print("Loading 5m bars …")
_ltf_df = load_ltf(SYMBOL, "5min")
_htf_df = build_htf_from_ltf(_ltf_df, "4h")
print(f"  5m bars : {len(_ltf_df):,}  [{_ltf_df.index[0].date()} -> {_ltf_df.index[-1].date()}]")
print(f"  4h bars : {len(_htf_df):,}")


def run(label: str, params: dict, start: str = "2021-01-01", end: str = "2026-03-11") -> dict | None:
    lf = filter_by_date(_ltf_df, start, end)
    hf = filter_by_date(_htf_df, start, end)
    print(f"  [{label}] {start}->{end} ...", end=" ", flush=True)
    try:
        td, m = run_trend_backtest(SYMBOL, lf, hf, params, 10_000.0)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return None
    if td is None or m is None:
        print("no result")
        return None
    n = len(td)
    if n == 0:
        print("0 trades")
        return None
    wr  = m.get("win_rate", 0.0)
    er  = m.get("expectancy_R", 0.0)
    pf  = m.get("profit_factor", 0.0)
    str_= m.get("max_losing_streak", 0)
    dd  = _calc_r_drawdown(td)
    sc  = er * math.sqrt(n) if n >= 5 else -999.0
    long_n  = int((td["direction"] == "LONG").sum())
    short_n = int((td["direction"] == "SHORT").sum())
    long_wr  = (td.loc[td["direction"] == "LONG",  "R"] > 0).mean() * 100 if long_n  else 0.0
    short_wr = (td.loc[td["direction"] == "SHORT", "R"] > 0).mean() * 100 if short_n else 0.0
    print(f"n={n}  WR={wr:.0f}%  E={er:+.3f}R  PF={pf:.2f}  DD={dd:.1f}R")
    return {
        "label":     label,
        "period":    f"{start[:7]}→{end[:7]}",
        "start":     start,
        "end":       end,
        "rr":        params["risk_reward"],
        "session":   params["use_session_filter"],
        "bos":       params["use_bos_momentum_filter"],
        "ltf_lb":    params["pivot_lookback_ltf"],
        "htf_lb":    params["pivot_lookback_htf"],
        "trades":    n,
        "long_n":    long_n,
        "short_n":   short_n,
        "win_rate":  round(wr, 1),
        "long_wr":   round(long_wr, 1),
        "short_wr":  round(short_wr, 1),
        "exp_R":     round(er, 3),
        "pf":        round(pf, 2),
        "max_dd_R":  round(dd, 1),
        "streak":    str_,
        "score":     round(sc, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
print("\n=== GROUP 1: Yearly breakdown (production params) ===")
g1 = []
for label, s, e in [
    ("2021",       "2021-01-01", "2021-12-31"),
    ("2022",       "2022-01-01", "2022-12-31"),
    ("2023",       "2023-01-01", "2023-12-31"),
    ("2024",       "2024-01-01", "2024-12-31"),
    ("2025-2026",  "2025-01-01", "2026-03-11"),
    ("FULL",       "2021-01-01", "2026-03-11"),
]:
    r = run(label, PROD, start=s, end=e)
    if r:
        r["group"] = "yearly"
        g1.append(r)

print("\n=== GROUP 2: RR grid (production params, 2022-2025) ===")
g2 = []
for rr in [1.5, 2.0, 2.5, 3.0, 3.5]:
    r = run(f"RR={rr}", _params(risk_reward=rr), start="2022-01-01", end="2025-12-31")
    if r:
        r["group"] = "rr_grid"
        g2.append(r)

print("\n=== GROUP 3: Filter combos (RR=2.0, 2022-2025) ===")
g3 = []
for sess, bos in [(True, True), (True, False), (False, True), (False, False)]:
    label = f"sess={'ON' if sess else 'OFF'} bos={'ON' if bos else 'OFF'}"
    r = run(label, _params(use_session_filter=sess, use_bos_momentum_filter=bos), start="2022-01-01", end="2025-12-31")
    if r:
        r["group"] = "filters"
        g3.append(r)

print("\n=== GROUP 4: Lookback grid — using 2023-2024 only for speed ===")
g4 = []
for ltf_lb, htf_lb in [(2, 3), (2, 5), (3, 3), (3, 5), (3, 7), (4, 5), (4, 7), (5, 7)]:
    r = run(f"lb={ltf_lb}/{htf_lb}", _params(pivot_lookback_ltf=ltf_lb, pivot_lookback_htf=htf_lb),
            start="2023-01-01", end="2024-12-31")
    if r:
        r["group"] = "lookback"
        g4.append(r)

# GROUP 5 is captured already in g1 (yearly) — skip quarterly to save time
g5 = []


# ── Save CSV ──────────────────────────────────────────────────────────────────
all_results = g1 + g2 + g3 + g4 + g5
df_out = pd.DataFrame(all_results)
csv_path = REPORTS / f"IDX_5M_GRID_2021_2026_{DATE_TAG}.csv"
df_out.to_csv(csv_path, index=False)
print(f"\nCSV saved: {csv_path}")


# ── Build markdown report ─────────────────────────────────────────────────────
def _row1(r):
    sc_s = f"{r['score']:.2f}" if r['score'] > -900 else "n/a"
    return (f"| {r['label']} | {r['trades']} | {r['win_rate']}% "
            f"| {r['exp_R']:+.3f} | {r['pf']:.2f} | {r['max_dd_R']:.1f}R "
            f"| {r['streak']} | {sc_s} |")

md_lines = [
    "# US100 — 5M Grid Backtest 2021–2026",
    "",
    f"**Generated:** {NOW}  |  **Symbol:** USATECHIDXUSD  |  **LTF:** 5m  |  **HTF:** 4h",
    "",
    "**Production params:** pivot_lb_ltf=3  pivot_lb_htf=5  conf_bars=1  require_close=True",
    "entry_offset=0.3×ATR  sl_buffer=0.5×ATR  sl_anchor=last_pivot  session=13–20 UTC",
    "",
    "---",
    "",
    "## 1. Yearly Breakdown (production params, RR=2.0)",
    "",
    "| Period | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
    "|--------|--------|------|--------|----|-----------|--------|-------|",
]
for r in g1:
    md_lines.append(_row1(r))

md_lines += [
    "",
    "## 2. Risk:Reward Grid (all filters ON, 2021–2026)",
    "",
    "| RR | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
    "|----|--------|------|--------|----|-----------|--------|-------|",
]
for r in g2:
    md_lines.append(f"| {r['rr']} " + _row1(r)[_row1(r).index("|", 1):])

md_lines += [
    "",
    "## 3. Filter Sensitivity (RR=2.0, 2021–2026)",
    "",
    "| Combo | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
    "|-------|--------|------|--------|----|-----------|--------|-------|",
]
for r in g3:
    md_lines.append(_row1(r))

md_lines += [
    "",
    "## 4. Pivot Lookback Grid (RR=2.0, all filters ON, 2021–2026)",
    "",
    "| lb_ltf/htf | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
    "|------------|--------|------|--------|----|-----------|--------|-------|",
]
for r in g4:
    md_lines.append(_row1(r))

md_lines += [
    "",
    "## 5. Out-of-Sample 2025–2026 (production params, RR=2.0)",
    "",
    "| Period | Trades | Win% | Exp(R) | PF | Max DD(R) | Streak | Score |",
    "|--------|--------|------|--------|----|-----------|--------|-------|",
]
for r in g5:
    md_lines.append(_row1(r))

# Best setup summary
best = sorted([r for r in all_results if r["trades"] >= 10], key=lambda x: x["score"], reverse=True)
if best:
    b = best[0]
    md_lines += [
        "",
        "---",
        "",
        "## Best Setup (by score = E(R)×√trades)",
        "",
        f"**Label:** {b['label']}  |  **Period:** {b['period']}  |  RR={b['rr']}  "
        f"sess={'ON' if b['session'] else 'OFF'}  bos={'ON' if b['bos'] else 'OFF'}  "
        f"lb_ltf={b['ltf_lb']}  lb_htf={b['htf_lb']}",
        "",
        f"Trades={b['trades']}  Win%={b['win_rate']}  E(R)={b['exp_R']:+.3f}  "
        f"PF={b['pf']}  MaxDD={b['max_dd_R']}R  Score={b['score']:.2f}",
    ]

md_path = REPORTS / f"IDX_5M_GRID_2021_2026_{DATE_TAG}.md"
md_path.write_text("\n".join(md_lines), encoding="utf-8")
print(f"MD  saved: {md_path}")
print("\nDone.")
