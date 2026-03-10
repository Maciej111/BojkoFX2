"""
Multi-Symbol Grid Backtest — M60 (native H1) data
==================================================
Uses native H1 bars downloaded to data/raw_dl_fx/download/m60/
Runs the same BOS+HTF strategy grid across all 14 FX pairs.

LTF  = H1  (native, not resampled from M30)
HTF  = D1 or H4

Outputs:
    data/outputs/m60_grid_results.csv
    reports/M60_GRID_BACKTEST_REPORT.md
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
DATA_DIR_M60 = ROOT / "data" / "raw_dl_fx" / "download" / "m60"
OUT_DIR      = ROOT / "data" / "outputs"
REPORT_DIR   = ROOT / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Per-symbol FX constants ───────────────────────────────────────────────────
SYMBOL_PARAMS = {
    "eurusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "gbpusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "audusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "nzdusd": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "usdchf": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "usdcad": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.5, session_filter=True),
    "usdjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.5, session_filter=False),
    "gbpjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "eurjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "audjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "cadjpy": dict(pip=0.01,   min_risk_pips=30, commission_pips=0.7, session_filter=False),
    "gbpchf": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.7, session_filter=True),
    "eurgbp": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.7, session_filter=True),
    "eurchf": dict(pip=0.0001, min_risk_pips=3,  commission_pips=0.7, session_filter=True),
}

ALL_SYMBOLS = list(SYMBOL_PARAMS.keys())


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["open", "high", "low", "close"]].dropna()


def load_m60_bars(symbol: str) -> pd.DataFrame:
    """Load native M60/H1 bid+ask bars, remove flat bars."""
    bid_file = DATA_DIR_M60 / f"{symbol}_m60_bid_2021_2024.csv"
    ask_file = DATA_DIR_M60 / f"{symbol}_m60_ask_2021_2024.csv"
    if not bid_file.exists() or not ask_file.exists():
        raise FileNotFoundError(f"Missing M60 data for {symbol}: {bid_file} / {ask_file}")
    bid = _read_csv(bid_file)
    ask = _read_csv(ask_file)
    idx = bid.index.intersection(ask.index)
    df = pd.DataFrame(index=idx)
    for c in ["open", "high", "low", "close"]:
        df[f"{c}_bid"] = bid.loc[idx, c].values
        df[f"{c}_ask"] = ask.loc[idx, c].values
    df = df.dropna()
    df = df[(df["high_bid"] - df["low_bid"]) > 0].copy()
    return df


def build_htf(ltf: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open_bid": "first", "high_bid": "max", "low_bid": "min", "close_bid": "last",
        "open_ask": "first", "high_ask": "max", "low_ask": "min", "close_ask": "last",
    }
    return ltf.resample(rule).agg(agg).dropna()


# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h = df["high_bid"].values
    l = df["low_bid"].values
    c = df["close_bid"].values
    n = len(h)
    tr = np.empty(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
    return pd.Series(tr, index=df.index).rolling(period).mean()


def build_pivot_arrays(df: pd.DataFrame, lookback: int, confirmation: int = 1):
    n = len(df)
    h = df["high_bid"].values.astype(np.float64)
    l = df["low_bid"].values.astype(np.float64)

    w = 2 * lookback + 1
    h_pad = np.pad(h, (lookback, lookback), mode='edge')
    l_pad = np.pad(l, (lookback, lookback), mode='edge')
    shape   = (n, w)
    strides = (h_pad.strides[0], h_pad.strides[0])
    h_win = np.lib.stride_tricks.as_strided(h_pad, shape=shape, strides=strides)
    l_win = np.lib.stride_tricks.as_strided(l_pad, shape=shape, strides=strides)

    raw_ph = h == h_win.max(axis=1)
    raw_pl = l == l_win.min(axis=1)
    raw_ph[:lookback] = False;  raw_ph[n-lookback:] = False
    raw_pl[:lookback] = False;  raw_pl[n-lookback:] = False

    conf_ph = np.zeros(n, bool)
    conf_pl = np.zeros(n, bool)
    if confirmation > 0:
        conf_ph[confirmation:] = raw_ph[:-confirmation]
        conf_pl[confirmation:] = raw_pl[:-confirmation]
    else:
        conf_ph[:] = raw_ph
        conf_pl[:] = raw_pl

    ph_lv = np.full(n, np.nan)
    pl_lv = np.full(n, np.nan)
    src_ph = np.clip(np.arange(n) - (confirmation if confirmation > 0 else 0), 0, n-1)
    ph_lv[conf_ph] = h[src_ph[conf_ph]]
    pl_lv[conf_pl] = l[src_ph[conf_pl]]
    return ph_lv, pl_lv, conf_ph, conf_pl


# ══════════════════════════════════════════════════════════════════════════════
# HTF BIAS
# ══════════════════════════════════════════════════════════════════════════════

def get_htf_bias_at(ltf_time, htf_df, htf_ph_lv, htf_pl_lv,
                    htf_ph_mask, htf_pl_mask, pivot_count=4) -> str:
    pos = htf_df.index.searchsorted(ltf_time, side="right") - 1
    if pos < 1:
        return "NEUTRAL"
    last_close = htf_df["close_bid"].iloc[pos]
    ph_p, pl_p = [], []
    for j in range(pos, -1, -1):
        if htf_ph_mask[j] and not np.isnan(htf_ph_lv[j]):
            ph_p.append(htf_ph_lv[j])
        if htf_pl_mask[j] and not np.isnan(htf_pl_lv[j]):
            pl_p.append(htf_pl_lv[j])
        if len(ph_p) >= pivot_count and len(pl_p) >= pivot_count:
            break
    if len(ph_p) < 2 or len(pl_p) < 2:
        return "NEUTRAL"
    if last_close > ph_p[0]:
        return "BULL"
    if last_close < pl_p[0]:
        return "BEAR"
    hh = ph_p[0] > ph_p[1]; hl = pl_p[0] > pl_p[1]
    ll = pl_p[0] < pl_p[1]; lh = ph_p[0] < ph_p[1]
    if hh and hl:
        return "BULL"
    if ll and lh:
        return "BEAR"
    return "NEUTRAL"


def _last_pv(bar_i, pv_lv, pv_mask, max_lb=100):
    stop = max(0, bar_i - max_lb)
    for j in range(bar_i - 1, stop - 1, -1):
        if pv_mask[j] and not np.isnan(pv_lv[j]):
            return pv_lv[j]
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG & OBJECTS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    htf: str = "1d"
    pivot_lookback_ltf: int = 3
    pivot_lookback_htf: int = 5
    confirmation_bars: int = 1
    entry_offset_atr_mult: float = 0.3
    pullback_max_bars: int = 40
    sl_buffer_atr_mult: float = 0.1
    risk_reward: float = 2.5
    atr_period: int = 14
    htf_pivot_count: int = 4
    session_filter: bool = True
    session_start_h: int = 7
    session_end_h: int = 21
    commission: float = 0.00005
    min_risk: float = 0.0003
    risk_pct: float = 0.01
    initial_balance: float = 10_000.0
    train_start: str = "2021-01-01"
    train_end: str = "2022-12-31"
    oos_start: str = "2023-01-01"
    oos_end: str = "2024-12-31"


@dataclass
class Trade:
    direction: str
    entry_price: float
    sl: float
    tp: float
    risk_dist: float
    entry_idx: int
    exit_idx: int = -1
    exit_price: float = 0.0
    exit_reason: str = ""
    R: float = 0.0


@dataclass
class _Setup:
    direction: str
    entry_price: float
    expiry_idx: int
    bos_level: float


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest(ltf_full: pd.DataFrame, cfg: Config,
                 period_start: str, period_end: str) -> Tuple[List[Trade], pd.Series]:
    if ((ltf_full.index >= period_start) & (ltf_full.index <= period_end)).sum() < 50:
        return [], pd.Series(dtype=float)

    htf_full = build_htf(ltf_full, cfg.htf)
    atr_vals = calc_atr(ltf_full, cfg.atr_period).values

    ltf_ph_lv, ltf_pl_lv, ltf_ph_mask, ltf_pl_mask = build_pivot_arrays(
        ltf_full, cfg.pivot_lookback_ltf, cfg.confirmation_bars)
    htf_ph_lv, htf_pl_lv, htf_ph_mask, htf_pl_mask = build_pivot_arrays(
        htf_full, cfg.pivot_lookback_htf, cfg.confirmation_bars)

    idx       = ltf_full.index
    close_bid = ltf_full["close_bid"].values
    high_bid  = ltf_full["high_bid"].values
    low_bid   = ltf_full["low_bid"].values
    high_ask  = ltf_full["high_ask"].values
    low_ask   = ltf_full["low_ask"].values

    start_i = max(idx.searchsorted(period_start, side="left"), 200)
    end_i   = idx.searchsorted(period_end, side="right")

    trades: List[Trade] = []
    equity = cfg.initial_balance
    eq_dict = {}
    active_setup: Optional[_Setup] = None
    open_trade: Optional[Trade] = None

    for i in range(start_i, end_i):
        t   = idx[i]
        atr = atr_vals[i]
        if np.isnan(atr) or atr <= 0:
            eq_dict[t] = equity
            continue

        # ── Exit check ────────────────────────────────────────────────────────
        if open_trade is not None:
            tr = open_trade
            if tr.direction == "LONG":
                sl_hit = low_bid[i]  <= tr.sl
                tp_hit = high_bid[i] >= tr.tp
            else:
                sl_hit = high_ask[i] >= tr.sl
                tp_hit = low_ask[i]  <= tr.tp
            if sl_hit and tp_hit:
                sl_hit, tp_hit = True, False
            if sl_hit or tp_hit:
                ep = tr.sl if sl_hit else tr.tp
                if sl_hit:
                    if tr.direction == "LONG":
                        ep = max(min(ep, high_bid[i]), low_bid[i]) - cfg.commission
                    else:
                        ep = max(min(ep, high_ask[i]), low_ask[i]) + cfg.commission
                else:
                    if tr.direction == "LONG":
                        ep = max(min(ep, high_bid[i]), low_bid[i]) - cfg.commission
                    else:
                        ep = max(min(ep, high_ask[i]), low_ask[i]) + cfg.commission
                reason = "SL" if sl_hit else "TP"
                tr.R = ((ep - tr.entry_price) / tr.risk_dist if tr.direction == "LONG"
                        else (tr.entry_price - ep) / tr.risk_dist)
                tr.exit_price = ep; tr.exit_reason = reason; tr.exit_idx = i
                equity *= (1.0 + tr.R * cfg.risk_pct)
                trades.append(tr)
                open_trade = None

        eq_dict[t] = equity
        if open_trade is not None:
            continue

        # ── Fill check ────────────────────────────────────────────────────────
        if active_setup is not None:
            s = active_setup
            if i > s.expiry_idx:
                active_setup = None
            else:
                filled = (low_ask[i] <= s.entry_price <= high_ask[i] if s.direction == "LONG"
                          else low_bid[i] <= s.entry_price <= high_bid[i])
                if filled:
                    fill_p = (s.entry_price + cfg.commission if s.direction == "LONG"
                              else s.entry_price - cfg.commission)
                    buf = cfg.sl_buffer_atr_mult * atr
                    if s.direction == "LONG":
                        lv = _last_pv(i, ltf_pl_lv, ltf_pl_mask)
                        sl = (lv - buf) if lv else (close_bid[i] - 2*atr)
                        sl = max(sl, close_bid[i] - 5*atr)
                    else:
                        lv = _last_pv(i, ltf_ph_lv, ltf_ph_mask)
                        sl = (lv + buf) if lv else (close_bid[i] + 2*atr)
                        sl = min(sl, close_bid[i] + 5*atr)
                    risk_dist = abs(fill_p - sl)
                    if risk_dist < cfg.min_risk:
                        active_setup = None
                        continue
                    tp = (fill_p + risk_dist * cfg.risk_reward if s.direction == "LONG"
                          else fill_p - risk_dist * cfg.risk_reward)
                    open_trade = Trade(s.direction, fill_p, sl, tp, risk_dist, i)
                    active_setup = None
                    continue

        if active_setup is not None or open_trade is not None:
            continue

        # ── Session filter ────────────────────────────────────────────────────
        if cfg.session_filter and not (cfg.session_start_h <= t.hour < cfg.session_end_h):
            continue

        # ── HTF Bias ──────────────────────────────────────────────────────────
        bias = get_htf_bias_at(t, htf_full, htf_ph_lv, htf_pl_lv,
                               htf_ph_mask, htf_pl_mask, cfg.htf_pivot_count)
        if bias == "NEUTRAL":
            continue

        # ── BOS ───────────────────────────────────────────────────────────────
        last_ph = _last_pv(i, ltf_ph_lv, ltf_ph_mask)
        last_pl = _last_pv(i, ltf_pl_lv, ltf_pl_mask)
        bos_dir = bos_level = None
        if bias == "BULL" and last_ph and close_bid[i] > last_ph:
            bos_dir, bos_level = "LONG", last_ph
        elif bias == "BEAR" and last_pl and close_bid[i] < last_pl:
            bos_dir, bos_level = "SHORT", last_pl
        if bos_dir is None:
            continue

        # ── Create Setup ──────────────────────────────────────────────────────
        offset = cfg.entry_offset_atr_mult * atr
        entry = bos_level + offset if bos_dir == "LONG" else bos_level - offset
        active_setup = _Setup(bos_dir, entry, i + cfg.pullback_max_bars, bos_level)

    return trades, pd.Series(eq_dict)


# ══════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════

def calc_metrics(trades: List[Trade], eq: pd.Series, bal: float = 10_000.0) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": 0.0, "exp_R": 0.0,
                "profit_factor": 0.0, "max_dd_pct": 0.0, "return_pct": 0.0}
    Rs   = [t.R for t in trades]
    wins = [r for r in Rs if r > 0]
    loss = [r for r in Rs if r <= 0]
    pf   = sum(wins) / abs(sum(loss)) if loss else float("inf")
    if not eq.empty:
        peak  = np.maximum.accumulate(eq.values)
        dd    = np.where(peak > 0, (peak - eq.values) / peak * 100, 0)
        maxdd = float(dd.max())
        ret   = float((eq.iloc[-1] / bal - 1) * 100)
    else:
        maxdd = ret = 0.0
    return {"n_trades": len(Rs), "win_rate": round(len(wins)/len(Rs)*100, 1),
            "exp_R": round(float(np.mean(Rs)), 4), "profit_factor": round(pf, 3),
            "max_dd_pct": round(maxdd, 1), "return_pct": round(ret, 1)}


# ══════════════════════════════════════════════════════════════════════════════
# GRID DEFINITION
# ══════════════════════════════════════════════════════════════════════════════

GRID = {
    "htf":                   ["1D", "4h"],
    "risk_reward":           [1.5, 2.0, 2.5, 3.0],
    "entry_offset_atr_mult": [0.0, 0.3],
    "sl_buffer_atr_mult":    [0.1, 0.3, 0.5],
    "pullback_max_bars":     [15, 30, 50],
}

BASE_CFG = dict(
    pivot_lookback_ltf=3, pivot_lookback_htf=5, confirmation_bars=1,
    atr_period=14, htf_pivot_count=4,
    risk_pct=0.01, initial_balance=10_000.0,
    train_start="2021-01-01", train_end="2022-12-31",
    oos_start="2023-01-01",   oos_end="2024-12-31",
)
# 2 * 4 * 2 * 3 * 3 = 144 combinations per symbol


def run_grid_symbol(symbol: str, ltf_h1: pd.DataFrame) -> pd.DataFrame:
    sp = SYMBOL_PARAMS[symbol]
    pip            = sp["pip"]
    commission     = sp["commission_pips"] * pip
    min_risk       = sp["min_risk_pips"] * pip
    session_filter = sp["session_filter"]

    keys   = list(GRID.keys())
    combos = list(itertools.product(*[GRID[k] for k in keys]))
    rows   = []

    for combo in combos:
        params = dict(zip(keys, combo))
        cfg = Config(**params, **BASE_CFG,
                     commission=commission, min_risk=min_risk,
                     session_filter=session_filter,
                     session_start_h=7, session_end_h=21)

        tr_t, tr_eq   = run_backtest(ltf_h1, cfg, cfg.train_start, cfg.train_end)
        oos_t, oos_eq = run_backtest(ltf_h1, cfg, cfg.oos_start,   cfg.oos_end)
        tr_m  = calc_metrics(tr_t,  tr_eq,  cfg.initial_balance)
        oos_m = calc_metrics(oos_t, oos_eq, cfg.initial_balance)

        rows.append({
            "symbol": symbol.upper(), **params,
            "train_n":    tr_m["n_trades"],   "train_wr":  tr_m["win_rate"],
            "train_expR": tr_m["exp_R"],       "train_pf":  tr_m["profit_factor"],
            "train_dd":   tr_m["max_dd_pct"], "train_ret": tr_m["return_pct"],
            "oos_n":      oos_m["n_trades"],  "oos_wr":    oos_m["win_rate"],
            "oos_expR":   oos_m["exp_R"],      "oos_pf":    oos_m["profit_factor"],
            "oos_dd":     oos_m["max_dd_pct"],"oos_ret":   oos_m["return_pct"],
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(all_results: pd.DataFrame) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("# M60 (Native H1) Grid Backtest Report — All 14 FX Pairs")
    L.append("")
    L.append(f"> Generated: {now}")
    L.append(f"> LTF: **H1 (native M60 from Dukascopy)** | HTF: D1 or H4")
    L.append(f"> TRAIN: 2021–2022 | OOS: 2023–2024")
    L.append(f"> Risk: 1% equity/trade | Session: EUR/GBP/CHF 07–21 UTC, JPY=all")
    L.append(f"> Grid: {len(all_results[all_results['symbol']==all_results['symbol'].iloc[0]])} configs/symbol × "
             f"{all_results['symbol'].nunique()} symbols = {len(all_results)} total")
    L.append("")
    L.append("---")
    L.append("")

    hdr = "| HTF | RR | off | buf | pmb | n | WR | ExpR | PF | MaxDD | Ret |"
    sep = "|-----|----|----|-----|-----|---|----|----|----|----|-----|"

    def frow(r):
        return (f"| {r['htf']} | {r['risk_reward']} | "
                f"{r['entry_offset_atr_mult']} | {r['sl_buffer_atr_mult']} | "
                f"{int(r['pullback_max_bars'])} | {int(r['oos_n'])} | "
                f"{r['oos_wr']}% | {r['oos_expR']:+.4f}R | "
                f"{r['oos_pf']:.3f} | {r['oos_dd']:.1f}% | {r['oos_ret']:+.1f}% |")

    # ── Executive summary table ───────────────────────────────────────────────
    L.append("## Executive Summary — Best Config per Symbol (OOS)\n")
    L.append("| Symbol | HTF | RR | off | buf | pmb | n | WR | ExpR | PF | MaxDD | Ret |")
    L.append("|--------|-----|----|----|-----|-----|---|----|----|----|----|-----|")

    symbols = sorted(all_results["symbol"].unique())
    best_rows = []
    for sym in symbols:
        df = all_results[all_results["symbol"] == sym]
        best = df.sort_values("oos_expR", ascending=False).iloc[0]
        best_rows.append(best)
        L.append(f"| {sym} | {best['htf']} | {best['risk_reward']} | "
                 f"{best['entry_offset_atr_mult']} | {best['sl_buffer_atr_mult']} | "
                 f"{int(best['pullback_max_bars'])} | {int(best['oos_n'])} | "
                 f"{best['oos_wr']}% | {best['oos_expR']:+.4f}R | "
                 f"{best['oos_pf']:.3f} | {best['oos_dd']:.1f}% | {best['oos_ret']:+.1f}% |")
    L.append("")

    # Count passing
    passing_all = all_results[
        (all_results["oos_expR"] > 0.20) &
        (all_results["oos_pf"] > 1.15) &
        (all_results["oos_dd"] < 25) &
        (all_results["oos_n"] >= 20)
    ]
    L.append(f"> Passing configs (ExpR>0.20R, PF>1.15, DD<25%, n≥20): "
             f"**{len(passing_all)}** / {len(all_results)}")
    L.append("")
    L.append("---")
    L.append("")

    # ── Per-symbol detail ─────────────────────────────────────────────────────
    for sym in symbols:
        df = all_results[all_results["symbol"] == sym]
        df_sorted = df.sort_values("oos_expR", ascending=False)
        passing = df[
            (df["oos_expR"] > 0.20) & (df["oos_pf"] > 1.15) &
            (df["oos_dd"] < 25) & (df["oos_n"] >= 20)
        ]

        L.append(f"## {sym}")
        L.append("")
        L.append(f"- Configs tested: **{len(df)}** | Passing: **{len(passing)}**")
        L.append(f"- Best OOS ExpR: **{df['oos_expR'].max():+.4f}R** | "
                 f"Worst: **{df['oos_expR'].min():+.4f}R**")
        L.append(f"- Avg OOS ExpR: **{df['oos_expR'].mean():+.4f}R**")
        L.append("")

        L.append(f"### Top 10 {sym} configs (OOS ExpR)")
        L.append("")
        L += [hdr, sep]
        for _, r in df_sorted.head(10).iterrows():
            L.append(frow(r))
        L.append("")

        if not passing.empty:
            L.append(f"### ✅ Passing configs {sym} ({len(passing)})")
            L.append("")
            L += [hdr, sep]
            for _, r in passing.sort_values("oos_expR", ascending=False).iterrows():
                L.append(frow(r))
            L.append("")

        best_r = df_sorted.iloc[0]
        L.append(f"> Best TRAIN: n={int(best_r['train_n'])} "
                 f"ExpR={best_r['train_expR']:+.4f}R PF={best_r['train_pf']:.3f} "
                 f"Ret={best_r['train_ret']:+.1f}% DD={best_r['train_dd']:.1f}%")
        L.append("")
        L.append("---")
        L.append("")

    # ── Cross-symbol at reference config ─────────────────────────────────────
    L.append("## Cross-Symbol Comparison — Reference Config (D1 HTF, RR=2.5, off=0.3, buf=0.1, pmb=30)")
    L.append("")
    L.append("| Symbol | n | WR | ExpR | PF | MaxDD | Ret |")
    L.append("|--------|---|----|----|----|----|-----|")
    for sym in symbols:
        df = all_results[all_results["symbol"] == sym]
        row = df[
            (df["htf"] == "1D") & (df["risk_reward"] == 2.5) &
            (df["entry_offset_atr_mult"] == 0.3) & (df["sl_buffer_atr_mult"] == 0.1) &
            (df["pullback_max_bars"] == 30)
        ]
        if not row.empty:
            r = row.iloc[0]
            L.append(f"| {sym} | {int(r['oos_n'])} | {r['oos_wr']}% | "
                     f"{r['oos_expR']:+.4f}R | {r['oos_pf']:.3f} | "
                     f"{r['oos_dd']:.1f}% | {r['oos_ret']:+.1f}% |")
    L.append("")
    L.append("---")
    L.append("")

    # ── Parameter impact ─────────────────────────────────────────────────────
    L.append("## Parameter Impact (avg OOS ExpR across all symbols)")
    L.append("")
    for param in ["htf", "risk_reward", "entry_offset_atr_mult",
                  "sl_buffer_atr_mult", "pullback_max_bars"]:
        L.append(f"### `{param}`")
        L.append("")
        L.append("| Value | Avg ExpR | Best Symbol |")
        L.append("|-------|----------|-------------|")
        vals = sorted(all_results[param].unique(), key=str)
        for v in vals:
            sub = all_results[all_results[param] == v]
            avg = sub["oos_expR"].mean()
            best_sym = sub.groupby("symbol")["oos_expR"].mean().idxmax()
            L.append(f"| {v} | {avg:+.4f}R | {best_sym} |")
        L.append("")

    # ── Recommended symbols ───────────────────────────────────────────────────
    L.append("---")
    L.append("")
    L.append("## Recommended Symbols for Live Trading (M60/H1)")
    L.append("")
    per_sym_best = []
    for sym in symbols:
        df = all_results[all_results["symbol"] == sym]
        best = df.sort_values("oos_expR", ascending=False).iloc[0]
        per_sym_best.append((sym, best["oos_expR"], best["oos_pf"], best["oos_dd"], int(best["oos_n"])))

    per_sym_best.sort(key=lambda x: x[1], reverse=True)
    L.append("| Rank | Symbol | Best ExpR | PF | MaxDD | Trades | Verdict |")
    L.append("|------|--------|-----------|----|----|--------|---------|")
    for rank, (sym, expr, pf, dd, n) in enumerate(per_sym_best, 1):
        if expr > 0.25 and pf > 1.2 and dd < 20 and n >= 30:
            verdict = "✅ RECOMMENDED"
        elif expr > 0.15 and pf > 1.1 and dd < 25:
            verdict = "⚠️ MARGINAL"
        else:
            verdict = "❌ AVOID"
        L.append(f"| {rank} | {sym} | {expr:+.4f}R | {pf:.3f} | {dd:.1f}% | {n} | {verdict} |")

    L.append("")
    L.append("---")
    L.append("")
    L.append("## Acceptance Criteria")
    L.append("")
    L.append("| Metric | Min | Target |")
    L.append("|--------|-----|--------|")
    L.append("| ExpR OOS | >+0.15R | >+0.25R |")
    L.append("| Win Rate | >38% | >44% |")
    L.append("| Profit Factor | >1.10 | >1.50 |")
    L.append("| Max DD | <25% | <15% |")
    L.append("| Trades/2yr OOS | >40 | >80 |")
    L.append("")
    L.append(f"*Report generated: {now}*")
    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("M60 Grid Backtest — All 14 FX Pairs (Native H1 from Dukascopy)")
    print("=" * 65)

    all_dfs = []
    n_grid = len(list(itertools.product(*GRID.values())))
    print(f"Grid size per symbol: {n_grid} configs")
    print(f"Symbols: {len(ALL_SYMBOLS)}")
    print(f"Total runs: {n_grid * len(ALL_SYMBOLS)}")
    print()

    for sym in ALL_SYMBOLS:
        print(f"[{sym.upper()}] Loading M60 bars...", flush=True)
        try:
            ltf_h1 = load_m60_bars(sym)
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
            continue
        print(f"  H1 bars: {len(ltf_h1):,}  ({ltf_h1.index.min().date()} to {ltf_h1.index.max().date()})")

        print(f"[{sym.upper()}] Running {n_grid} configs...", flush=True)
        df = run_grid_symbol(sym, ltf_h1)
        all_dfs.append(df)

        best = df.sort_values("oos_expR", ascending=False).iloc[0]
        passing = df[(df["oos_expR"] > 0.20) & (df["oos_pf"] > 1.15) &
                     (df["oos_dd"] < 25) & (df["oos_n"] >= 20)]
        print(f"  Best OOS: HTF={best['htf']} RR={best['risk_reward']} "
              f"off={best['entry_offset_atr_mult']} buf={best['sl_buffer_atr_mult']} "
              f"pmb={int(best['pullback_max_bars'])} -> "
              f"ExpR={best['oos_expR']:+.4f}R WR={best['oos_wr']}% "
              f"PF={best['oos_pf']:.3f} DD={best['oos_dd']:.1f}%")
        print(f"  Passing configs: {len(passing)}/{n_grid}")
        print()

    if not all_dfs:
        print("No results — check data files.")
        return

    all_results = pd.concat(all_dfs, ignore_index=True)

    out_path = OUT_DIR / "m60_grid_results.csv"
    all_results.to_csv(out_path, index=False)
    print(f"CSV saved: {out_path}")

    print("Generating report...", flush=True)
    md = generate_report(all_results)
    rp = REPORT_DIR / "M60_GRID_BACKTEST_REPORT.md"
    rp.write_text(md, encoding="utf-8")
    print(f"Report: {rp}")

    # ── Final console summary ─────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("FINAL SUMMARY — Best config per symbol (OOS)")
    print("=" * 65)
    print(f"{'Symbol':<8} {'HTF':<4} {'RR':<5} {'n':>4} {'WR':>6} "
          f"{'ExpR':>8} {'PF':>6} {'DD':>6} {'Ret':>7}")
    print("-" * 65)
    symbols = sorted(all_results["symbol"].unique())
    for sym in symbols:
        df = all_results[all_results["symbol"] == sym]
        best = df.sort_values("oos_expR", ascending=False).iloc[0]
        flag = "*" if best["oos_expR"] > 0.20 and best["oos_pf"] > 1.15 else " "
        print(f"{sym:<8} {str(best['htf']):<4} {best['risk_reward']:<5} "
              f"{int(best['oos_n']):>4} {best['oos_wr']:>5.1f}% "
              f"{best['oos_expR']:>+8.4f}R {best['oos_pf']:>6.3f} "
              f"{best['oos_dd']:>5.1f}% {best['oos_ret']:>+6.1f}%  {flag}")
    print()
    print("Done.")


if __name__ == "__main__":
    main()






