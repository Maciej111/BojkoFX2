# -*- coding: utf-8 -*-
"""
scripts/trailing_stop_val2025.py
================================
Walidacja trailing stop na danych 2025 (OOS hold-out).
Identyczna logika jak trailing_stop_scan.py, ale:
  IS  = 2023-01-01 – 2024-12-31  (poprzedni OOS jako nowy "train")
  OOS = 2025-01-01 – 2025-12-31  (fresh hold-out)

Cel: potwierdzic ze wyniki TS z OOS 2023-2024 sa stabilne w 2025.
Skupiamy sie na 5 parach + kandydatach: USDJPY i CADJPY.

Wyniki:
  reports/TRAILING_STOP_VAL2025.md
  reports/trailing_stop_val2025_results.csv
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

# ── Okresy ─────────────────────────────────────────────────────────────────────
# "IS" = poprzedni OOS (2023-2024) — referencja
# "OOS" = nowy hold-out 2025
IS_START  = "2023-01-01"
IS_END    = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END   = "2025-12-31"

# Kandydaci z OOS 2023-2024: te konfiguracje testujemy na 2025
# Format: (rr, trail_cfg_or_None, label)
CANDIDATE_CONFIGS = [
    # Baseline PROD
    (3.0, None,                               "PROD_baseline"),
    # USDJPY winner
    (2.5, {"ts_r": 2.0, "lock_r": 0.5},      "USDJPY_winner"),
    # CADJPY winner
    (3.0, {"ts_r": 2.0, "lock_r": 0.5},      "CADJPY_winner"),
    # Silny runner-up CADJPY
    (3.0, {"ts_r": 1.5, "lock_r": 0.5},      "TS1.5R_lock0.5R"),
    # USDCHF marginalny
    (3.0, {"ts_r": 1.5, "lock_r": 0.0},      "USDCHF_cand"),
    # EURUSD marginalny
    (3.0, {"ts_r": 1.5, "lock_r": 0.0},      "EURUSD_cand"),
    # AUDJPY — bez TS
    (3.0, None,                               "AUDJPY_nots"),
    # Full grid: RR=2.5 x ts_r=1.5 x lock0.5
    (2.5, {"ts_r": 1.5, "lock_r": 0.5},      "RR2.5_TS1.5_lock0.5"),
    # Full grid: RR=3.0 x ts_r=2.0 x lock0.0
    (3.0, {"ts_r": 2.0, "lock_r": 0.0},      "RR3.0_TS2.0_lock0.0"),
    # Full grid: RR=2.5 x ts_r=2.0 x lock0.0
    (2.5, {"ts_r": 2.0, "lock_r": 0.0},      "RR2.5_TS2.0_lock0.0"),
    # RR=2.5 x ts_r=2.5 x lock0.5
    (2.5, {"ts_r": 2.5, "lock_r": 0.5},      "RR2.5_TS2.5_lock0.5"),
]

# Deduplikuj: ta sama (rr, trail_cfg) moze pojawic sie wielokrotnie w kandydatach
# ale run_one jest deterministyczny wiec nie szkodzi
PROD_RR = 3.0

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
            n_2025 = len(df.loc["2025-01-01":])
            print(f"  {symbol}: {len(df)} total bars, {n_2025} bars in 2025")
            return df
    print(f"  [WARN] No data for {symbol}")
    return None


# ── Metrics ───────────────────────────────────────────────────────────────────

def r_metrics(trades: List[ClosedTrade], initial_equity: float = 30_000.0) -> dict:
    tp_sl_ts = [t for t in trades if t.exit_reason in ("TP", "SL", "TS")]
    if not tp_sl_ts:
        return {
            "n_trades": len(trades), "win_rate": 0.0, "expectancy_R": 0.0,
            "profit_factor": 0.0, "max_dd_pct": 0.0,
            "n_tp": 0, "n_sl": 0, "n_ts": 0, "n_ttl": 0,
        }

    r_vals = np.array([t.r_multiple for t in tp_sl_ts])
    n_tp  = sum(1 for t in tp_sl_ts if t.exit_reason == "TP")
    n_sl  = sum(1 for t in tp_sl_ts if t.exit_reason == "SL")
    n_ts  = sum(1 for t in tp_sl_ts if t.exit_reason == "TS")
    n_ttl = sum(1 for t in trades   if t.exit_reason == "TTL")

    wins = r_vals[r_vals > 0]
    loss = r_vals[r_vals < 0]
    win_rate = len(wins) / len(r_vals)
    exp_r    = float(np.mean(r_vals))
    pf_wins  = wins.sum()
    pf_loss  = abs(loss.sum())
    pf       = pf_wins / pf_loss if pf_loss > 0 else (float("inf") if pf_wins > 0 else 0.0)

    risk_pct = 0.005
    eq = initial_equity
    curve = [eq]
    for r in r_vals:
        eq += r * eq * risk_pct
        curve.append(eq)
    eq_arr = np.array(curve)
    peak = np.maximum.accumulate(eq_arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, (peak - eq_arr) / peak * 100, 0)

    return {
        "n_trades":     len(trades),
        "win_rate":     win_rate,
        "expectancy_R": exp_r,
        "profit_factor": pf,
        "max_dd_pct":   float(dd.max()),
        "n_tp": n_tp, "n_sl": n_sl, "n_ts": n_ts, "n_ttl": n_ttl,
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
    h1_slice = h1.loc[period_start:period_end].copy()
    if len(h1_slice) == 0:
        return _empty(symbol, rr, trail_cfg)

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
        return _empty(symbol, rr, trail_cfg)

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
    return {
        "symbol":        symbol,
        "rr":            rr,
        "trail_cfg":     str(trail_cfg),
        "n_trades":      m["n_trades"],
        "win_rate":      round(m["win_rate"] * 100, 1),
        "expectancy_R":  round(m["expectancy_R"], 4),
        "profit_factor": round(m["profit_factor"], 2),
        "max_dd_pct":    round(m["max_dd_pct"], 1),
        "n_tp": m["n_tp"], "n_sl": m["n_sl"],
        "n_ts": m["n_ts"], "n_ttl": m["n_ttl"],
        "is_baseline": trail_cfg is None,
    }


def _empty(symbol, rr, trail_cfg):
    return {
        "symbol": symbol, "rr": rr, "trail_cfg": str(trail_cfg),
        "n_trades": 0, "win_rate": 0.0, "expectancy_R": 0.0,
        "profit_factor": 0.0, "max_dd_pct": 0.0,
        "n_tp": 0, "n_sl": 0, "n_ts": 0, "n_ttl": 0,
        "is_baseline": trail_cfg is None,
    }


# ── Report ────────────────────────────────────────────────────────────────────

def generate_report(
    results_is: List[dict],   # period=IS (2023-2024) re-run for reference
    results_oos: List[dict],  # period=OOS (2025)
) -> str:
    lines = []
    ts_now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    lines.append("# Trailing Stop — Walidacja OOS 2025")
    lines.append("")
    lines.append(f"**Data:** {ts_now}  ")
    lines.append(f"**Cel:** Potwierdzenie stabilnosci wynikow TS z OOS 2023-2024  ")
    lines.append(f"**IS ref:** {IS_START} – {IS_END} (poprzedni OOS)  ")
    lines.append(f"**OOS 2025:** {OOS_START} – {OOS_END} (nowy hold-out)  ")
    lines.append(f"**Filtry:** ADX H4>=16 (poza CADJPY), ATR 10-80 (CADJPY)  ")
    lines.append(f"**Kandydaci:** {len(CANDIDATE_CONFIGS)} konfiguracji x {len(SYMBOLS)} symboli  ")
    lines.append("")

    # ── 1: Liczba barow 2025 ─────────────────────────────────────────────────
    lines.append("## 1. Dostepne dane 2025")
    lines.append("")
    lines.append("| Symbol | Bars 2025 | Trades (PROD, no TS) | Uwaga |")
    lines.append("|--------|-----------|---------------------|-------|")
    for sym in SYMBOLS:
        prod_oos = next(
            (r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR),
            None,
        )
        n_t = prod_oos["n_trades"] if prod_oos else 0
        note = "OK" if n_t >= 30 else ("MALO (<30 trades)" if n_t > 0 else "BRAK DANYCH")
        lines.append(f"| {sym} | — | {n_t} | {note} |")
    lines.append("")
    lines.append(
        "> Minimalna liczba transakcji do wiarygodnej oceny: **30**. "
        "Przy mniejszej liczbie wyniki sa podatne na szum."
    )
    lines.append("")

    # ── 2: PROD baseline — IS 2023-2024 vs OOS 2025 ─────────────────────────
    lines.append("## 2. PROD baseline: IS 2023-2024 vs OOS 2025 (RR=3.0, bez TS)")
    lines.append("")
    lines.append("| Symbol | IS ExpR | IS WR | IS DD | OOS 2025 ExpR | OOS 2025 WR | OOS 2025 DD | Stabilnosc |")
    lines.append("|--------|---------|-------|-------|---------------|-------------|-------------|------------|")
    for sym in SYMBOLS:
        r_is = next(
            (r for r in results_is  if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        r_oos = next(
            (r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        if not r_is or not r_oos:
            continue
        delta = r_oos["expectancy_R"] - r_is["expectancy_R"]
        if abs(delta) <= 0.05:
            stab = "STABLE"
        elif delta > 0.05:
            stab = "LEPSZY w 2025"
        else:
            stab = "GORSZY w 2025"
        lines.append(
            f"| {sym} "
            f"| {r_is['expectancy_R']:+.3f}R | {r_is['win_rate']}% | {r_is['max_dd_pct']}% "
            f"| {r_oos['expectancy_R']:+.3f}R | {r_oos['win_rate']}% | {r_oos['max_dd_pct']}% "
            f"| {stab} |"
        )
    lines.append("")

    # ── 3: Kandydaci TS — IS vs OOS 2025 ────────────────────────────────────
    lines.append("## 3. Kandydaci TS — IS 2023-2024 vs OOS 2025")
    lines.append("")
    lines.append("Konfiguarcje wybrane jako najlepsze w OOS 2023-2024 (z TRAILING_STOP_FX_ANALYSIS.md).")
    lines.append("")

    # Klucz do kandydatow per symbol
    SYMBOL_WINNERS = {
        "USDJPY": (2.5, {"ts_r": 2.0, "lock_r": 0.5}),
        "CADJPY": (3.0, {"ts_r": 2.0, "lock_r": 0.5}),
        "USDCHF": (3.0, {"ts_r": 1.5, "lock_r": 0.0}),
        "EURUSD": (3.0, {"ts_r": 1.5, "lock_r": 0.0}),
        "AUDJPY": (3.0, None),
    }

    lines.append(
        "| Symbol | Config | IS ExpR | IS WR | OOS 2025 ExpR | OOS 2025 WR | "
        "Δ IS→2025 | n_TS_2025 | Stabilnosc |"
    )
    lines.append(
        "|--------|--------|---------|-------|---------------|-------------|"
        "----------|-----------|------------|"
    )

    for sym in SYMBOLS:
        winner_rr, winner_tc = SYMBOL_WINNERS[sym]
        winner_tc_str = str(winner_tc)

        r_is = next(
            (r for r in results_is
             if r["symbol"] == sym and r["rr"] == winner_rr and r["trail_cfg"] == winner_tc_str),
            None,
        )
        r_oos = next(
            (r for r in results_oos
             if r["symbol"] == sym and r["rr"] == winner_rr and r["trail_cfg"] == winner_tc_str),
            None,
        )
        if not r_is or not r_oos:
            lines.append(f"| {sym} | brak danych | — | — | — | — | — | — | — |")
            continue

        delta = r_oos["expectancy_R"] - r_is["expectancy_R"]
        # Czy TS nadal bije PROD w 2025?
        prod_oos = next(
            (r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        beats_prod = (prod_oos is not None and r_oos["expectancy_R"] > prod_oos["expectancy_R"] + 0.03)

        if r_oos["n_trades"] < 15:
            stab = "ZA MALO DANYCH"
        elif abs(delta) <= 0.08 and beats_prod:
            stab = "STABLE ✅"
        elif r_oos["expectancy_R"] > 0 and beats_prod:
            stab = "DZIALA ✅"
        elif abs(delta) <= 0.08:
            stab = "STABLE (nie bije PROD)"
        else:
            stab = "NIESTABILNY ⚠️"

        tc_label = f"TS{winner_tc['ts_r']}R_lock{winner_tc['lock_r']}R" if winner_tc else "NO_TS"
        lines.append(
            f"| {sym} | RR={winner_rr} {tc_label} "
            f"| {r_is['expectancy_R']:+.3f}R | {r_is['win_rate']}% "
            f"| {r_oos['expectancy_R']:+.3f}R | {r_oos['win_rate']}% "
            f"| {delta:+.3f}R | {r_oos['n_ts']} | {stab} |"
        )
    lines.append("")

    # ── 4: Pelna tabela OOS 2025 ─────────────────────────────────────────────
    lines.append("## 4. Pelna tabela OOS 2025 — wszyscy kandydaci")
    lines.append("")
    lines.append("| Symbol | Config | RR | ExpR | WR | DD% | n_TP | n_SL | n_TS | vs PROD 2025 |")
    lines.append("|--------|--------|----|------|----|-----|------|------|------|------------|")
    for sym in SYMBOLS:
        prod_oos_expr = next(
            (r["expectancy_R"] for r in results_oos
             if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR),
            None,
        )
        sym_rows = sorted(
            [r for r in results_oos if r["symbol"] == sym],
            key=lambda r: r["expectancy_R"], reverse=True,
        )
        for r in sym_rows:
            tc = r["trail_cfg"]
            # Short label
            if tc == "None" or tc is None:
                tc_lbl = "NO_TS"
            else:
                tc_lbl = tc
            vs_prod = ""
            if prod_oos_expr is not None:
                d = r["expectancy_R"] - prod_oos_expr
                vs_prod = f"{d:+.3f}R"
                if d >= 0.05:
                    vs_prod += " ✅"
                elif d >= 0.0:
                    vs_prod += " ~"
                else:
                    vs_prod += " ❌"
            lines.append(
                f"| {sym} | {tc_lbl} | {r['rr']} "
                f"| {r['expectancy_R']:+.4f}R | {r['win_rate']}% | {r['max_dd_pct']}% "
                f"| {r['n_tp']} | {r['n_sl']} | {r['n_ts']} | {vs_prod} |"
            )
        lines.append("| | | | | | | | | | |")
    lines.append("")

    # ── 5: Porownanie trojokresowe ────────────────────────────────────────────
    lines.append("## 5. Porownanie trojokresowe IS/OOS_2324/OOS_2025")
    lines.append("")
    lines.append("IS = 2021-2022 (z TRAILING_STOP_FX_ANALYSIS.md) | OOS_2324 = 2023-2024 | OOS_2025 = 2025")
    lines.append("")
    lines.append(
        "| Symbol | Config | IS_2122 ExpR | OOS_2324 ExpR | OOS_2025 ExpR | Trend |"
    )
    lines.append(
        "|--------|--------|-------------|---------------|---------------|-------|"
    )

    # Dane IS 2021-2022 z poprzedniego raportu (hardkodowane z TRAILING_STOP_FX_ANALYSIS.md)
    IS_2122_PROD = {
        "EURUSD": -0.009, "USDJPY": +0.300, "USDCHF": +0.156,
        "AUDJPY": -0.017, "CADJPY": +0.346,
    }
    # OOS 2023-2024 winners z poprzedniego raportu
    OOS_2324_WINNERS = {
        "EURUSD": -0.139, "USDJPY": +0.147, "USDCHF": +0.035,
        "AUDJPY": +0.105, "CADJPY": +0.230,
    }
    OOS_2324_PROD = {
        "EURUSD": -0.190, "USDJPY": +0.049, "USDCHF": -0.010,
        "AUDJPY": +0.104, "CADJPY": +0.037,
    }

    for sym in SYMBOLS:
        winner_rr, winner_tc = SYMBOL_WINNERS[sym]
        winner_tc_str = str(winner_tc)
        tc_label = f"TS{winner_tc['ts_r']}R_lock{winner_tc['lock_r']}R" if winner_tc else "NO_TS"

        is_21 = IS_2122_PROD.get(sym, 0.0)
        oos_23 = OOS_2324_WINNERS.get(sym, 0.0)
        r_oos25 = next(
            (r for r in results_oos
             if r["symbol"] == sym and r["rr"] == winner_rr and r["trail_cfg"] == winner_tc_str),
            None,
        )
        oos_25 = r_oos25["expectancy_R"] if r_oos25 else float("nan")

        # Trend
        if not np.isnan(oos_25):
            if oos_25 > 0 and oos_23 > 0:
                trend = "STABILNY ✅"
            elif oos_25 > oos_23 - 0.05:
                trend = "TRZYMA ~"
            else:
                trend = "SPADA ⚠️"
        else:
            trend = "BRAK DANYCH"

        lines.append(
            f"| {sym} | RR={winner_rr} {tc_label} "
            f"| {is_21:+.3f}R | {oos_23:+.3f}R "
            f"| {oos_25:+.3f}R | {trend} |"
        )
    lines.append("")
    lines.append("*IS_2122 = PROD bez TS (referencja). OOS_2324/OOS_2025 = konfiguracja winner z poprzedniego testu.*")
    lines.append("")

    # ── 6: Wnioski ───────────────────────────────────────────────────────────
    lines.append("## 6. Wnioski walidacji 2025")
    lines.append("")

    # Auto-werdykt
    n_stable = 0
    n_total  = 0
    for sym in SYMBOLS:
        winner_rr, winner_tc = SYMBOL_WINNERS[sym]
        winner_tc_str = str(winner_tc)
        r_oos25 = next(
            (r for r in results_oos
             if r["symbol"] == sym and r["rr"] == winner_rr and r["trail_cfg"] == winner_tc_str),
            None,
        )
        prod_oos25 = next(
            (r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        if r_oos25 and prod_oos25 and r_oos25["n_trades"] >= 15:
            n_total += 1
            if r_oos25["expectancy_R"] > prod_oos25["expectancy_R"]:
                n_stable += 1

    lines.append(f"**Wynik:** {n_stable}/{n_total} par utrzymuje przewage TS nad PROD w 2025.")
    lines.append("")

    if n_stable >= n_total * 0.6:
        lines.append("**Werdykt: POTWIERDZONE** — trailing stop jest stabilny miedzyokresowo.")
    elif n_stable >= n_total * 0.4:
        lines.append("**Werdykt: CZESCIOWO POTWIERDZONE** — wyniki mieszane, kontynuowac obserwacje.")
    else:
        lines.append("**Werdykt: NIESTABILNY** — wyniki 2023-2024 nie powtarzaja sie w 2025.")
    lines.append("")

    lines.append("### Per-symbol")
    lines.append("")
    for sym in SYMBOLS:
        winner_rr, winner_tc = SYMBOL_WINNERS[sym]
        winner_tc_str = str(winner_tc)
        r_oos25 = next(
            (r for r in results_oos
             if r["symbol"] == sym and r["rr"] == winner_rr and r["trail_cfg"] == winner_tc_str), None)
        prod_oos25 = next(
            (r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        if not r_oos25:
            lines.append(f"- **{sym}**: brak danych 2025")
            continue
        tc_label = f"TS{winner_tc['ts_r']}R_lock{winner_tc['lock_r']}R" if winner_tc else "NO_TS"
        prod_expr_25 = prod_oos25["expectancy_R"] if prod_oos25 else 0.0
        delta_prod = r_oos25["expectancy_R"] - prod_expr_25
        if r_oos25["n_trades"] < 15:
            icon, verdict = "❓", "za mało transakcji"
        elif delta_prod >= 0.05:
            icon, verdict = "✅", "bije PROD w 2025"
        elif delta_prod >= 0.0:
            icon, verdict = "~", "rowny PROD w 2025"
        else:
            icon, verdict = "⚠️", "gorszy niz PROD w 2025"
        lines.append(
            f"- **{sym}** {icon}: `RR={winner_rr} {tc_label}` "
            f"→ 2025 ExpR={r_oos25['expectancy_R']:+.3f}R "
            f"vs PROD {prod_expr_25:+.3f}R (Δ={delta_prod:+.3f}R) "
            f"WR={r_oos25['win_rate']}% n_TS={r_oos25['n_ts']} — {verdict}"
        )
    lines.append("")

    lines.append("## 7. Decyzja")
    lines.append("")
    lines.append(
        "Na podstawie walidacji 2025, ostateczna rekomendacja implementacji "
        "trailing stop w `ibkr_exec.py`:"
    )
    lines.append("")
    lines.append("| Symbol | 2023-2024 | 2025 | Decyzja |")
    lines.append("|--------|-----------|------|---------|")
    decisions = []
    for sym in SYMBOLS:
        winner_rr, winner_tc = SYMBOL_WINNERS[sym]
        winner_tc_str = str(winner_tc)
        r_oos25 = next(
            (r for r in results_oos
             if r["symbol"] == sym and r["rr"] == winner_rr and r["trail_cfg"] == winner_tc_str), None)
        prod_oos25 = next(
            (r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        oos_2324 = OOS_2324_WINNERS.get(sym, 0.0)
        oos_25   = r_oos25["expectancy_R"] if r_oos25 else float("nan")
        prod_25  = prod_oos25["expectancy_R"] if prod_oos25 else 0.0
        n_t      = r_oos25["n_trades"] if r_oos25 else 0

        tc_label = f"TS{winner_tc['ts_r']}R_lock{winner_tc['lock_r']}R" if winner_tc else "NO_TS"

        if n_t < 15:
            decision = "❓ za malo danych — monitorowac"
        elif not np.isnan(oos_25) and oos_25 > prod_25 + 0.03 and oos_2324 > 0:
            decision = "✅ WDROZYT (obydwa okresy pozytywne)"
        elif not np.isnan(oos_25) and oos_25 > prod_25:
            decision = "⚠️ ROZWAZYC (2025 pozytywne, maly margines)"
        else:
            decision = "❌ WSTRZYMAC (niestabilne)"
        decisions.append((sym, oos_2324, oos_25, decision, tc_label, winner_rr))
        lines.append(
            f"| {sym} | {oos_2324:+.3f}R | "
            f"{oos_25:+.3f}R | {decision} |"
        )
    lines.append("")
    lines.append("---")
    lines.append(f"*Wygenerowano: {ts_now}*  ")
    lines.append(f"*Skrypt: scripts/trailing_stop_val2025.py*")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(" Trailing Stop — Walidacja OOS 2025")
    print(f" Symbole: {SYMBOLS}")
    print(f" IS ref : {IS_START} – {IS_END}")
    print(f" OOS    : {OOS_START} – {OOS_END}")
    print(f" Kandydaci: {len(CANDIDATE_CONFIGS)} konfiguracji")
    print("=" * 60)

    # ── Load data ─────────────────────────────────────────────────────────
    h1_data: Dict[str, pd.DataFrame] = {}
    all_setups: Dict[str, List[TradeSetup]] = {}
    gen = BOSPullbackSignalGenerator(PROD_CONFIG)

    for sym in SYMBOLS:
        print(f"\n[{sym}] Loading...")
        h1 = load_h1(sym)
        if h1 is None:
            continue
        h1_data[sym] = h1
        d1 = build_d1(h1)
        h4 = build_h4(h1)
        t0 = time.time()
        setups = gen.generate_all(sym, h1, d1, h4)
        all_setups[sym] = setups
        print(f"  {len(setups)} raw setups ({time.time()-t0:.1f}s)")

    # ── Run all configs ───────────────────────────────────────────────────
    total = len(SYMBOLS) * len(CANDIDATE_CONFIGS) * 2
    run_n = 0
    results_is:  List[dict] = []
    results_oos: List[dict] = []

    print(f"\nRunning {len(CANDIDATE_CONFIGS)} configs x {len(SYMBOLS)} symbols x 2 periods...")
    print()

    for sym in SYMBOLS:
        if sym not in h1_data:
            continue
        # Deduplicate configs for this symbol (same rr+trail_cfg might repeat)
        seen = set()
        for rr, trail_cfg, label in CANDIDATE_CONFIGS:
            key = (rr, str(trail_cfg))
            if key in seen:
                continue
            seen.add(key)

            t0 = time.time()
            r_is  = run_one(sym, all_setups[sym], h1_data[sym], rr, trail_cfg, IS_START,  IS_END)
            r_oos = run_one(sym, all_setups[sym], h1_data[sym], rr, trail_cfg, OOS_START, OOS_END)
            results_is.append(r_is)
            results_oos.append(r_oos)
            run_n += 2

            prod_oos_expr = next(
                (r["expectancy_R"] for r in results_oos
                 if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR),
                0.0,
            )
            delta = r_oos["expectancy_R"] - prod_oos_expr
            tc_short = f"TS{trail_cfg['ts_r']}R_lock{trail_cfg['lock_r']}R" if trail_cfg else "NO_TS"
            mark = " ✅" if delta >= 0.05 else ""
            print(
                f"  [{sym}] RR={rr} {tc_short:22s}: "
                f"IS={r_is['expectancy_R']:+.4f}R | "
                f"OOS_2025={r_oos['expectancy_R']:+.4f}R "
                f"WR={r_oos['win_rate']}% n_TS={r_oos['n_ts']}{mark} "
                f"({time.time()-t0:.1f}s)"
            )

    # ── Save CSV ──────────────────────────────────────────────────────────
    all_rows = (
        [{"period": "IS_2324",  **r} for r in results_is] +
        [{"period": "OOS_2025", **r} for r in results_oos]
    )
    csv_path = REPORT_DIR / "trailing_stop_val2025_results.csv"
    pd.DataFrame(all_rows).to_csv(csv_path, index=False)
    print(f"\nCSV: {csv_path}")

    # ── Report ────────────────────────────────────────────────────────────
    print("Generating report...")
    md = generate_report(results_is, results_oos)
    report_path = REPORT_DIR / "TRAILING_STOP_VAL2025.md"
    report_path.write_text(md, encoding="utf-8")
    print(f"Report: {report_path}")

    # ── Quick summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" QUICK SUMMARY — Winner config: IS_2324 vs OOS_2025")
    print("=" * 60)
    SYMBOL_WINNERS = {
        "USDJPY": (2.5, {"ts_r": 2.0, "lock_r": 0.5}),
        "CADJPY": (3.0, {"ts_r": 2.0, "lock_r": 0.5}),
        "USDCHF": (3.0, {"ts_r": 1.5, "lock_r": 0.0}),
        "EURUSD": (3.0, {"ts_r": 1.5, "lock_r": 0.0}),
        "AUDJPY": (3.0, None),
    }
    for sym in SYMBOLS:
        wr, wt = SYMBOL_WINNERS[sym]
        wt_str = str(wt)
        r_is  = next((r for r in results_is  if r["symbol"] == sym and r["rr"] == wr and r["trail_cfg"] == wt_str), None)
        r_oos = next((r for r in results_oos if r["symbol"] == sym and r["rr"] == wr and r["trail_cfg"] == wt_str), None)
        prod  = next((r for r in results_oos if r["symbol"] == sym and r["is_baseline"] and r["rr"] == PROD_RR), None)
        if r_is and r_oos and prod:
            tc_s = f"TS{wt['ts_r']}R_lock{wt['lock_r']}R" if wt else "NO_TS"
            beats = "BIJE PROD" if r_oos["expectancy_R"] > prod["expectancy_R"] + 0.01 else "nie bije PROD"
            print(
                f"  {sym:8s} RR={wr} {tc_s:22s}: "
                f"IS={r_is['expectancy_R']:+.4f}R → 2025={r_oos['expectancy_R']:+.4f}R "
                f"(PROD_2025={prod['expectancy_R']:+.4f}R) [{beats}]"
            )

    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()

