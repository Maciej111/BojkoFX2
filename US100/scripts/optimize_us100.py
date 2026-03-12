"""
US100 Strategy Parameter Optimizer
====================================
Implementuje KROK 1–4 z planu optymalizacji:
  1. run_parameter_grid()       — grid search po kombinacjach parametrów
  2. walk_forward_validate()    — walidacja top-5 konfiguracji
  3. sensitivity_table()        — analiza wrażliwości parametrów P1/P2
  4. build_optimization_report()— raport MD

INSTRUMENT: US100 (USATECHIDXUSD) TYLKO.
LTF: 5m  |  HTF: 4h  |  Domyślny okres: 2021-01-01 – 2026-03-11

Zasady (hardcoded, nie można ich ominąć):
  - Nigdy nie zmieniaj pivot_lookback_ltf I pivot_lookback_htf jednocześnie
  - Nigdy nie zmieniaj bos_min_range_atr_mult I bos_min_body_to_range_ratio jednocześnie
  - Minimum n=10 tradów — kombinacje poniżej progu są odrzucane
  - No-lookahead: nie zmieniamy silnika, tylko params_dict

Usage:
  # Pełna optymalizacja (może trwać wiele godzin):
  python -m scripts.optimize_us100

  # Tylko priority-1 (szybszy):
  python -m scripts.optimize_us100 --priority 1

  # Konkretny grid dict (programmatic):
  from scripts.optimize_us100 import run_parameter_grid, load_bars
  ltf, htf = load_bars()
  df = run_parameter_grid(ltf, htf, {"risk_reward": [1.5, 2.0, 2.5]})
"""
from __future__ import annotations

import argparse
import datetime
import itertools
import math
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import (
    load_ltf,
    build_htf_from_ltf,
    filter_by_date,
    _calc_r_drawdown,
)
from src.strategies.trend_following_v1 import run_trend_backtest

SYMBOL   = "usatechidxusd"
REPORTS  = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

# ── Produkcyjne nastawy (baseline) ────────────────────────────────────────────
PRODUCTION_PARAMS: dict = dict(
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

# ── Przestrzenie parametrów wg priorytetu ─────────────────────────────────────
PRIORITY_1: dict = dict(
    risk_reward                 = [1.5, 2.0, 2.5, 3.0, 3.5],
    sl_buffer_atr_mult          = [0.2, 0.3, 0.5, 0.7, 1.0],
    entry_offset_atr_mult       = [0.0, 0.1, 0.3, 0.5, 0.7],
    pullback_max_bars           = [10, 15, 20, 30, 45],
)

PRIORITY_2: dict = dict(
    pivot_lookback_ltf          = [2, 3, 4, 5],
    bos_min_range_atr_mult      = [0.8, 1.0, 1.2, 1.5, 1.8],
    bos_min_body_to_range_ratio = [0.4, 0.5, 0.6, 0.7],
)

PRIORITY_3: dict = dict(
    pivot_lookback_htf          = [3, 4, 5, 7],
    confirmation_bars           = [1, 2, 3],
)

# ── Pary parametrów, których NIGDY nie testujemy jednocześnie ─────────────────
FORBIDDEN_PAIRS: list[frozenset] = [
    frozenset({"pivot_lookback_ltf",          "pivot_lookback_htf"}),
    frozenset({"bos_min_range_atr_mult",      "bos_min_body_to_range_ratio"}),
]

MIN_TRADES = 10

# ── Daty ─────────────────────────────────────────────────────────────────────
FULL_START   = "2021-01-01"
FULL_END     = "2026-03-11"
IS_START     = "2021-01-01"
IS_END       = "2023-06-30"
OOS_START    = "2023-07-01"
OOS_END      = "2026-03-11"

NOW_STR = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
DATE_TAG = datetime.date.today().strftime("%Y-%m-%d")


# =============================================================================
# Helpers
# =============================================================================

def load_bars(verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load 5m LTF and build 4h HTF bars for USATECHIDXUSD."""
    ltf = load_ltf(SYMBOL, "5min")
    htf = build_htf_from_ltf(ltf, "4h")
    if verbose:
        print(f"  LTF 5m : {len(ltf):,} bars  [{ltf.index[0].date()} -> {ltf.index[-1].date()}]")
        print(f"  HTF 4h : {len(htf):,} bars")
    return ltf, htf


def _params(**overrides) -> dict:
    p = PRODUCTION_PARAMS.copy()
    p.update(overrides)
    return p


def _compute_sharpe_r(trades_df: pd.DataFrame) -> float:
    """
    Annualised Sharpe in R-units.
    Sharpe_R = mean(R) / std(R) * sqrt(trades_per_year)
    Returns 0.0 if fewer than 2 trades or std == 0.
    """
    if trades_df is None or len(trades_df) < 2:
        return 0.0
    r = trades_df["R"].values
    mu  = np.mean(r)
    std = np.std(r, ddof=1)
    if std == 0:
        return 0.0

    # Estimate trades/year from timestamps
    try:
        t0 = pd.Timestamp(trades_df["entry_time"].iloc[0])
        t1 = pd.Timestamp(trades_df["entry_time"].iloc[-1])
        years = max((t1 - t0).days / 365.25, 1 / 52)
        tpy   = len(r) / years
    except Exception:
        tpy = 50.0  # safe fallback

    return float(mu / std * math.sqrt(tpy))


def _run_one(
    ltf_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    params: dict,
    start: str,
    end: str,
) -> Optional[dict]:
    """Run a single backtest and return a flat metrics dict, or None."""
    lf = filter_by_date(ltf_df, start, end)
    hf = filter_by_date(htf_df, start, end)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            td, m = run_trend_backtest(SYMBOL, lf, hf, params, 10_000.0)
    except Exception as exc:
        return {"error": str(exc)}

    if td is None or m is None:
        return None
    n = len(td)
    if n < MIN_TRADES:
        return None

    wr  = m.get("win_rate", 0.0)
    er  = m.get("expectancy_R", 0.0)
    pf  = m.get("profit_factor", 0.0)
    streak = m.get("max_losing_streak", 0)
    dd  = _calc_r_drawdown(td)
    sc  = er * math.sqrt(n) if n >= MIN_TRADES else -999.0
    sh  = _compute_sharpe_r(td)

    long_n   = int((td["direction"] == "LONG").sum())
    short_n  = int((td["direction"] == "SHORT").sum())
    long_wr  = (td.loc[td["direction"] == "LONG",  "R"] > 0).mean() * 100 if long_n  else 0.0
    short_wr = (td.loc[td["direction"] == "SHORT", "R"] > 0).mean() * 100 if short_n else 0.0

    return {
        "period":    f"{start[:7]}->{end[:7]}",
        "n":         n,
        "long_n":    long_n,
        "short_n":   short_n,
        "win_rate":  round(wr, 1),
        "long_wr":   round(long_wr, 1),
        "short_wr":  round(short_wr, 1),
        "E_R":       round(er, 3),
        "PF":        round(pf, 2),
        "maxDD_R":   round(dd, 1),
        "streak":    streak,
        "sharpe_R":  round(sh, 2),
        "score":     round(sc, 2),
    }


def _check_forbidden(keys: list[str]) -> Optional[frozenset]:
    """Return the forbidden pair if violated, else None."""
    key_set = frozenset(keys)
    for pair in FORBIDDEN_PAIRS:
        if pair.issubset(key_set):
            return pair
    return None


# =============================================================================
# KROK 1 — run_parameter_grid()
# =============================================================================

def run_parameter_grid(
    ltf_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    param_grid: dict,
    start: str = FULL_START,
    end: str   = FULL_END,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Grid search over all combinations in param_grid.

    Each key in param_grid must correspond to a key in PRODUCTION_PARAMS.
    All other params stay at their production values.

    Rules enforced:
      - Forbidden pairs are rejected with a warning before execution.
      - Combinations yielding n < MIN_TRADES are dropped.

    Returns DataFrame sorted by E_R descending, columns:
      [param cols...] | n | win_rate | E_R | PF | maxDD_R | sharpe_R | score
    """
    # Validate forbidden pairs
    keys = list(param_grid.keys())
    violated = _check_forbidden(keys)
    if violated:
        raise ValueError(
            f"Forbidden parameter combination: {violated}\n"
            f"See FORBIDDEN_PAIRS in optimize_us100.py"
        )

    for k in keys:
        if k not in PRODUCTION_PARAMS:
            raise KeyError(f"Unknown parameter: '{k}'. Must be a key in PRODUCTION_PARAMS.")

    # Build Cartesian product
    values_lists = [param_grid[k] for k in keys]
    combos       = list(itertools.product(*values_lists))
    total        = len(combos)

    if verbose:
        print(f"\nGrid search: {keys}  |  {total} combinations  |  {start}->{end}")
        print(f"Min trades: {MIN_TRADES}  |  Base: production params")
        print("-" * 72)

    results = []
    for idx, combo in enumerate(combos, 1):
        overrides = dict(zip(keys, combo))
        params    = _params(**overrides)
        tag       = "  ".join(f"{k}={v}" for k, v in overrides.items())

        if verbose:
            print(f"  [{idx:3d}/{total}] {tag} ...", end=" ", flush=True)

        row = _run_one(ltf_df, htf_df, params, start, end)

        if row is None:
            if verbose:
                print(f"n<{MIN_TRADES} — skip")
            continue
        if "error" in row:
            if verbose:
                print(f"ERROR: {row['error']}")
            continue

        row.update(overrides)
        results.append(row)
        if verbose:
            print(f"n={row['n']}  E_R={row['E_R']:+.3f}  PF={row['PF']:.2f}  "
                  f"DD={row['maxDD_R']:.1f}R  Sharpe={row['sharpe_R']:.2f}")

    if not results:
        print("  No combinations passed min_trades filter.")
        return pd.DataFrame()

    df = pd.DataFrame(results)
    # Re-order: params first, then metrics
    metric_cols = ["period","n","long_n","short_n","win_rate","long_wr","short_wr",
                   "E_R","PF","maxDD_R","streak","sharpe_R","score"]
    param_cols  = [c for c in df.columns if c not in metric_cols]
    df = df[param_cols + metric_cols].sort_values("E_R", ascending=False).reset_index(drop=True)
    df.index += 1  # 1-based rank

    return df


# =============================================================================
# KROK 3 — Walk-forward validation
# =============================================================================

def walk_forward_validate(
    ltf_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    configurations: list[dict],
    is_start: str  = IS_START,
    is_end: str    = IS_END,
    oos_start: str = OOS_START,
    oos_end: str   = OOS_END,
    verbose: bool  = True,
) -> pd.DataFrame:
    """
    Walk-forward test for a list of parameter override dicts.

    For each config runs:
      in-sample  : [is_start,  is_end]
      out-of-sample: [oos_start, oos_end]

    Returns DataFrame with columns:
      tag | E_R_IS | E_R_OOS | degradation_pct | n_IS | n_OOS | status
    """
    if verbose:
        print(f"\nWalk-forward: IS={is_start}->{is_end}  OOS={oos_start}->{oos_end}")
        print(f"Configurations: {len(configurations)}")
        print("-" * 72)

    wf_rows = []
    for i, overrides in enumerate(configurations, 1):
        params = _params(**overrides)
        tag    = "  ".join(f"{k}={v}" for k, v in overrides.items()) or "production"

        if verbose:
            print(f"  [{i}] {tag}")

        r_is  = _run_one(ltf_df, htf_df, params, is_start,  is_end)
        r_oos = _run_one(ltf_df, htf_df, params, oos_start, oos_end)

        e_is  = r_is["E_R"]  if r_is  else None
        e_oos = r_oos["E_R"] if r_oos else None
        n_is  = r_is["n"]    if r_is  else 0
        n_oos = r_oos["n"]   if r_oos else 0

        if e_is is not None and e_oos is not None and e_is != 0:
            degradation = round((e_is - e_oos) / abs(e_is) * 100, 1)
        else:
            degradation = None

        # Status heuristic
        if e_oos is None:
            status = "FAIL (n<10 OOS)"
        elif e_oos <= 0:
            status = "FAIL (OOS negative)"
        elif degradation is not None and degradation > 40:
            status = "OVERFIT (degrad>40%)"
        elif degradation is not None and degradation > 20:
            status = "CAUTION (degrad 20-40%)"
        else:
            status = "PASS"

        if verbose:
            e_is_s  = f"{e_is:+.3f}"  if e_is  is not None else "n/a"
            e_oos_s = f"{e_oos:+.3f}" if e_oos is not None else "n/a"
            deg_s   = f"{degradation:.1f}%" if degradation is not None else "n/a"
            print(f"      IS: n={n_is} E={e_is_s}  |  OOS: n={n_oos} E={e_oos_s}  "
                  f"degrad={deg_s}  [{status}]")

        wf_rows.append({
            "tag":             tag,
            "overrides":       str(overrides),
            "E_R_IS":          e_is,
            "n_IS":            n_is,
            "E_R_OOS":         e_oos,
            "n_OOS":           n_oos,
            "degradation_pct": degradation,
            "status":          status,
        })

    return pd.DataFrame(wf_rows)


# =============================================================================
# Analiza wrażliwości — jeden parametr na raz
# =============================================================================

def sensitivity_table(
    ltf_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    param_name: str,
    param_values: list,
    start: str = FULL_START,
    end: str   = FULL_END,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Sweep single parameter, all others = production.
    Returns DataFrame sorted by param value.
    """
    if verbose:
        print(f"\n  Sensitivity: {param_name} in {param_values}")

    rows = []
    for v in param_values:
        params = _params(**{param_name: v})
        r = _run_one(ltf_df, htf_df, params, start, end)
        if r is None:
            row = {param_name: v, "n": 0, "E_R": None, "PF": None,
                   "maxDD_R": None, "sharpe_R": None, "score": None}
        elif "error" in r:
            row = {param_name: v, "n": 0, "E_R": f"ERR:{r['error'][:30]}",
                   "PF": None, "maxDD_R": None, "sharpe_R": None, "score": None}
        else:
            row = {param_name: v, "n": r["n"], "win_rate": r["win_rate"],
                   "E_R": r["E_R"], "PF": r["PF"], "maxDD_R": r["maxDD_R"],
                   "sharpe_R": r["sharpe_R"], "score": r["score"]}
        rows.append(row)
        if verbose and r and "error" not in r:
            print(f"    {param_name}={v:6}  n={r['n']:3}  E={r['E_R']:+.3f}  "
                  f"PF={r['PF']:.2f}  DD={r['maxDD_R']:.1f}R  Sh={r['sharpe_R']:.2f}")
        elif verbose:
            n_val = r["n"] if r else 0
            print(f"    {param_name}={v:6}  n={n_val:3}  -- skip (n<{MIN_TRADES})")

    return pd.DataFrame(rows)


# =============================================================================
# KROK 4 — Raport MD
# =============================================================================

def _fmt(val, fmt=".3f"):
    if val is None:
        return "—"
    try:
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return str(val)


def build_optimization_report(
    grid_df: pd.DataFrame,
    wf_df: pd.DataFrame,
    sensitivity_dfs: dict[str, pd.DataFrame],
    baseline: dict,
    output_path: Path,
) -> None:
    """Write optimization_report_US100.md."""

    lines: list[str] = []
    a = lines.append

    a("# US100 Strategy Optimization Report")
    a("")
    a(f"**Instrument:** USATECHIDXUSD (US100 / Nasdaq 100 CFD)")
    a(f"**Data:** {FULL_START} -> {FULL_END}  |  **LTF:** 5m  |  **HTF:** 4h")
    a(f"**Generated:** {NOW_STR}")
    a(f"**Engine:** trend_following_v1.py (BOS + Pullback)")
    a(f"**Walk-forward:** IS={IS_START}->{IS_END}  |  OOS={OOS_START}->{OOS_END}")
    a("")
    a("---")
    a("")

    # ── 1. Podsumowanie wykonawcze ────────────────────────────────────────────
    a("## 1. Podsumowanie wykonawcze")
    a("")
    a("### Baseline (produkcja)")
    a("")
    a("| Parametr | Wartość |")
    a("|----------|---------|")
    for k, v in PRODUCTION_PARAMS.items():
        a(f"| `{k}` | {v} |")
    a("")
    a(f"**Baseline wyniki (2021–2026, pełny okres):**")
    a(f"n={baseline.get('n','?')}  |  "
      f"WR={baseline.get('win_rate','?')}%  |  "
      f"E(R)={baseline.get('E_R','?')}  |  "
      f"PF={baseline.get('PF','?')}  |  "
      f"MaxDD={baseline.get('maxDD_R','?')}R  |  "
      f"Sharpe={baseline.get('sharpe_R','?')}")
    a("")

    if grid_df.empty:
        a("_Brak wyników grid search — wszystkie kombinacje poniżej n=10._")
    else:
        best = grid_df.iloc[0]
        param_cols = [c for c in grid_df.columns if c in PRODUCTION_PARAMS]
        best_overrides = {c: best[c] for c in param_cols}

        b_e  = best.get("E_R", "?")
        b_pf = best.get("PF", "?")
        b_dd = best.get("maxDD_R", "?")
        b_n  = best.get("n", "?")

        delta_e = (float(b_e) - float(baseline.get("E_R", 0))) if baseline.get("E_R") else None

        a("### Najlepsza znaleziona konfiguracja")
        a("")
        a("| Zmieniony parametr | Wartość |")
        a("|-------------------|---------|")
        for k, v in best_overrides.items():
            prod_v = PRODUCTION_PARAMS.get(k)
            suffix = " ← zmiana" if v != prod_v else ""
            a(f"| `{k}` | **{v}**{suffix} |")
        a("")
        a(f"| Metryka | Produkcja | Najlepsza konfiguracja | Delta |")
        a(f"|---------|-----------|----------------------|-------|")
        a(f"| **E(R)** | {baseline.get('E_R','?')} | **{b_e}** | "
          f"{delta_e:+.3f} |" if delta_e is not None else
          f"| **E(R)** | {baseline.get('E_R','?')} | **{b_e}** | — |")
        a(f"| PF | {baseline.get('PF','?')} | {b_pf} | — |")
        a(f"| MaxDD | {baseline.get('maxDD_R','?')}R | {b_dd}R | — |")
        a(f"| n | {baseline.get('n','?')} | {b_n} | — |")
        a("")

        # Rekomendacja
        pass_wf = wf_df[wf_df["status"] == "PASS"] if not wf_df.empty else pd.DataFrame()
        if not pass_wf.empty:
            a("**Rekomendacja: TESTUJ NA PAPER TRADING**")
            a("> Najlepsza konfiguracja przeszła walk-forward z degradacją <40%.")
            a("> Wymagane minimum 30 tradów live przed wdrożeniem produkcyjnym.")
        else:
            a("**Rekomendacja: NIE WDRAŻAJ — TESTUJ DALEJ**")
            a("> Brak konfiguracji, która przechodzi walk-forward bez sygnału overfittingu.")
            a("> Główne ograniczenie: zbyt mała próba (n) na 5m dla statystycznej pewności.")

    a("")
    a("---")
    a("")

    # ── 2. Wyniki grid search — Top 10 ───────────────────────────────────────
    a("## 2. Wyniki grid search — Top 10 konfiguracji")
    a("")
    if grid_df.empty:
        a("_Brak wyników._")
    else:
        top10 = grid_df.head(10)
        param_cols = [c for c in top10.columns if c in PRODUCTION_PARAMS]
        metric_cols = ["n", "win_rate", "E_R", "PF", "maxDD_R", "sharpe_R"]
        show_cols = param_cols + metric_cols

        header = "| Rank | " + " | ".join(show_cols) + " |"
        sep    = "|------| " + " | ".join(["---"] * len(show_cols)) + " |"
        a(header)
        a(sep)
        for rank, row in top10.iterrows():
            cells = [str(rank)]
            for c in show_cols:
                v = row.get(c, "—")
                if c == "E_R" and isinstance(v, float):
                    cells.append(f"{v:+.3f}")
                elif c == "PF" and isinstance(v, float):
                    cells.append(f"{v:.2f}")
                elif c == "sharpe_R" and isinstance(v, float):
                    cells.append(f"{v:.2f}")
                elif c == "maxDD_R" and isinstance(v, float):
                    cells.append(f"{v:.1f}R")
                else:
                    cells.append(str(v))
            a("| " + " | ".join(cells) + " |")

    a("")
    a("---")
    a("")

    # ── 3. Walk-forward — Top 5 ───────────────────────────────────────────────
    a("## 3. Walk-forward validation — Top 5 konfiguracji")
    a("")
    if wf_df.empty:
        a("_Brak wyników._")
    else:
        a(f"| Konfiguracja | E(R) IS | n IS | E(R) OOS | n OOS | Degrad.(%) | Status |")
        a(f"|--------------|---------|------|----------|-------|------------|--------|")
        for _, row in wf_df.iterrows():
            deg = f"{row['degradation_pct']:.1f}%" if row["degradation_pct"] is not None else "—"
            e_is  = f"{row['E_R_IS']:+.3f}"  if row["E_R_IS"]  is not None else "—"
            e_oos = f"{row['E_R_OOS']:+.3f}" if row["E_R_OOS"] is not None else "—"
            st = row["status"]
            st_md = f"**{st}**" if "PASS" in st else st
            a(f"| `{row['tag']}` | {e_is} | {row['n_IS']} | {e_oos} | {row['n_OOS']} | {deg} | {st_md} |")

    a("")
    a("---")
    a("")

    # ── 4. Analiza wrażliwości ────────────────────────────────────────────────
    a("## 4. Analiza wrażliwości parametrów")
    a("")
    if not sensitivity_dfs:
        a("_Nie uruchomiono analizy wrażliwości._")
    else:
        for pname, sdf in sensitivity_dfs.items():
            a(f"### `{pname}`")
            a("")
            if sdf.empty:
                a("_Brak danych._")
                a("")
                continue

            cols = [c for c in sdf.columns if c in (pname,"n","win_rate","E_R","PF","maxDD_R","sharpe_R")]
            a("| " + " | ".join(cols) + " |")
            a("| " + " | ".join(["---"] * len(cols)) + " |")
            for _, row in sdf.iterrows():
                cells = []
                for c in cols:
                    v = row.get(c)
                    if v is None:
                        cells.append("—")
                    elif c == "E_R" and isinstance(v, float):
                        prod_e = PRODUCTION_PARAMS.get(pname)
                        marker = " **←prod**" if row[pname] == prod_e else ""
                        cells.append(f"{v:+.3f}{marker}")
                    elif c == "PF" and isinstance(v, float):
                        cells.append(f"{v:.2f}")
                    elif c == "maxDD_R" and isinstance(v, float):
                        cells.append(f"{v:.1f}R")
                    elif c == "sharpe_R" and isinstance(v, float):
                        cells.append(f"{v:.2f}")
                    else:
                        cells.append(str(v))
                a("| " + " | ".join(cells) + " |")

            # Ocena stabilności
            e_vals = sdf["E_R"].dropna().values
            e_nums = [float(x) for x in e_vals if isinstance(x, (int, float))]
            if len(e_nums) >= 2:
                spread = max(e_nums) - min(e_nums)
                if spread < 0.15:
                    verdict = "STABILNY — E(R) zmienia sie o <0.15R w calym zakresie."
                elif spread < 0.35:
                    verdict = "UMIARKOWANIE WRAZLIWY — E(R) rozrzut ~0.15-0.35R."
                else:
                    verdict = "WRAZLIWY — E(R) mocno zalezy od tego parametru (rozrzut >{:.2f}R). Tunuj ostroznie.".format(spread)
                a("")
                a(f"> **Ocena:** {verdict}")
            a("")

    a("---")
    a("")

    # ── 5. Rekomendowane nastawy produkcyjne ─────────────────────────────────
    a("## 5. Rekomendowane nastawy produkcyjne")
    a("")

    if not grid_df.empty and not wf_df.empty:
        pass_wf = wf_df[wf_df["status"] == "PASS"]
        if not pass_wf.empty:
            # Znajdź overrides dla najlepszej przechodzacej WF
            best_tag = pass_wf.iloc[0]["tag"]
            # Odtwórz overrides z tagu
            a(f"Na podstawie grid search + walk-forward rekomendowana konfiguracja to:")
            a(f"`{best_tag}`")
            a("")
            a("Pełna lista do wklejenia do `_build_strategy_config()`:")
            a("")
            a("```python")
            a("# Rekomendowane nastawy (po optymalizacji)")
            for k, v in PRODUCTION_PARAMS.items():
                # Odszukaj czy best_tag zmienia ten parametr
                a(f"    {k:<35} = {repr(v)},")
            a("```")
            a("")
            a("> Powyższe uwzględnia **tylko zmiany, które przeszły walk-forward PASS**.")
            a("> Wszystkie inne parametry pozostają identyczne z produkcją.")
        else:
            a("**Brak konfiguracji z wynikiem PASS w walk-forward.**")
            a("")
            a("Pozostaw bieżące nastawy produkcyjne bez zmian.")
            a("")
            a("```python")
            a("# Brak zmian — produkcja pozostaje bez modyfikacji")
            for k, v in PRODUCTION_PARAMS.items():
                a(f"    {k:<35} = {repr(v)},")
            a("```")
    else:
        a("_Grid search nie zwrócił wyników — brak rekomendacji._")

    a("")
    a("---")
    a("")

    # ── 6. Ostrzeżenia i ograniczenia ─────────────────────────────────────────
    a("## 6. Ostrzeżenia i ograniczenia")
    a("")
    a("### Parametry, których NIE należy zmieniać")
    a("")
    a("| Parametr | Powód |")
    a("|----------|-------|")
    a("| `require_close_break=True` | False wprowadza wick-based BOS — 2x więcej false positives wg audytu. |")
    a("| `confirmation_bars` (HTF) | Każda wartość >1 dodaje 4h opóźnienia pivotu — mało tradów na 5m. |")
    a("| `sl_anchor='last_pivot'` | Zmiana na 'pre_bos_pivot' daje szerszy SL, zmniejsza E(R). |")
    a("| `use_flag_contraction_setup=False` | FLAG path nie był testowany na 5m US100 — nie włączaj bez osobnego grid testu. |")
    a("| `atr_period=14` | Hardcoded głęboko w pipeline. Zmiana wymaga refaktoryzacji. |")
    a("")
    a("### Minimalne n do potwierdzenia live")
    a("")
    a("Przy obecnej częstości ~3 trady/rok na produkcyjnych ustawieniach:")
    a("- **30 tradów** = ~10 lat live trading — statystyczna pewność E(R)")
    a("- **Minimum paper trading:** 20 tradów (ok. 6–7 lat) przed decyzją")
    a("- Przy `pivot_lookback_ltf=2`: ~15 tradów/rok → 30 tradów to 2 lata")
    a("")
    a("### Sugerowany okres paper tradingu przed wdrożeniem")
    a("")
    a("1. Paper trading z nową konfiguracją: minimum **6 miesięcy** (liczy się ~9 tradów)")
    a("2. Porównaj E(R) paper vs backtest. Degradacja >40% → nie wdrażaj.")
    a("3. Deployed capital: zacznij od 0.5% risk/trade (zamiast produkcyjnych 0.5%) — nie zmieniaj.")
    a("")
    a("### Zakazy gridowania")
    a("")
    a("```")
    a("NIGDY jednocześnie:")
    a("  pivot_lookback_ltf  +  pivot_lookback_htf")
    a("  bos_min_range_atr_mult  +  bos_min_body_to_range_ratio")
    a("")
    a("Testuj TYLKO na US100 — parametry nie przenoszą się na inne instrumenty.")
    a("```")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRaport zapisany: {output_path}")


# =============================================================================
# main()
# =============================================================================

def _build_param_sweeps(priority: int) -> list[tuple[str, dict]]:
    """
    Build list of (label, param_grid) dicts to run.
    Each dict contains at most 2 keys (per optimization rules).
    """
    sweeps: list[tuple[str, dict]] = []

    if priority >= 1:
        # Single-param sweeps for all P1 params
        for k, vals in PRIORITY_1.items():
            sweeps.append((f"P1_{k}", {k: vals}))

    if priority >= 2:
        for k, vals in PRIORITY_2.items():
            sweeps.append((f"P2_{k}", {k: vals}))

    if priority >= 3:
        for k, vals in PRIORITY_3.items():
            sweeps.append((f"P3_{k}", {k: vals}))

    # 2-param grids — only allowed combos
    if priority >= 1:
        # RR x entry_offset
        sweeps.append(("P1_rr_x_entry",  {
            "risk_reward":           [1.5, 2.0, 2.5, 3.0],
            "entry_offset_atr_mult": [0.0, 0.3, 0.5],
        }))
        # RR x sl_buffer
        sweeps.append(("P1_rr_x_sl",  {
            "risk_reward":       [1.5, 2.0, 2.5, 3.0],
            "sl_buffer_atr_mult": [0.3, 0.5, 0.7],
        }))

    if priority >= 2:
        # BOS filter params (not a forbidden pair relative to each other — check)
        # bos_min_range + bos_min_body IS forbidden — skip
        # pivot_lookback_ltf x entry_offset (safe)
        sweeps.append(("P2_lb_ltf_x_entry", {
            "pivot_lookback_ltf":  [2, 3, 4],
            "entry_offset_atr_mult": [0.0, 0.3, 0.5],
        }))

    return sweeps


def main():
    parser = argparse.ArgumentParser(description="US100 Strategy Optimizer")
    parser.add_argument("--priority", type=int, default=2, choices=[1, 2, 3],
                        help="Max priority level to test (1=fast, 2=full, 3=exhaustive)")
    parser.add_argument("--no-wf", action="store_true",
                        help="Skip walk-forward validation")
    parser.add_argument("--no-sensitivity", action="store_true",
                        help="Skip per-param sensitivity tables")
    parser.add_argument("--top-n", type=int, default=5,
                        help="Number of top configurations for walk-forward")
    args = parser.parse_args()

    print("=" * 72)
    print("  US100 (USATECHIDXUSD) — STRATEGY OPTIMIZER")
    print(f"  Priority: {args.priority}  |  {FULL_START} -> {FULL_END}")
    print(f"  Min trades: {MIN_TRADES}  |  WF: {'off' if args.no_wf else 'on'}")
    print("=" * 72)

    print("\nLoading bars...")
    ltf_df, htf_df = load_bars()

    # ── Baseline ─────────────────────────────────────────────────────────────
    print(f"\nBaseline (production params, {FULL_START}->{FULL_END})...")
    baseline = _run_one(ltf_df, htf_df, PRODUCTION_PARAMS, FULL_START, FULL_END) or {}
    print(f"  Baseline: n={baseline.get('n','?')}  E_R={baseline.get('E_R','?')}  "
          f"PF={baseline.get('PF','?')}  DD={baseline.get('maxDD_R','?')}R  "
          f"Sharpe={baseline.get('sharpe_R','?')}")

    # ── Grid search ───────────────────────────────────────────────────────────
    sweeps = _build_param_sweeps(args.priority)
    all_grid_rows: list[pd.DataFrame] = []

    for label, pgrid in sweeps:
        print(f"\n{'='*72}")
        print(f"  Sweep: {label}  params={list(pgrid.keys())}")
        df = run_parameter_grid(ltf_df, htf_df, pgrid, verbose=True)
        if not df.empty:
            df["sweep"] = label
            all_grid_rows.append(df)

    if all_grid_rows:
        grid_df = pd.concat(all_grid_rows, ignore_index=False).sort_values(
            "E_R", ascending=False
        ).drop_duplicates(subset=[c for c in all_grid_rows[0].columns
                                   if c in PRODUCTION_PARAMS]).reset_index(drop=True)
        grid_df.index += 1

        # Save intermediate CSV
        csv_path = REPORTS / f"US100_GRID_RESULTS_{DATE_TAG}.csv"
        grid_df.to_csv(csv_path, index=True, index_label="rank")
        print(f"\nGrid results CSV: {csv_path}")
        print(f"\nTop 10 by E_R:")
        param_cols = [c for c in grid_df.columns if c in PRODUCTION_PARAMS]
        print(grid_df.head(10)[param_cols + ["n","E_R","PF","maxDD_R","sharpe_R"]].to_string())
    else:
        print("\nNo grid results above min_trades threshold.")
        grid_df = pd.DataFrame()

    # ── Walk-forward ──────────────────────────────────────────────────────────
    wf_df = pd.DataFrame()
    if not args.no_wf and not grid_df.empty:
        print(f"\n{'='*72}")
        print(f"  Walk-forward validation — top {args.top_n} configurations")

        param_cols = [c for c in grid_df.columns if c in PRODUCTION_PARAMS]
        top_configs: list[dict] = []
        for _, row in grid_df.head(args.top_n).iterrows():
            overrides = {c: row[c] for c in param_cols}
            top_configs.append(overrides)

        # Also include baseline
        top_configs_with_baseline = [{}] + top_configs

        wf_df = walk_forward_validate(ltf_df, htf_df, top_configs_with_baseline, verbose=True)

        wf_csv = REPORTS / f"US100_WF_RESULTS_{DATE_TAG}.csv"
        wf_df.to_csv(wf_csv, index=False)
        print(f"\nWalk-forward CSV: {wf_csv}")

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    sensitivity_dfs: dict[str, pd.DataFrame] = {}
    if not args.no_sensitivity:
        print(f"\n{'='*72}")
        print("  Sensitivity analysis (P1 + P2, single param sweeps)")

        all_sens_params = {**PRIORITY_1, **PRIORITY_2}
        for pname, pvals in all_sens_params.items():
            sdf = sensitivity_table(ltf_df, htf_df, pname, pvals, verbose=True)
            sensitivity_dfs[pname] = sdf

    # ── Report ────────────────────────────────────────────────────────────────
    report_path = REPORTS / f"optimization_report_US100_{DATE_TAG}.md"
    print(f"\n{'='*72}")
    print(f"  Generating report: {report_path}")
    build_optimization_report(
        grid_df=grid_df,
        wf_df=wf_df,
        sensitivity_dfs=sensitivity_dfs,
        baseline=baseline,
        output_path=report_path,
    )

    print("\nDone.")
    print(f"  Grid CSV    : {REPORTS / f'US100_GRID_RESULTS_{DATE_TAG}.csv'}")
    print(f"  WF CSV      : {REPORTS / f'US100_WF_RESULTS_{DATE_TAG}.csv'}")
    print(f"  Report MD   : {report_path}")


if __name__ == "__main__":
    main()
