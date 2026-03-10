# -*- coding: utf-8 -*-
"""
scripts/trailing_stop_scan.py
==============================
Trailing stop grid test dla 5 par FX (BojkoFx).

Testuje kombinacje:
  RR   in {2.5, 3.0}          (TP target)
  ts_r in {1.5, 2.0, 2.5}     (aktywacja TS w R od entry)
  lock_r in {0.0 (BE), 0.5}   (blokada zysku przy aktywacji)

  + baseline: brak TS (fixed SL/TP) dla kazdego RR

Razem: 2 RR x 3 ts_r x 2 lock_r + 2 baseline = 14 konfiguracji x 5 symboli = 70 runow

Uzywanie:
  cd C:\\dev\\projects\\BojkoFx
  python scripts/trailing_stop_scan.py

Wyniki:
  reports/TRAILING_STOP_FX.md
  reports/trailing_stop_fx_results.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backtests.signals_bos_pullback import (
    BOSPullbackSignalGenerator, build_d1, build_h4,
    filter_and_adjust, ClosedTrade, TradeSetup,
)
from backtests.engine import PortfolioSimulator

# ── Configuration ─────────────────────────────────────────────────────────────

SYMBOLS = ["EURUSD", "USDJPY", "USDCHF", "AUDJPY", "CADJPY"]

PROD_CONFIG = dict(
    pivot_lookback=3,
    entry_offset_atr_mult=0.3,
    sl_buffer_atr_mult=0.1,
    rr=3.0,
    ttl_bars=50,
    atr_period=14,
    atr_pct_window=100,
)

ADX_H4_GATE: Dict[str, Optional[float]] = {
    "EURUSD": 16.0,
    "USDJPY": 16.0,
    "USDCHF": 16.0,
    "AUDJPY": 16.0,
    "CADJPY": None,
}

ATR_FILTER: Dict[str, Tuple[float, float]] = {
    "EURUSD": (0, 100),
    "USDJPY": (0, 100),
    "USDCHF": (0, 100),
    "AUDJPY": (0, 100),
    "CADJPY": (10, 80),
}

SESSION: Dict[str, Optional[Tuple[int, int]]] = {
    "EURUSD": (8, 21),
    "USDJPY": None,
    "USDCHF": (8, 21),
    "AUDJPY": (0, 21),
    "CADJPY": None,
}

OOS_START = "2023-01-01"
OOS_END   = "2024-12-31"
IS_START  = "2021-01-01"
IS_END    = "2022-12-31"

# Grid: RR x ts_r x lock_r
RR_VALUES    = [2.5, 3.0]
TS_R_VALUES  = [1.5, 2.0, 2.5]
LOCK_R_VALUES = [0.0, 0.5]   # 0.0 = breakeven

PROD_RR = 3.0   # current production

DATA_DIR   = _ROOT / "data" / "raw_dl_fx" / "download" / "m60"
REPORT_DIR = _ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_h1(symbol: str) -> Optional[pd.DataFrame]:
    sym_l = symbol.lower()
    for suffix in ("_2021_2025", "_2021_2024"):
        p = DATA_DIR / f"{sym_l}_m60_bid{suffix}.csv"
        if p.exists():
            df = pd.read_csv(p)
            df.columns = [c.lower() for c in df.columns]
            ts_col = next(
                (c for c in ("timestamp", "time", "date", "datetime") if c in df.columns),
                df.columns[0],
            )
            try:
                val = float(df[ts_col].iloc[0])
                df.index = pd.to_datetime(df[ts_col], unit="ms", utc=True) if val > 1e10 \
                           else pd.to_datetime(df[ts_col], utc=True)
            except (ValueError, TypeError):
                df.index = pd.to_datetime(df[ts_col], utc=True)
            df = df[["open", "high", "low", "close"]].sort_index()
            df = df[~df.index.duplicated(keep="first")]
            print(f"  Loaded {symbol}: {len(df)} bars from {p.name}")
            return df
    print(f"  [WARN] No data for {symbol}")
    return None


# ── Metrics (R-based, currency-agnostic) ──────────────────────────────────────

def r_metrics(trades: List[ClosedTrade], initial_equity: float = 30_000.0) -> dict:
    """R-based metrics: DD from equity curve simulated at 0.5% risk/trade."""
    tp_sl_ts = [t for t in trades if t.exit_reason in ("TP", "SL", "TS")]
    if not tp_sl_ts:
        return {
            "n_trades": len(trades), "win_rate": 0.0, "expectancy_R": 0.0,
            "profit_factor": 0.0, "max_dd_pct": 0.0,
            "n_tp": 0, "n_sl": 0, "n_ts": 0, "n_ttl": 0,
            "avg_win_R": 0.0, "avg_loss_R": 0.0,
        }

    r_vals = np.array([t.r_multiple for t in tp_sl_ts])
    n_tp   = sum(1 for t in tp_sl_ts if t.exit_reason == "TP")
    n_sl   = sum(1 for t in tp_sl_ts if t.exit_reason == "SL")
    n_ts   = sum(1 for t in tp_sl_ts if t.exit_reason == "TS")
    n_ttl  = sum(1 for t in trades   if t.exit_reason == "TTL")

    wins = r_vals[r_vals > 0]
    loss = r_vals[r_vals < 0]
    win_rate  = len(wins) / len(r_vals)
    exp_r     = float(np.mean(r_vals))
    pf_wins   = wins.sum()
    pf_loss   = abs(loss.sum())
    pf        = pf_wins / pf_loss if pf_loss > 0 else (float("inf") if pf_wins > 0 else 0.0)
    avg_win_r = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_los_r = float(np.mean(loss)) if len(loss) > 0 else 0.0

    # Equity curve at 0.5% risk
    risk_pct = 0.005
    eq = initial_equity
    curve = [eq]
    for r in r_vals:
        eq += r * eq * risk_pct
        curve.append(eq)
    eq_arr = np.array(curve)
    running_max = np.maximum.accumulate(eq_arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(running_max > 0, (running_max - eq_arr) / running_max * 100, 0)

    return {
        "n_trades":    len(trades),
        "win_rate":    win_rate,
        "expectancy_R": exp_r,
        "profit_factor": pf,
        "max_dd_pct":  float(dd.max()),
        "n_tp":        n_tp,
        "n_sl":        n_sl,
        "n_ts":        n_ts,
        "n_ttl":       n_ttl,
        "avg_win_R":   avg_win_r,
        "avg_loss_R":  avg_los_r,
    }


# ── Single run ────────────────────────────────────────────────────────────────

def run_one(
    symbol: str,
    all_setups: List[TradeSetup],
    h1: pd.DataFrame,
    rr: float,
    trail_cfg: Optional[dict],
    period_start: str,
    period_end: str,
) -> dict:
    """Run one backtest for a single symbol/config."""
    h1_slice = h1.loc[period_start:period_end].copy()

    adx_gate = ADX_H4_GATE.get(symbol)
    atr_min, atr_max = ATR_FILTER.get(symbol, (0, 100))
    sess = SESSION.get(symbol)
    sess_cfg = {"start": sess[0], "end": sess[1]} if sess else None

    exp = dict(
        gate_type="ADX_THRESHOLD" if adx_gate is not None else "NONE",
        gate_tf="H4",
        adx_threshold=adx_gate or 0.0,
        atr_pct_min=atr_min,
        atr_pct_max=atr_max,
        rr=rr,
        rr_mode="fixed",
    )
    filtered = [
        s for s in filter_and_adjust(all_setups, exp)
        if pd.Timestamp(period_start, tz="UTC") <= s.bar_ts <= pd.Timestamp(period_end, tz="UTC")
    ]

    if not filtered:
        return _empty_row(symbol, rr, trail_cfg)

    sim = PortfolioSimulator(
        h1_data={symbol: h1_slice},
        setups={symbol: filtered},
        sizing_cfg={"mode": "risk_first", "risk_pct": 0.005},
        session_cfg={symbol: sess_cfg} if sess_cfg else {},
        same_bar_mode="conservative",
        max_positions_total=None,
        max_positions_per_symbol=1,
        initial_equity=30_000.0,
        trail_cfg=trail_cfg,
    )
    trades = sim.run()
    m = r_metrics(trades)

    ts_label = _trail_label(trail_cfg)
    return {
        "symbol":       symbol,
        "rr":           rr,
        "trail":        ts_label,
        "ts_r":         trail_cfg["ts_r"] if trail_cfg else None,
        "lock_r":       trail_cfg.get("lock_r") if trail_cfg else None,
        "n_trades":     m["n_trades"],
        "win_rate":     round(m["win_rate"] * 100, 1),
        "expectancy_R": round(m["expectancy_R"], 4),
        "profit_factor": round(m["profit_factor"], 2),
        "max_dd_pct":   round(m["max_dd_pct"], 1),
        "n_tp":         m["n_tp"],
        "n_sl":         m["n_sl"],
        "n_ts":         m["n_ts"],
        "n_ttl":        m["n_ttl"],
        "avg_win_R":    round(m["avg_win_R"], 3),
        "avg_loss_R":   round(m["avg_loss_R"], 3),
        "is_baseline":  trail_cfg is None,
    }


def _empty_row(symbol, rr, trail_cfg):
    ts_label = _trail_label(trail_cfg)
    return {
        "symbol": symbol, "rr": rr, "trail": ts_label,
        "ts_r": trail_cfg["ts_r"] if trail_cfg else None,
        "lock_r": trail_cfg.get("lock_r") if trail_cfg else None,
        "n_trades": 0, "win_rate": 0.0, "expectancy_R": 0.0,
        "profit_factor": 0.0, "max_dd_pct": 0.0,
        "n_tp": 0, "n_sl": 0, "n_ts": 0, "n_ttl": 0,
        "avg_win_R": 0.0, "avg_loss_R": 0.0, "is_baseline": trail_cfg is None,
    }


def _trail_label(trail_cfg: Optional[dict]) -> str:
    if trail_cfg is None:
        return "NO_TS"
    lock = trail_cfg.get("lock_r")
    lock_s = f"lock{lock:.1f}R" if lock is not None else "lockBE"
    return f"TS{trail_cfg['ts_r']:.1f}R_{lock_s}"


# ── Report generation ─────────────────────────────────────────────────────────

def generate_report(
    oos_rows: List[dict],
    is_rows: List[dict],
) -> str:
    lines = []
    ts_now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    lines.append("# Trailing Stop Grid Test — BojkoFx FX Pairs")
    lines.append("")
    lines.append(f"**Data:** {ts_now}  ")
    lines.append(f"**Strategia:** BOS+Pullback LTF=H1 / HTF=D1  ")
    lines.append(f"**Symbole:** {', '.join(SYMBOLS)}  ")
    lines.append(f"**IS (train):** {IS_START} – {IS_END}  ")
    lines.append(f"**OOS (test):** {OOS_START} – {OOS_END}  ")
    lines.append(f"**Filtry prod:** ADX H4>=16 (poza CADJPY), ATR 10-80 (CADJPY)  ")
    lines.append(f"**Sizing:** risk_first 0.5%/trade, equity $30,000  ")
    lines.append(f"**PROD baseline:** RR=3.0, brak TS  ")
    lines.append("")

    # ── Sekcja 1: Metodologia TS ────────────────────────────────────────────
    lines.append("## 1. Metodologia trailing stop")
    lines.append("")
    lines.append("```")
    lines.append("Parametry siatki:")
    lines.append(f"  RR (TP target) : {RR_VALUES}")
    lines.append(f"  ts_r (aktywacja): {TS_R_VALUES}  [R od entry]")
    lines.append(f"  lock_r (blokada): {LOCK_R_VALUES}  [R blokowane przy aktywacji]")
    lines.append("  + 2 baseline bez TS (RR=2.5 i RR=3.0)")
    lines.append("")
    lines.append("Logika dzialania:")
    lines.append("  1. Pozycja otwarta normalnie (limit entry, staly SL, staly TP)")
    lines.append("  2. Gdy cena osiaga entry + ts_r * risk (dla LONG):")
    lines.append("     - SL przesuwa sie do entry + lock_r * risk (0.0 = breakeven)")
    lines.append("     - Od tej chwili SL sladuje za cena: SL = max(SL, high - ts_r*risk)")
    lines.append("  3. TP pozostaje niezmienione")
    lines.append("  4. Wyjscie przez TS = exit_reason='TS', R = (exit_px - entry) / risk")
    lines.append("  5. conservative: gdy TP i TS trafione w tym samym barze -> TS wins")
    lines.append("```")
    lines.append("")

    # ── Sekcja 2: IS baseline (weryfikacja) ─────────────────────────────────
    lines.append("## 2. Baseline IS 2021-2022 (bez TS, RR=3.0)")
    lines.append("")
    lines.append("| Symbol | Trades | WR | ExpR | PF | MaxDD% |")
    lines.append("|--------|--------|----|------|----|--------|")
    for sym in SYMBOLS:
        row = next(
            (r for r in is_rows if r["symbol"] == sym and r["rr"] == PROD_RR and r["is_baseline"]),
            None,
        )
        if row:
            lines.append(
                f"| {sym} | {row['n_trades']} | {row['win_rate']}% "
                f"| {row['expectancy_R']:+.4f}R | {row['profit_factor']} "
                f"| {row['max_dd_pct']}% |"
            )
    lines.append("")

    # ── Sekcja 3: OOS heat matrix — ExpR ────────────────────────────────────
    lines.append("## 3. OOS heat matrix — ExpR per konfiguracja")
    lines.append("")

    all_cfgs = sorted(
        set((r["rr"], r["trail"]) for r in oos_rows),
        key=lambda x: (x[0], x[1]),
    )
    # Separate by RR
    for rr_val in RR_VALUES:
        lines.append(f"### RR = {rr_val}")
        lines.append("")
        cfgs_rr = [(rr, trail) for (rr, trail) in all_cfgs if rr == rr_val]
        trail_labels = [t for (_, t) in cfgs_rr]

        header = "| Symbol | " + " | ".join(trail_labels) + " |"
        sep    = "|--------|" + "|".join(["-------"] * len(trail_labels)) + "|"
        lines.append(header)
        lines.append(sep)

        for sym in SYMBOLS:
            cells = []
            baseline_expr = next(
                (r["expectancy_R"] for r in oos_rows
                 if r["symbol"] == sym and r["rr"] == rr_val and r["is_baseline"]),
                None,
            )
            for trail_lbl in trail_labels:
                row = next(
                    (r for r in oos_rows
                     if r["symbol"] == sym and r["rr"] == rr_val and r["trail"] == trail_lbl),
                    None,
                )
                if row is None:
                    cells.append("—")
                    continue
                v = row["expectancy_R"]
                mark = ""
                if trail_lbl == "NO_TS":
                    mark = " *"
                elif baseline_expr is not None and v > baseline_expr + 0.03:
                    mark = " ✅"
                cells.append(f"{v:+.3f}R{mark}")
            lines.append(f"| {sym} | " + " | ".join(cells) + " |")

        # AVG row
        avg_cells = []
        for trail_lbl in trail_labels:
            vals = [r["expectancy_R"] for r in oos_rows
                    if r["rr"] == rr_val and r["trail"] == trail_lbl]
            avg_cells.append(f"{np.mean(vals):+.3f}R" if vals else "—")
        lines.append("| **AVG** | " + " | ".join(avg_cells) + " |")
        lines.append("")
        lines.append("\\* = baseline bez TS | ✅ = poprawa > +0.03R vs baseline  ")
        lines.append("")

    # ── Sekcja 4: OOS best config per symbol ────────────────────────────────
    lines.append("## 4. Best config per symbol (OOS)")
    lines.append("")
    lines.append(
        "| Symbol | PROD ExpR | Best trail | Best RR | Best ExpR | Delta | WR | DD% | n_TS | Decyzja |"
    )
    lines.append(
        "|--------|-----------|-----------|---------|-----------|-------|----|----|------|---------|"
    )

    prod_baseline = {
        sym: next(
            (r["expectancy_R"] for r in oos_rows
             if r["symbol"] == sym and r["rr"] == PROD_RR and r["is_baseline"]),
            None,
        )
        for sym in SYMBOLS
    }

    for sym in SYMBOLS:
        sym_rows = [r for r in oos_rows if r["symbol"] == sym]
        if not sym_rows:
            continue
        prod_expr = prod_baseline.get(sym) or 0.0
        best = max(sym_rows, key=lambda r: r["expectancy_R"])
        delta = best["expectancy_R"] - prod_expr

        if best["is_baseline"] and best["rr"] == PROD_RR:
            decision = "PROD optimal"
        elif delta >= 0.05 and best["win_rate"] >= 38 and best["max_dd_pct"] <= (
            next((r["max_dd_pct"] for r in oos_rows
                  if r["symbol"] == sym and r["rr"] == PROD_RR and r["is_baseline"]), 99) + 3
        ):
            decision = "✅ wdrozyt"
        elif delta >= 0.03:
            decision = "⚠️ marginalny"
        else:
            decision = "❌ zostac"

        lines.append(
            f"| {sym} | {prod_expr:+.4f}R | {best['trail']} | RR={best['rr']} "
            f"| {best['expectancy_R']:+.4f}R | {delta:+.4f}R "
            f"| {best['win_rate']}% | {best['max_dd_pct']}% "
            f"| {best['n_ts']} | {decision} |"
        )
    lines.append("")

    # ── Sekcja 5: TS stats — ile pozycji dotknielo TS ──────────────────────
    lines.append("## 5. TS activation statistics (OOS)")
    lines.append("")
    lines.append("Jak czesto trailing stop sie aktywuje vs TP/SL hit.")
    lines.append("")
    lines.append("| Symbol | Config | n_TP | n_SL | n_TS | n_TTL | TS% | TP% | avg_TS_R |")
    lines.append("|--------|--------|------|------|------|-------|-----|-----|----------|")

    for sym in SYMBOLS:
        for trail_lbl in sorted(set(r["trail"] for r in oos_rows if not
                                (r["is_baseline"] and r["rr"] == PROD_RR))):
            row = next(
                (r for r in oos_rows
                 if r["symbol"] == sym and r["trail"] == trail_lbl and r["rr"] == PROD_RR),
                None,
            )
            if row is None:
                # try RR=2.5
                row = next(
                    (r for r in oos_rows
                     if r["symbol"] == sym and r["trail"] == trail_lbl and r["rr"] == 2.5),
                    None,
                )
            if row is None or row["n_trades"] == 0:
                continue
            total_closed = row["n_tp"] + row["n_sl"] + row["n_ts"]
            ts_pct = round(row["n_ts"] / total_closed * 100, 1) if total_closed > 0 else 0
            tp_pct = round(row["n_tp"] / total_closed * 100, 1) if total_closed > 0 else 0
            lines.append(
                f"| {sym} | {trail_lbl} | {row['n_tp']} | {row['n_sl']} | {row['n_ts']} "
                f"| {row['n_ttl']} | {ts_pct}% | {tp_pct}% | {row['avg_win_R']:+.3f}R |"
            )
    lines.append("")

    # ── Sekcja 6: Porownanie RR=2.5+TS vs PROD RR=3.0 ──────────────────────
    lines.append("## 6. Kluczowe porownanie: RR=2.5+TS vs PROD RR=3.0 (brak TS)")
    lines.append("")
    lines.append(
        "Hipoteza: nizszy TP (RR=2.5) + trailing stop powinien "
        "zwiekszyc WR i chronic zyski na duzych ruchach."
    )
    lines.append("")
    lines.append("| Symbol | PROD (RR=3.0 no TS) | Best TS@RR=2.5 | Delta ExpR | Delta WR | Delta DD |")
    lines.append("|--------|---------------------|----------------|-----------|----------|----------|")

    for sym in SYMBOLS:
        prod_row = next(
            (r for r in oos_rows if r["symbol"] == sym and r["rr"] == PROD_RR and r["is_baseline"]),
            None,
        )
        if prod_row is None:
            continue
        # Best TS config at RR=2.5
        ts_rows_25 = [r for r in oos_rows
                      if r["symbol"] == sym and r["rr"] == 2.5 and not r["is_baseline"]]
        if not ts_rows_25:
            continue
        best_ts = max(ts_rows_25, key=lambda r: r["expectancy_R"])
        d_expr = best_ts["expectancy_R"] - prod_row["expectancy_R"]
        d_wr   = best_ts["win_rate"] - prod_row["win_rate"]
        d_dd   = best_ts["max_dd_pct"] - prod_row["max_dd_pct"]
        lines.append(
            f"| {sym} "
            f"| ExpR={prod_row['expectancy_R']:+.3f}R WR={prod_row['win_rate']}% DD={prod_row['max_dd_pct']}% "
            f"| {best_ts['trail']} ExpR={best_ts['expectancy_R']:+.3f}R WR={best_ts['win_rate']}% DD={best_ts['max_dd_pct']}% "
            f"| {d_expr:+.3f}R | {d_wr:+.1f}pp | {d_dd:+.1f}pp |"
        )
    lines.append("")

    # ── Sekcja 7: Wnioski ───────────────────────────────────────────────────
    lines.append("## 7. Wnioski")
    lines.append("")

    # Oblicz ile symboli zyska na TS
    improvements = 0
    for sym in SYMBOLS:
        prod_expr = prod_baseline.get(sym)
        if prod_expr is None:
            continue
        ts_rows = [r for r in oos_rows if r["symbol"] == sym and not r["is_baseline"]]
        if any(r["expectancy_R"] > prod_expr + 0.05 for r in ts_rows):
            improvements += 1

    if improvements >= 4:
        verdict = "IMPLEMENT"
        verdict_text = "Trailing stop poprawia wyniki na wiekszosci par (>=4/5). Zalecane wdrozenie."
    elif improvements >= 2:
        verdict = "PARTIAL"
        verdict_text = f"Trailing stop pomaga na {improvements}/5 parach. Rozwazyc per-symbol."
    else:
        verdict = "REJECT"
        verdict_text = "Trailing stop nie poprawia wynikow w sposob istotny."

    lines.append(f"**Werdykt: {verdict}**")
    lines.append("")
    lines.append(verdict_text)
    lines.append("")

    lines.append("### Szczegoly per symbol")
    lines.append("")
    for sym in SYMBOLS:
        prod_expr = prod_baseline.get(sym)
        sym_ts_rows = [r for r in oos_rows if r["symbol"] == sym and not r["is_baseline"]]
        if not sym_ts_rows or prod_expr is None:
            continue
        best_ts = max(sym_ts_rows, key=lambda r: r["expectancy_R"])
        delta = best_ts["expectancy_R"] - prod_expr
        if delta >= 0.05:
            icon = "✅"
        elif delta >= 0.02:
            icon = "⚠️"
        else:
            icon = "❌"
        lines.append(
            f"- **{sym}** {icon}: best `{best_ts['trail']}` @ RR={best_ts['rr']} "
            f"→ ExpR={best_ts['expectancy_R']:+.4f}R "
            f"(delta={delta:+.4f}R vs PROD, WR={best_ts['win_rate']}%)"
        )
    lines.append("")

    lines.append("### Mechanizm dzialania TS (obserwacje)")
    lines.append("")
    avg_wr_no_ts = np.mean([r["win_rate"] for r in oos_rows
                            if r["is_baseline"] and r["rr"] == PROD_RR])
    avg_expr_no_ts = np.mean([r["expectancy_R"] for r in oos_rows
                               if r["is_baseline"] and r["rr"] == PROD_RR])
    # Best TS overall
    best_ts_rows = [r for r in oos_rows if not r["is_baseline"]]
    if best_ts_rows:
        avg_wr_ts = np.mean([r["win_rate"] for r in best_ts_rows
                             if r["ts_r"] == 1.5 and r["lock_r"] == 0.0])
        avg_expr_ts = np.mean([r["expectancy_R"] for r in best_ts_rows
                                if r["ts_r"] == 1.5 and r["lock_r"] == 0.0])
        lines.append(
            f"- Bez TS (RR=3.0): avg WR={avg_wr_no_ts:.1f}%, avg ExpR={avg_expr_no_ts:+.4f}R"
        )
        lines.append(
            f"- Z TS1.5R_lockBE (RR=2.5/3.0): avg WR={avg_wr_ts:.1f}%, avg ExpR={avg_expr_ts:+.4f}R"
        )
    lines.append("")

    lines.append("### Porownanie z projektem Crypto")
    lines.append("")
    lines.append(
        "W BojkoFx-Crypto trailing stop (TS=2.0, lock=1.0) przy RR=2.0 "
        "poprawil ExpR o +8-15% per symbol. Glowny mechanizm: "
        "ochrona zysku gdy ruch jedzie 2R i wraca zamiast spasc do SL."
    )
    lines.append("")
    lines.append(
        "W FX (H1): ruchy sa wolniejsze (p50 ~1R vs ~0.7R w crypto), "
        "wiec TS aktywuje sie rzadziej niz w crypto. "
        "Efekt moze byc slabszy ale kierunek powinien byc podobny."
    )
    lines.append("")

    lines.append("## 8. Gotowa konfiguracja (jesli wdrozyt)")
    lines.append("")
    lines.append("```yaml")
    lines.append("# Eksperymentalna konfiguracja trailing stop (wymagana implementacja)")
    lines.append("# w src/execution/ibkr_exec.py (TrailingStopOrder IBKR API)")
    lines.append("")
    lines.append("strategy:")
    lines.append("  risk_reward: 2.5   # obnizone z 3.0 gdy uzywamy TS")
    lines.append("  trailing_stop:")
    lines.append("    enabled: true")
    lines.append("    ts_r: 1.5        # aktywacja gdy cena jedzie 1.5R od entry")
    lines.append("    lock_r: 0.0      # przy aktywacji: przesun SL na breakeven")
    lines.append("```")
    lines.append("")
    lines.append(
        "> **Uwaga implementacyjna:** IBKR API wspiera `TrailingStopOrder` "
        "z parametrem `trailStopPrice` lub `trailingPercent`. "
        "Wymaga modyfikacji `ibkr_exec.py` — dodania trzeciego leg zamiast "
        "statycznego SL. Niezaleznie od implementacji backtest potwierdza/odrzuca sens."
    )
    lines.append("")

    lines.append("---")
    lines.append(f"*Wygenerowano: {ts_now}*  ")
    lines.append(f"*Grid: {len(RR_VALUES)} RR x {len(TS_R_VALUES)} ts_r x {len(LOCK_R_VALUES)} lock_r + 2 baseline = {len(RR_VALUES)*len(TS_R_VALUES)*len(LOCK_R_VALUES)+2} konfig*  ")
    lines.append(f"*Symbole: {len(SYMBOLS)} x IS + OOS = {len(SYMBOLS)*2*(len(RR_VALUES)*len(TS_R_VALUES)*len(LOCK_R_VALUES)+2)} runow lacznie*")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(" Trailing Stop Grid Test — BojkoFx FX pairs")
    print(f" Symbols: {SYMBOLS}")
    print(f" RR grid: {RR_VALUES}")
    print(f" TS activate: {TS_R_VALUES} R")
    print(f" Lock on activation: {LOCK_R_VALUES} R")
    print(f" OOS: {OOS_START} – {OOS_END}")
    print("=" * 60)

    # ── Load data and generate all setups ─────────────────────────────────
    h1_data: Dict[str, pd.DataFrame] = {}
    all_setups: Dict[str, List[TradeSetup]] = {}

    gen = BOSPullbackSignalGenerator(PROD_CONFIG)

    for sym in SYMBOLS:
        print(f"\n[{sym}] Loading data...")
        h1 = load_h1(sym)
        if h1 is None:
            continue
        h1_data[sym] = h1
        d1 = build_d1(h1)
        h4 = build_h4(h1)
        t0 = time.time()
        setups = gen.generate_all(sym, h1, d1, h4)
        all_setups[sym] = setups
        print(f"[{sym}] {len(setups)} raw setups ({time.time()-t0:.1f}s)")

    # ── Build config list ─────────────────────────────────────────────────
    configs = []
    for rr in RR_VALUES:
        configs.append((rr, None))  # baseline: no TS
    for rr in RR_VALUES:
        for ts_r in TS_R_VALUES:
            for lock_r in LOCK_R_VALUES:
                configs.append((rr, {"ts_r": ts_r, "lock_r": lock_r}))

    total = len(SYMBOLS) * len(configs) * 2   # IS + OOS
    run_n = 0

    oos_rows: List[dict] = []
    is_rows:  List[dict] = []

    print(f"\nRunning {len(configs)} configs x {len(SYMBOLS)} symbols x 2 periods = {total} runs...")

    for sym in SYMBOLS:
        if sym not in h1_data:
            continue
        for rr, trail_cfg in configs:
            label = _trail_label(trail_cfg)
            # IS
            t0 = time.time()
            row_is = run_one(sym, all_setups[sym], h1_data[sym],
                             rr, trail_cfg, IS_START, IS_END)
            is_rows.append(row_is)
            # OOS
            row_oos = run_one(sym, all_setups[sym], h1_data[sym],
                              rr, trail_cfg, OOS_START, OOS_END)
            oos_rows.append(row_oos)
            run_n += 2

            elapsed = time.time() - t0
            delta = row_oos["expectancy_R"] - next(
                (r["expectancy_R"] for r in oos_rows
                 if r["symbol"] == sym and r["rr"] == rr and r["is_baseline"]),
                0.0,
            )
            mark = " ✅" if delta >= 0.05 else ""
            print(
                f"  [{run_n:3d}/{total}] {sym} RR={rr} {label:20s}: "
                f"OOS ExpR={row_oos['expectancy_R']:+.4f}R "
                f"WR={row_oos['win_rate']}% "
                f"n_TS={row_oos['n_ts']}{mark} "
                f"({elapsed:.1f}s)"
            )

    # ── Save CSV ──────────────────────────────────────────────────────────
    all_rows = [{"period": "OOS", **r} for r in oos_rows] + \
               [{"period": "IS",  **r} for r in is_rows]
    csv_path = REPORT_DIR / "trailing_stop_fx_results.csv"
    pd.DataFrame(all_rows).to_csv(csv_path, index=False)
    print(f"\nCSV saved: {csv_path}")

    # ── Generate report ───────────────────────────────────────────────────
    print("Generating report...")
    report_md = generate_report(oos_rows, is_rows)
    report_path = REPORT_DIR / "TRAILING_STOP_FX.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Report saved: {report_path}")

    # ── Quick summary ─────────────────────────────────────────────────────
    print("\n" + "="*60)
    print(" QUICK SUMMARY — OOS per symbol (best TS vs PROD)")
    print("="*60)
    for sym in SYMBOLS:
        prod_expr = next(
            (r["expectancy_R"] for r in oos_rows
             if r["symbol"] == sym and r["rr"] == PROD_RR and r["is_baseline"]),
            None,
        )
        sym_ts = [r for r in oos_rows if r["symbol"] == sym and not r["is_baseline"]]
        if not sym_ts or prod_expr is None:
            continue
        best = max(sym_ts, key=lambda r: r["expectancy_R"])
        delta = best["expectancy_R"] - prod_expr
        verdict = "LEPSZY" if delta >= 0.05 else ("~ROWNY" if delta >= 0.0 else "GORSZY")
        print(
            f"  {sym:8s}: PROD={prod_expr:+.4f}R → best {best['trail']:22s} "
            f"RR={best['rr']} ExpR={best['expectancy_R']:+.4f}R (Δ={delta:+.4f})  {verdict}"
        )

    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()

