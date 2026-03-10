"""
backtests/metrics.py
Obliczanie metryk z listy ClosedTrade.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signals_bos_pullback import ClosedTrade


def calc_metrics(trades: List[ClosedTrade],
                 initial_equity: float = 10_000.0,
                 label: str = "") -> dict:
    """
    Oblicza kompletny zestaw metryk dla listy zamkniętych transakcji.

    Includes robustness diagnostics:
      median_R              – median R per trade (less sensitive to outliers than mean)
      top_5_trade_r_share   – fraction of total absolute R from the top 5 winning trades
      outlier_dependence    – True if top 5 trades account for >50% of total absolute R

    These diagnostics quantify tail dependence: a strategy where top_5_trade_r_share
    is very high depends critically on a small number of outlier wins.
    """
    if not trades:
        return _empty_metrics(label)

    df = _to_df(trades)
    # Exclude TTL from R stats (TTL = 0R, nie jest TP ani SL)
    filled = df[df["exit_reason"] != "TTL"]
    tp_sl  = filled  # tylko TP/SL

    n_total      = len(df)
    n_tp_sl      = len(tp_sl)
    n_tp         = int((tp_sl["exit_reason"] == "TP").sum())
    n_sl         = int((tp_sl["exit_reason"] == "SL").sum())
    n_ttl        = int((df["exit_reason"] == "TTL").sum())
    win_rate     = n_tp / n_tp_sl if n_tp_sl > 0 else 0.0

    r_vals       = tp_sl["r_multiple"].values
    avg_r        = float(np.mean(r_vals)) if len(r_vals) > 0 else 0.0
    median_r     = float(np.median(r_vals)) if len(r_vals) > 0 else 0.0
    avg_win_r    = float(np.mean(r_vals[r_vals > 0])) if (r_vals > 0).any() else 0.0
    avg_loss_r   = float(np.mean(r_vals[r_vals < 0])) if (r_vals < 0).any() else 0.0

    wins_pnl  = tp_sl.loc[tp_sl["r_multiple"] > 0, "pnl_price"].sum()
    loss_pnl  = abs(tp_sl.loc[tp_sl["r_multiple"] < 0, "pnl_price"].sum())
    pf        = wins_pnl / loss_pnl if loss_pnl > 0 else (np.inf if wins_pnl > 0 else 0.0)

    # ── Robustness: outlier contribution ─────────────────────────────────────
    # Top-5 winning trades' R as a share of total |R| across all TP/SL trades
    top5_r_share = _top_n_trade_r_share(r_vals, n=5)
    outlier_dependence = top5_r_share > 0.50 if not np.isnan(top5_r_share) else False

    # ── Equity curve ─────────────────────────────────────────────────────────
    eq_curve = _equity_curve(df, initial_equity)
    max_dd   = _max_drawdown(eq_curve)

    # Consecutive losses
    cons_losses = _max_consecutive_losses(tp_sl["r_multiple"].values)

    # Trades per month
    if len(df) >= 2:
        span_months = (df["exit_ts"].max() - df["exit_ts"].min()).days / 30.44
        tpm = n_total / span_months if span_months > 0 else 0.0
    else:
        tpm = 0.0

    # Exposure: średnia liczba barów w pozycji
    avg_bars = float(df["bars_held"].mean()) if n_total > 0 else 0.0

    # Stability: % dodatnich miesięcy
    pct_pos_months, pct_pos_quarters = _stability(df)

    # Tail risk: 95th percentile worst monthly drawdown
    tail_risk = _tail_risk(eq_curve, df)

    return {
        "label":                label,
        "n_trades":             n_total,
        "n_tp":                 n_tp,
        "n_sl":                 n_sl,
        "n_ttl":                n_ttl,
        "win_rate":             round(win_rate, 4),
        "expectancy_R":         round(avg_r, 4),
        "median_R":             round(median_r, 4),
        "avg_win_R":            round(avg_win_r, 4),
        "avg_loss_R":           round(avg_loss_r, 4),
        "profit_factor":        round(pf, 3),
        "max_dd_pct":           round(max_dd * 100, 2),
        "max_cons_losses":      cons_losses,
        "trades_per_month":     round(tpm, 2),
        "avg_bars_held":        round(avg_bars, 1),
        "pct_pos_months":       round(pct_pos_months, 2),
        "pct_pos_quarters":     round(pct_pos_quarters, 2),
        "tail_risk_95":         round(tail_risk * 100, 2),
        # Robustness diagnostics
        "top_5_trade_r_share":  round(top5_r_share, 4) if not np.isnan(top5_r_share) else None,
        "outlier_dependence":   outlier_dependence,
    }


def _to_df(trades: List[ClosedTrade]) -> pd.DataFrame:
    rows = []
    for t in trades:
        rows.append({
            "symbol":      t.symbol,
            "side":        t.side,
            "entry_ts":    t.entry_ts,
            "exit_ts":     t.exit_ts,
            "entry_price": t.entry_price,
            "exit_price":  t.exit_price,
            "exit_reason": t.exit_reason,
            "r_multiple":  t.r_multiple,
            "pnl_price":   t.pnl_price,
            "bars_held":   t.bars_held,
            "rr":          t.rr,
            "adx_val":     t.adx_val,
            "atr_pct_val": t.atr_pct_val,
            "units":       t.units,
        })
    df = pd.DataFrame(rows)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    return df.sort_values("exit_ts").reset_index(drop=True)


def _equity_curve(df: pd.DataFrame, initial_equity: float) -> pd.Series:
    """Equity curve jako kumulatywna suma PnL od initial_equity."""
    eq = initial_equity + df["pnl_price"].cumsum()
    return pd.concat([pd.Series([initial_equity]), eq]).reset_index(drop=True)


def _max_drawdown(eq: pd.Series) -> float:
    """Max drawdown jako ułamek (0–1)."""
    running_max = eq.cummax()
    dd = (eq - running_max) / running_max.replace(0, np.nan)
    return float(dd.min()) * -1 if len(dd) > 0 else 0.0


def _top_n_trade_r_share(r_vals: np.ndarray, n: int = 5) -> float:
    """
    Returns the fraction of total absolute R contributed by the top-n winning trades.

    A value close to 1.0 indicates extreme tail dependence — the strategy's entire
    P&L is driven by a handful of outlier trades.

    Returns float(nan) if there are fewer than n trades.
    """
    if len(r_vals) < n:
        return float("nan")
    winning = np.sort(r_vals[r_vals > 0])[::-1]  # descending
    top_n   = winning[:n]
    total_abs_r = np.abs(r_vals).sum()
    if total_abs_r == 0:
        return 0.0
    return float(top_n.sum() / total_abs_r)


def _max_consecutive_losses(r_vals: np.ndarray) -> int:
    max_c = cur = 0
    for r in r_vals:
        if r < 0:
            cur += 1
            max_c = max(max_c, cur)
        else:
            cur = 0
    return max_c


def _stability(df: pd.DataFrame) -> tuple[float, float]:
    """
    Zwraca (pct_positive_months, pct_positive_quarters).
    """
    if df.empty:
        return 0.0, 0.0
    df2 = df.copy()
    # strip timezone so to_period() works without warnings
    exit_ts_naive = df2["exit_ts"].dt.tz_localize(None) if df2["exit_ts"].dt.tz is not None else df2["exit_ts"]
    df2["ym"] = exit_ts_naive.dt.to_period("M")
    df2["yq"] = exit_ts_naive.dt.to_period("Q")
    m_pnl = df2.groupby("ym")["pnl_price"].sum()
    q_pnl = df2.groupby("yq")["pnl_price"].sum()
    pct_m = float((m_pnl > 0).mean()) if len(m_pnl) > 0 else 0.0
    pct_q = float((q_pnl > 0).mean()) if len(q_pnl) > 0 else 0.0
    return pct_m, pct_q


def _tail_risk(eq: pd.Series, df: pd.DataFrame) -> float:
    """
    95th percentile najgorszego drawdownu rocznego.
    Uproszczone: max drawdown na każdym roku, zwróć 95. percentyl.
    """
    if df.empty:
        return 0.0
    yearly_dds = []
    for year, grp in df.groupby(df["exit_ts"].dt.year):
        mask = grp.index
        sub_eq = initial_eq = 0.0
        pnls = grp["pnl_price"].values
        peak = 0.0
        cur = 0.0
        worst = 0.0
        for p in pnls:
            cur += p
            if cur > peak:
                peak = cur
            dd = (peak - cur) / (abs(peak) + 1e-9)
            worst = max(worst, dd)
        yearly_dds.append(worst)
    if not yearly_dds:
        return 0.0
    return float(np.percentile(yearly_dds, 95))


def _empty_metrics(label: str) -> dict:
    return {
        "label": label, "n_trades": 0, "n_tp": 0, "n_sl": 0, "n_ttl": 0,
        "win_rate": 0.0, "expectancy_R": 0.0, "median_R": 0.0,
        "avg_win_R": 0.0, "avg_loss_R": 0.0,
        "profit_factor": 0.0, "max_dd_pct": 0.0, "max_cons_losses": 0,
        "trades_per_month": 0.0, "avg_bars_held": 0.0,
        "pct_pos_months": 0.0, "pct_pos_quarters": 0.0, "tail_risk_95": 0.0,
        "top_5_trade_r_share": None, "outlier_dependence": False,
    }


def metrics_per_symbol(trades: List[ClosedTrade],
                        initial_equity: float = 10_000.0) -> Dict[str, dict]:
    """Zwraca metryki per symbol."""
    syms = set(t.symbol for t in trades)
    return {
        sym: calc_metrics([t for t in trades if t.symbol == sym],
                           initial_equity, label=sym)
        for sym in sorted(syms)
    }


def equity_series(trades: List[ClosedTrade],
                  initial_equity: float = 10_000.0) -> pd.Series:
    """Zwraca equity curve jako Series z indeksem exit_ts."""
    if not trades:
        return pd.Series(dtype=float)
    df = _to_df(trades)
    eq = initial_equity + df["pnl_price"].cumsum()
    eq.index = df["exit_ts"]
    return eq

