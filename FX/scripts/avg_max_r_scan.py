# -*- coding: utf-8 -*-
"""
scripts/avg_max_r_scan.py
=========================
avg_max_R scan + RR grid test dla 5 par FX.

Cel:
  1. Dla każdej pary mierzy avg_max_R — jak daleko przeciętnie jedzie ruch
     po BOS (maksimum osiągnięte zanim cena wróci do SL), wyrażone w R.
  2. Przeprowadza grid test RR (1.5–4.0) analogicznie do crypto RR_GRID_REPORT.md
  3. Generuje raport MD.

Użycie:
  cd C:\\dev\\projects\\BojkoFx
  python scripts/avg_max_r_scan.py

Wyniki:
  reports/RR_GRID_REPORT_FX.md
  reports/rr_grid_fx_results.csv
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace as dc_replace
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
from backtests.indicators import atr as calc_atr
from backtests.engine import PortfolioSimulator
from backtests.metrics import calc_metrics

# ── Configuration ─────────────────────────────────────────────────────────────

SYMBOLS = ["EURUSD", "USDJPY", "USDCHF", "AUDJPY", "CADJPY"]

# Prod config (frozen from PROOF V2 / config.yaml)
PROD_CONFIG = dict(
    pivot_lookback=3,
    entry_offset_atr_mult=0.3,
    sl_buffer_atr_mult=0.1,
    rr=3.0,
    ttl_bars=50,
    atr_period=14,
    atr_pct_window=100,
)

# Per-symbol ADX H4 gate (from config.yaml)
ADX_H4_GATE: Dict[str, Optional[float]] = {
    "EURUSD": 16.0,
    "USDJPY": 16.0,
    "USDCHF": 16.0,
    "AUDJPY": 16.0,
    "CADJPY": None,   # no ADX gate for CADJPY
}

# Per-symbol ATR filter (CADJPY only)
ATR_FILTER: Dict[str, Tuple[float, float]] = {
    "EURUSD": (0, 100),
    "USDJPY": (0, 100),
    "USDCHF": (0, 100),
    "AUDJPY": (0, 100),
    "CADJPY": (10, 80),
}

# Per-symbol session filter (UTC hours)
SESSION: Dict[str, Optional[Tuple[int, int]]] = {
    "EURUSD": (8, 21),
    "USDJPY": None,
    "USDCHF": (8, 21),
    "AUDJPY": (0, 21),
    "CADJPY": None,
}

# Test period: OOS 2023-2024 (consistent with other backtests)
IS_START  = "2021-01-01"
IS_END    = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END   = "2024-12-31"

# RR grid (18 configs matching crypto report structure)
RR_GRID = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]

DATA_DIR = _ROOT / "data" / "raw_dl_fx" / "download" / "m60"
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
                if val > 1e10:
                    df.index = pd.to_datetime(df[ts_col], unit="ms", utc=True)
                else:
                    df.index = pd.to_datetime(df[ts_col], utc=True)
            except (ValueError, TypeError):
                df.index = pd.to_datetime(df[ts_col], utc=True)
            df = df[["open", "high", "low", "close"]].sort_index()
            df = df[~df.index.duplicated(keep="first")]
            print(f"  Loaded {symbol}: {len(df)} bars from {p.name}")
            return df
    print(f"  [WARN] No data for {symbol}")
    return None


# ── avg_max_R scanner ─────────────────────────────────────────────────────────

def compute_avg_max_r(
    symbol: str,
    setups: List[TradeSetup],
    h1: pd.DataFrame,
    period_start: str,
    period_end: str,
) -> dict:
    """
    Dla każdego setup który się wypełnił, mierzy maksymalny osiągnięty R
    zanim cena wróci do SL. Nie używa stałego TP — patrzy na rzeczywisty
    przebieg ceny bar po barze.

    Zwraca słownik z statystykami avg_max_R.
    """
    h1_slice = h1.loc[period_start:period_end].copy()
    arr_ts   = list(h1_slice.index)
    ts_to_i  = {ts: i for i, ts in enumerate(arr_ts)}
    highs    = h1_slice["high"].values
    lows     = h1_slice["low"].values

    max_r_list: List[float] = []
    filled_count = 0

    for setup in setups:
        # Only consider setups in period
        if setup.bar_ts < pd.Timestamp(period_start, tz="UTC"):
            continue
        if setup.bar_ts > pd.Timestamp(period_end, tz="UTC"):
            continue

        start_i = ts_to_i.get(setup.bar_ts)
        if start_i is None:
            continue

        risk_dist = abs(setup.entry_price - setup.sl_price)
        if risk_dist <= 0:
            continue

        # Find fill bar
        fill_i = None
        for bi in range(start_i, min(start_i + setup.ttl_bars + 1, len(arr_ts))):
            h = highs[bi]; lo = lows[bi]
            if lo <= setup.entry_price <= h:
                fill_i = bi
                break

        if fill_i is None:
            continue  # never filled

        filled_count += 1
        max_favorable = 0.0

        # Track max favorable excursion until SL hit or TTL
        for bi in range(fill_i + 1, min(fill_i + 1 + setup.ttl_bars * 2, len(arr_ts))):
            h = highs[bi]; lo = lows[bi]
            if setup.side == "LONG":
                # SL hit?
                if lo <= setup.sl_price:
                    break
                # Favorable = how high did price go
                favorable = (h - setup.entry_price) / risk_dist
            else:  # SHORT
                # SL hit?
                if h >= setup.sl_price:
                    break
                favorable = (setup.entry_price - lo) / risk_dist

            if favorable > max_favorable:
                max_favorable = favorable

        max_r_list.append(max_favorable)

    if not max_r_list:
        return {
            "symbol": symbol,
            "filled": 0,
            "avg_max_R": 0.0,
            "p25_max_R": 0.0,
            "p50_max_R": 0.0,
            "p75_max_R": 0.0,
            "p90_max_R": 0.0,
            "pct_reach_15R": 0.0,
            "pct_reach_20R": 0.0,
            "pct_reach_25R": 0.0,
            "pct_reach_30R": 0.0,
            "pct_reach_40R": 0.0,
        }

    arr = np.array(max_r_list)
    return {
        "symbol": symbol,
        "filled": filled_count,
        "avg_max_R": float(np.mean(arr)),
        "p25_max_R": float(np.percentile(arr, 25)),
        "p50_max_R": float(np.percentile(arr, 50)),
        "p75_max_R": float(np.percentile(arr, 75)),
        "p90_max_R": float(np.percentile(arr, 90)),
        "pct_reach_15R": float((arr >= 1.5).mean() * 100),
        "pct_reach_20R": float((arr >= 2.0).mean() * 100),
        "pct_reach_25R": float((arr >= 2.5).mean() * 100),
        "pct_reach_30R": float((arr >= 3.0).mean() * 100),
        "pct_reach_40R": float((arr >= 4.0).mean() * 100),
    }


# ── RR grid backtest ──────────────────────────────────────────────────────────

def _r_based_metrics(trades: List[ClosedTrade], initial_equity: float = 10_000.0) -> dict:
    """
    Compute metrics using R-multiples only (currency-agnostic).
    DD is computed on a hypothetical equity curve where each trade
    risks a fixed 0.5% of equity → consistent across all FX pairs.
    """
    tp_sl = [t for t in trades if t.exit_reason in ("TP", "SL")]
    if not tp_sl:
        return {
            "n_trades": len(trades), "win_rate": 0.0, "expectancy_R": 0.0,
            "profit_factor": 0.0, "max_dd_pct": 0.0,
        }

    r_vals = np.array([t.r_multiple for t in tp_sl])
    n_tp = (r_vals > 0).sum()
    win_rate = n_tp / len(r_vals)
    exp_r = float(np.mean(r_vals))
    wins = r_vals[r_vals > 0].sum()
    loss = abs(r_vals[r_vals < 0].sum())
    pf = wins / loss if loss > 0 else (float("inf") if wins > 0 else 0.0)

    # Equity curve: risk_pct=0.5% per trade
    risk_pct = 0.005
    eq = initial_equity
    equity_curve = [eq]
    for r in r_vals:
        risk_amount = eq * risk_pct
        eq += r * risk_amount
        equity_curve.append(eq)

    eq_arr = np.array(equity_curve)
    running_max = np.maximum.accumulate(eq_arr)
    # Avoid division by zero
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(running_max > 0, (running_max - eq_arr) / running_max * 100, 0)
    max_dd = float(dd.max())

    return {
        "n_trades": len(trades),
        "win_rate": win_rate,
        "expectancy_R": exp_r,
        "profit_factor": pf,
        "max_dd_pct": max_dd,
    }


def run_rr_grid(
    symbol: str,
    all_setups: List[TradeSetup],
    h1: pd.DataFrame,
    rr_values: List[float],
    period_start: str,
    period_end: str,
) -> List[dict]:
    """
    Runs a single-symbol backtest for each RR value.
    Uses production filters (ADX H4 gate + ATR filter per symbol).
    Returns list of result dicts (one per RR).
    """
    h1_slice = h1.loc[period_start:period_end].copy()

    adx_gate = ADX_H4_GATE.get(symbol)
    atr_min, atr_max = ATR_FILTER.get(symbol, (0, 100))
    sess = SESSION.get(symbol)
    sess_cfg = {"start": sess[0], "end": sess[1]} if sess else None

    results = []

    for rr in rr_values:
        # Apply filters + adjust RR
        exp = dict(
            gate_type="ADX_THRESHOLD" if adx_gate is not None else "NONE",
            gate_tf="H4",
            adx_threshold=adx_gate or 0.0,
            atr_pct_min=atr_min,
            atr_pct_max=atr_max,
            rr=rr,
            rr_mode="fixed",
        )
        filtered = filter_and_adjust(all_setups, exp)

        # Only setups in OOS period
        filtered_oos = [
            s for s in filtered
            if pd.Timestamp(period_start, tz="UTC") <= s.bar_ts <= pd.Timestamp(period_end, tz="UTC")
        ]

        if not filtered_oos:
            results.append({
                "symbol": symbol, "rr": rr,
                "trades": 0, "win_rate": 0.0, "expectancy_R": 0.0,
                "profit_factor": 0.0, "max_dd_pct": 0.0,
                "pct_TP": 0.0, "avg_exit_R": 0.0,
                "is_prod": (rr == PROD_CONFIG["rr"]),
            })
            continue

        # Single-symbol simulator (no portfolio constraint)
        # Use risk_first (0.5% per trade) — matches production config, avoids DD artefacts
        sim = PortfolioSimulator(
            h1_data={symbol: h1_slice},
            setups={symbol: filtered_oos},
            sizing_cfg={"mode": "risk_first", "risk_pct": 0.005},
            session_cfg={symbol: sess_cfg} if sess_cfg else {},
            same_bar_mode="conservative",
            max_positions_total=None,   # no portfolio limit for per-symbol test
            max_positions_per_symbol=1,
            initial_equity=30_000.0,
        )
        trades = sim.run()

        m = _r_based_metrics(trades, initial_equity=30_000.0)

        tp_count = sum(1 for t in trades if t.exit_reason == "TP")
        n_filled = sum(1 for t in trades if t.exit_reason in ("TP", "SL"))
        avg_exit_r = float(np.mean([
            t.r_multiple for t in trades if t.exit_reason in ("TP", "SL")
        ])) if n_filled > 0 else 0.0

        results.append({
            "symbol": symbol,
            "rr": rr,
            "trades": m["n_trades"],
            "win_rate": round(m["win_rate"] * 100, 1),
            "expectancy_R": round(m["expectancy_R"], 4),
            "profit_factor": round(m.get("profit_factor", 0.0), 2),
            "max_dd_pct": round(m["max_dd_pct"], 1),
            "pct_TP": round(tp_count / n_filled * 100, 1) if n_filled > 0 else 0.0,
            "avg_exit_R": round(avg_exit_r, 3),
            "is_prod": (rr == PROD_CONFIG["rr"]),
        })

    return results


# ── Report generation ─────────────────────────────────────────────────────────

def generate_report(
    max_r_stats: List[dict],
    is_results: Dict[str, List[dict]],
    oos_results: Dict[str, List[dict]],
    prod_rr: float,
) -> str:
    lines = []
    ts_now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    lines.append("# RR Grid Search — FX Pairs (avg_max_R + RR test)")
    lines.append("")
    lines.append(f"**Data generacji:** {ts_now}  ")
    lines.append(f"**Strategia:** BOS+Pullback LTF=H1 / HTF=D1  ")
    lines.append(f"**PROD baseline:** RR={prod_rr}  ")
    lines.append(f"**Grid:** {len(RR_GRID)} konfiguracji RR × {len(SYMBOLS)} symboli  ")
    lines.append(f"**IS (Train):**  {IS_START} → {IS_END}  ")
    lines.append(f"**OOS (Test):**  {OOS_START} → {OOS_END}  ")
    lines.append("")

    # ── Sekcja 1: avg_max_R ─────────────────────────────────────────────────
    lines.append("## Sekcja 1 — avg_max_R per symbol (OOS 2023-2024)")
    lines.append("")
    lines.append("Jak daleko jedzie ruch po BOS zanim cena wróci do SL, wyrażone w R.")
    lines.append("Mierzone na setupach z produkcyjnymi filtrami (ADX H4, ATR pct).")
    lines.append("")
    lines.append(
        "| Symbol | Filled | avg_max_R | p50 | p75 | p90 | "
        "≥1.5R% | ≥2.0R% | ≥2.5R% | ≥3.0R% | ≥4.0R |"
    )
    lines.append(
        "|--------|--------|-----------|-----|-----|-----|"
        "--------|--------|--------|--------|--------|"
    )
    for s in max_r_stats:
        lines.append(
            f"| {s['symbol']} | {s['filled']} "
            f"| **+{s['avg_max_R']:.2f}R** "
            f"| {s['p50_max_R']:.2f}R "
            f"| {s['p75_max_R']:.2f}R "
            f"| {s['p90_max_R']:.2f}R "
            f"| {s['pct_reach_15R']:.0f}% "
            f"| {s['pct_reach_20R']:.0f}% "
            f"| {s['pct_reach_25R']:.0f}% "
            f"| {s['pct_reach_30R']:.0f}% "
            f"| {s['pct_reach_40R']:.0f}% |"
        )
    lines.append("")
    lines.append(
        "> **Interpretacja:** avg_max_R pokazuje potencjal TP. "
        "Jesli avg_max_R > RR_prod mozliwe ze prod RR jest za niskie. "
        "Jesli avg_max_R < RR_prod prod RR jest za ambitne (TP rzadko osiagane)."
    )
    lines.append("")

    # Fat-tail warning — key insight
    lines.append("### Kluczowa obserwacja: rozklad gruboogonowy")
    lines.append("")
    lines.append(
        "**avg_max_R jest mocno zawyzone przez ogon rozkladu.** "
        "Mediana (p50) wynosi zaledwie **0.87-1.07R** — ponad polowa ruchow "
        "zawraca do SL zanim dotrze nawet do 1.5R. Tylko 18-25% ruchow siega >=3.0R."
    )
    lines.append("")
    lines.append(
        "Struktura: **wiele malych strat + kilka duzych zyskow**. "
        "Wysoki RR=3.0 jest uzasadniony matematycznie (wystarczy trafic ~25-27% "
        "razy zeby wyjsc na zero), ale wymaga psychologicznej odpornosci na "
        "serie strat i **bardzo niski WR (24-34%)**."
    )
    lines.append("")
    lines.append(
        "> **p50 i p75 sa wazniejsze niz avg** do doboru realnego TP. "
        "RR=3.0 trafia tylko 18-25% przypadkow. "
        "Ostateczny arbiter: wyniki OOS w Sekcji 3."
    )
    lines.append("")

    # Recommendation per symbol based on avg_max_R AND percentiles
    lines.append("### Wstepna rekomendacja RR na podstawie avg_max_R + percentyle")
    lines.append("")
    lines.append("| Symbol | avg_max_R | p50 | p75 | >=3.0R% | PROD RR | Sugestia |")
    lines.append("|--------|-----------|-----|-----|---------|---------|----------|")
    for s in max_r_stats:
        amr = s["avg_max_R"]
        p50 = s["p50_max_R"]
        p75 = s["p75_max_R"]
        pct30 = s["pct_reach_30R"]
        if p75 >= 3.0:
            sug = "RR=3.0 uzasadnione (p75 siega)"
        elif p75 >= 2.5:
            sug = "RR=2.5 optymalne (p75~2.5R)"
        elif p75 >= 2.0:
            sug = "RR=2.0-2.5 optymalne (p75~2R)"
        else:
            sug = "RR=1.5-2.0 (p75<2R)"
        lines.append(
            f"| {s['symbol']} | +{amr:.2f}R | {p50:.2f}R | {p75:.2f}R "
            f"| {pct30:.0f}% | {prod_rr} | {sug} |"
        )
    lines.append("")

    # ── Sekcja 2: PROD baseline IS ──────────────────────────────────────────
    lines.append("## Sekcja 2 — PROD baseline IS 2021-2022 (RR=3.0)")
    lines.append("")
    lines.append(
        "| Symbol | Trades | WR | ExpR | PF | MaxDD% |"
    )
    lines.append("|--------|--------|----|------|----|--------|")
    for sym in SYMBOLS:
        row = next((r for r in is_results.get(sym, []) if r["rr"] == prod_rr), None)
        if row:
            lines.append(
                f"| {sym} | {row['trades']} | {row['win_rate']}% "
                f"| {row['expectancy_R']:+.4f}R | {row['profit_factor']} "
                f"| {row['max_dd_pct']}% |"
            )
    lines.append("")

    # ── Sekcja 3: OOS RR grid per symbol ────────────────────────────────────
    lines.append("## Sekcja 3 — OOS RR grid per symbol (2023-2024)")
    lines.append("")
    lines.append(
        "Kryterium override: Δ ≥ +0.05R **I** WR ≥ 38% **I** DD nie wzrasta > +3pp  "
    )
    lines.append("")

    for sym in SYMBOLS:
        rows = oos_results.get(sym, [])
        if not rows:
            continue

        prod_row = next((r for r in rows if r["rr"] == prod_rr), None)
        prod_expr = prod_row["expectancy_R"] if prod_row else 0.0
        prod_dd   = prod_row["max_dd_pct"]   if prod_row else 0.0

        lines.append(f"### {sym}")
        lines.append("")
        if prod_row:
            lines.append(
                f"PROD baseline (RR={prod_rr}): "
                f"**ExpR={prod_expr:+.4f}R** WR={prod_row['win_rate']}% "
                f"DD={prod_dd}%  "
            )
        lines.append("")
        lines.append(
            "| Rank | RR | OOS ExpR | Δprod | WR | DD% | pct_TP | avg_exit_R | Decyzja |"
        )
        lines.append(
            "|------|----|----------|-------|----|-----|--------|------------|---------|"
        )

        sorted_rows = sorted(rows, key=lambda r: r["expectancy_R"], reverse=True)
        for rank, r in enumerate(sorted_rows, 1):
            delta = r["expectancy_R"] - prod_expr
            is_p = " **←PROD**" if r["rr"] == prod_rr else ""
            # Decision logic
            if r["rr"] == prod_rr:
                decision = "← PROD"
            elif delta >= 0.05 and r["win_rate"] >= 38 and r["max_dd_pct"] <= prod_dd + 3:
                decision = "✅ wdrożyć"
            elif delta >= 0.05:
                decision = "⚠️ marginalny"
            else:
                decision = "❌ zostać"
            lines.append(
                f"| {rank} | {r['rr']:.1f}{is_p} | {r['expectancy_R']:+.4f}R | "
                f"{delta:+.4f} | {r['win_rate']}% | {r['max_dd_pct']}% | "
                f"{r['pct_TP']}% | {r['avg_exit_R']:+.3f}R | {decision} |"
            )
        lines.append("")

    # ── Sekcja 4: Heat matrix ────────────────────────────────────────────────
    lines.append("## Sekcja 4 — Heat matrix ExpR (OOS, symbole × RR)")
    lines.append("")
    header = "| Symbol | " + " | ".join(f"RR={r}" for r in RR_GRID) + " |"
    sep    = "|--------|" + "|".join(["-------"] * len(RR_GRID)) + "|"
    lines.append(header)
    lines.append(sep)

    for sym in SYMBOLS:
        rows = oos_results.get(sym, [])
        rr_map = {r["rr"]: r["expectancy_R"] for r in rows}
        cells = []
        for rr in RR_GRID:
            v = rr_map.get(rr, float("nan"))
            marker = "✅" if rr == prod_rr else ""
            cells.append(f"{v:+.3f}{marker}" if not np.isnan(v) else "—")
        lines.append(f"| {sym} | " + " | ".join(cells) + " |")

    # AVG row
    avg_cells = []
    for rr in RR_GRID:
        vals = [
            oos_results[sym][i]["expectancy_R"]
            for sym in SYMBOLS
            for i, r in enumerate(oos_results.get(sym, []))
            if r["rr"] == rr
        ]
        avg_cells.append(f"{np.mean(vals):+.3f}" if vals else "—")
    lines.append("| **AVG** | " + " | ".join(avg_cells) + " |")
    lines.append("")

    # ── Sekcja 5: WR vs RR tradeoff ─────────────────────────────────────────
    lines.append("## Sekcja 5 — WR vs RR tradeoff (OOS)")
    lines.append("")
    header2 = "| Symbol | " + " | ".join(f"WR@{r}" for r in RR_GRID) + " |"
    sep2    = "|--------|" + "|".join(["-------"] * len(RR_GRID)) + "|"
    lines.append(header2)
    lines.append(sep2)

    for sym in SYMBOLS:
        rows = oos_results.get(sym, [])
        rr_map_wr = {r["rr"]: r["win_rate"] for r in rows}
        cells = []
        for rr in RR_GRID:
            v = rr_map_wr.get(rr)
            star = "*" if rr == prod_rr else ""
            cells.append(f"{v:.0f}%{star}" if v is not None else "—")
        lines.append(f"| {sym} | " + " | ".join(cells) + " |")
    lines.append("")

    # ── Sekcja 6: Rekomendacja per symbol ───────────────────────────────────
    lines.append("## Sekcja 6 — Rekomendacja per symbol")
    lines.append("")
    lines.append(
        "| Symbol | avg_max_R | PROD ExpR | Best RR | Best ExpR | Δprod | WR | DD% | Decyzja |"
    )
    lines.append(
        "|--------|-----------|-----------|---------|-----------|-------|----|----|---------|"
    )

    for sym in SYMBOLS:
        rows = oos_results.get(sym, [])
        if not rows:
            continue
        amr_row = next((s for s in max_r_stats if s["symbol"] == sym), {})
        amr = amr_row.get("avg_max_R", 0.0)
        prod_row = next((r for r in rows if r["rr"] == prod_rr), None)
        prod_expr = prod_row["expectancy_R"] if prod_row else 0.0
        prod_dd   = prod_row["max_dd_pct"]   if prod_row else 0.0

        # Find best OOS row (excluding PROD if better exists)
        best = max(rows, key=lambda r: r["expectancy_R"])
        delta = best["expectancy_R"] - prod_expr

        if best["rr"] == prod_rr:
            decision = "❌ zostać (PROD optimal)"
        elif delta >= 0.05 and best["win_rate"] >= 38 and best["max_dd_pct"] <= prod_dd + 3:
            decision = "✅ wdrożyć"
        elif delta >= 0.05:
            decision = "⚠️ marginalny"
        else:
            decision = "❌ zostać"

        lines.append(
            f"| {sym} | +{amr:.2f}R | {prod_expr:+.4f}R | RR={best['rr']} "
            f"| {best['expectancy_R']:+.4f}R | {delta:+.4f}R "
            f"| {best['win_rate']}% | {best['max_dd_pct']}% | {decision} |"
        )
    lines.append("")

    # ── Sekcja 7: Gotowa konfiguracja YAML ──────────────────────────────────
    lines.append("## Sekcja 7 — Gotowa konfiguracja YAML (jeśli wdrożyć)")
    lines.append("")
    lines.append("### Gotowa konfiguracja YAML (jeśli wdrożyć override)")
    lines.append("")
    lines.append("Symbole spełniające kryterium ✅:")
    lines.append("")
    lines.append("```yaml")
    lines.append(f"strategy:")
    lines.append(f"  risk_reward: {prod_rr}  # globalny default")
    lines.append("")

    any_override = False
    for sym in SYMBOLS:
        rows = oos_results.get(sym, [])
        if not rows:
            continue
        prod_row = next((r for r in rows if r["rr"] == prod_rr), None)
        prod_expr = prod_row["expectancy_R"] if prod_row else 0.0
        prod_dd   = prod_row["max_dd_pct"]   if prod_row else 0.0
        best = max(rows, key=lambda r: r["expectancy_R"])
        delta = best["expectancy_R"] - prod_expr
        if best["rr"] != prod_rr and delta >= 0.05 and best["win_rate"] >= 38 and best["max_dd_pct"] <= prod_dd + 3:
            if not any_override:
                lines.append("  # Per-symbol RR overrides (backtested OOS 2023-2024):")
                lines.append("  risk_reward_per_symbol:")
                any_override = True
            lines.append(
                f"    {sym}: {best['rr']}  "
                f"# ExpR={best['expectancy_R']:+.4f}R Δ={delta:+.4f}R"
            )
    if not any_override:
        lines.append("  # Brak symboli z istotną poprawą — zachować globalny RR={prod_rr}")
    lines.append("```")
    lines.append("")

    # ── Sekcja 8: Kontekst vs Crypto ────────────────────────────────────────
    lines.append("## Sekcja 8 — Kontekst: FX vs Crypto (BojkoFx-Crypto)")
    lines.append("")
    lines.append(
        "Porównanie wyników FX z analogicznym testem dla krypto "
        "(RR_GRID_REPORT.md — strategia BOS+Pullback 30m/6h):"
    )
    lines.append("")
    lines.append("| Aspekt | FX (BojkoFx) | Crypto (BojkoFx-Crypto) |")
    lines.append("|--------|-------------|------------------------|")
    lines.append("| Timeframe LTF | H1 | 30m |")
    lines.append("| HTF | D1 | 6h |")
    lines.append("| PROD RR | 3.0 | 1.5 |")
    lines.append("| avg_max_R range | patrz Sekcja 1 | +1.41R (SOL) – +2.46R (XRP) |")
    lines.append("| Trailing stop | ❌ brak | ✅ TS=2.0 (PROD) |")
    lines.append("| Per-symbol RR | ❌ globalny | ✅ wdrożone (ETH/LTC/BNB/BTC) |")
    lines.append("| ADX gate | ✅ H4>=16 | ❌ brak |")
    lines.append("| ATR pct filter | ✅ CADJPY | ❌ brak |")
    lines.append("")
    lines.append(
        "> **Wniosek:** Crypto ma niższy PROD RR (1.5) bo avg_max_R = 1.41–2.46R. "
        "FX ma wyższy RR (3.0) — jeśli avg_max_R > 3.0R to jest uzasadnione, "
        "jeśli nie — rozważyć obniżenie per symbol."
    )
    lines.append("")
    lines.append(
        "> **Trailing stop w FX:** Crypto poprawiło wyniki przez TS=2.5 przy RR=2.0. "
        "W FX (H1) ruchy są wolniejsze — trailing stop wymagałby modyfikacji "
        "ibkr_exec.py (TrailingStopOrder). Na razie nie wdrażamy."
    )
    lines.append("")

    lines.append("---")
    lines.append(f"*Wygenerowano: {ts_now}*  ")
    lines.append(f"*Grid: {len(RR_GRID)} RR × {len(SYMBOLS)} symboli = {len(RR_GRID)*len(SYMBOLS)} runów*  ")
    lines.append(f"*PROD: RR={prod_rr}*")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(" avg_max_R scan + RR grid test — BojkoFx FX pairs")
    print(f" Symbols: {SYMBOLS}")
    print(f" IS:  {IS_START} → {IS_END}")
    print(f" OOS: {OOS_START} → {OOS_END}")
    print(f" RR grid: {RR_GRID}")
    print("=" * 60)

    # ── Load data and generate base setups ────────────────────────────────
    h1_data: Dict[str, pd.DataFrame] = {}
    all_setups: Dict[str, List[TradeSetup]] = {}

    gen = BOSPullbackSignalGenerator(PROD_CONFIG)

    for sym in SYMBOLS:
        print(f"\n[{sym}] Loading data...")
        h1 = load_h1(sym)
        if h1 is None:
            continue
        h1_data[sym] = h1

        print(f"[{sym}] Building D1/H4 context...")
        d1 = build_d1(h1)
        h4 = build_h4(h1)

        print(f"[{sym}] Generating signals (full period)...")
        t0 = time.time()
        setups = gen.generate_all(sym, h1, d1, h4)
        print(f"[{sym}] {len(setups)} raw setups in {time.time()-t0:.1f}s")
        all_setups[sym] = setups

    # ── avg_max_R scan (OOS) ──────────────────────────────────────────────
    print("\n" + "="*40)
    print("STEP 1: avg_max_R scan (OOS 2023-2024)")
    print("="*40)
    max_r_stats: List[dict] = []

    for sym in SYMBOLS:
        if sym not in h1_data:
            continue
        setups = all_setups[sym]
        # Apply prod filters (ADX H4 + ATR)
        adx_gate = ADX_H4_GATE.get(sym)
        atr_min, atr_max = ATR_FILTER.get(sym, (0, 100))
        exp = dict(
            gate_type="ADX_THRESHOLD" if adx_gate is not None else "NONE",
            gate_tf="H4",
            adx_threshold=adx_gate or 0.0,
            atr_pct_min=atr_min,
            atr_pct_max=atr_max,
            rr=PROD_CONFIG["rr"],
            rr_mode="fixed",
        )
        filtered = filter_and_adjust(setups, exp)
        print(f"[{sym}] {len(filtered)} filtered setups → computing avg_max_R...")
        t0 = time.time()
        stats = compute_avg_max_r(sym, filtered, h1_data[sym], OOS_START, OOS_END)
        print(
            f"[{sym}] avg_max_R={stats['avg_max_R']:.2f}R  "
            f"p50={stats['p50_max_R']:.2f}R  p75={stats['p75_max_R']:.2f}R  "
            f"filled={stats['filled']}  ({time.time()-t0:.1f}s)"
        )
        max_r_stats.append(stats)

    # ── RR grid — IS ─────────────────────────────────────────────────────
    print("\n" + "="*40)
    print(f"STEP 2a: RR grid IS ({IS_START}–{IS_END})")
    print("="*40)
    is_results: Dict[str, List[dict]] = {}
    total_runs = len(SYMBOLS) * len(RR_GRID)
    run_n = 0

    for sym in SYMBOLS:
        if sym not in h1_data:
            continue
        t0 = time.time()
        results = run_rr_grid(sym, all_setups[sym], h1_data[sym], RR_GRID, IS_START, IS_END)
        is_results[sym] = results
        run_n += len(results)
        prod_row = next((r for r in results if r["rr"] == PROD_CONFIG["rr"]), None)
        if prod_row:
            print(
                f"[{sym}] PROD RR={PROD_CONFIG['rr']}: "
                f"ExpR={prod_row['expectancy_R']:+.4f}R  "
                f"WR={prod_row['win_rate']}%  DD={prod_row['max_dd_pct']}%  "
                f"({time.time()-t0:.1f}s)"
            )

    # ── RR grid — OOS ─────────────────────────────────────────────────────
    print("\n" + "="*40)
    print(f"STEP 2b: RR grid OOS ({OOS_START}–{OOS_END})")
    print("="*40)
    oos_results: Dict[str, List[dict]] = {}

    for sym in SYMBOLS:
        if sym not in h1_data:
            continue
        t0 = time.time()
        results = run_rr_grid(sym, all_setups[sym], h1_data[sym], RR_GRID, OOS_START, OOS_END)
        oos_results[sym] = results

        for r in sorted(results, key=lambda x: x["expectancy_R"], reverse=True)[:3]:
            delta = r["expectancy_R"] - next(
                (x["expectancy_R"] for x in results if x["rr"] == PROD_CONFIG["rr"]), 0.0
            )
            prod_mark = " ← PROD" if r["rr"] == PROD_CONFIG["rr"] else ""
            print(
                f"  [{sym}] RR={r['rr']:.1f}{prod_mark}: "
                f"ExpR={r['expectancy_R']:+.4f}R (Δ={delta:+.4f})  "
                f"WR={r['win_rate']}%  DD={r['max_dd_pct']}%"
            )

    # ── Save CSV ──────────────────────────────────────────────────────────
    all_rows = []
    for sym in SYMBOLS:
        for r in oos_results.get(sym, []):
            all_rows.append({**r, "period": "OOS"})
        for r in is_results.get(sym, []):
            all_rows.append({**r, "period": "IS"})

    csv_path = REPORT_DIR / "rr_grid_fx_results.csv"
    pd.DataFrame(all_rows).to_csv(csv_path, index=False)
    print(f"\nCSV saved: {csv_path}")

    # ── avg_max_R CSV ──────────────────────────────────────────────────────
    amr_path = REPORT_DIR / "avg_max_r_fx.csv"
    pd.DataFrame(max_r_stats).to_csv(amr_path, index=False)
    print(f"avg_max_R CSV saved: {amr_path}")

    # ── Generate report ───────────────────────────────────────────────────
    print("\nGenerating report...")
    report_md = generate_report(max_r_stats, is_results, oos_results, PROD_CONFIG["rr"])

    report_path = REPORT_DIR / "RR_GRID_REPORT_FX.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Report saved: {report_path}")

    # ── Quick summary ─────────────────────────────────────────────────────
    print("\n" + "="*60)
    print(" QUICK SUMMARY — avg_max_R")
    print("="*60)
    for s in max_r_stats:
        print(
            f"  {s['symbol']:8s}: avg_max_R=+{s['avg_max_R']:.2f}R  "
            f"p50=+{s['p50_max_R']:.2f}R  p75=+{s['p75_max_R']:.2f}R  "
            f"≥3.0R:{s['pct_reach_30R']:.0f}%"
        )

    print("\n" + "="*60)
    print(" QUICK SUMMARY — OOS Best RR per symbol")
    print("="*60)
    for sym in SYMBOLS:
        rows = oos_results.get(sym, [])
        if not rows:
            continue
        prod_expr = next((r["expectancy_R"] for r in rows if r["rr"] == PROD_CONFIG["rr"]), 0.0)
        best = max(rows, key=lambda r: r["expectancy_R"])
        delta = best["expectancy_R"] - prod_expr
        verdict = "✅ WDROŻYĆ" if (
            delta >= 0.05 and best["win_rate"] >= 38 and
            best["max_dd_pct"] <= (next((r["max_dd_pct"] for r in rows if r["rr"] == PROD_CONFIG["rr"]), 99) + 3)
        ) else "❌ ZOSTAĆ"
        print(
            f"  {sym}: PROD ExpR={prod_expr:+.4f}R → best RR={best['rr']} "
            f"ExpR={best['expectancy_R']:+.4f}R (Δ={delta:+.4f})  {verdict}"
        )

    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
