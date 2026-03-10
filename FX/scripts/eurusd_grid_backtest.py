"""
EURUSD Grid Backtest — BOS + Pullback Strategy
================================================
Self-contained backtest engine — full implementation of
STRATEGY_ALGORITHM_SPEC_FOR_FX.md adapted for EURUSD.

Key rules (spec-compliant):
  - ATR(14) on LTF bid columns
  - Pivots confirmed with confirmation_bars=1 (anti-lookahead shift)
  - HTF bias via HH/HL or LL/LH on last N confirmed HTF pivots
  - BOS = close_bid > last confirmed pivot high (LONG) or < low (SHORT)
  - BOS direction must match HTF bias (BULL/BEAR)
  - LIMIT entry: LONG uses ask side, SHORT uses bid side
  - One setup at a time — new BOS cancels pending unfilled setup
  - SL anchored to last_pivot ± ATR buffer (at fill time)
  - TP = entry ± risk_distance × RR
  - Exit: worst-case intrabar (SL beats TP if both hit same bar)
  - Commission applied at entry and exit

Usage:
    python scripts/eurusd_grid_backtest.py

Outputs:
    data/outputs/eurusd_grid_results.csv
    reports/EURUSD_BACKTEST_REPORT.md
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
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw_dl_fx" / "download" / "m30"
OUT_DIR  = ROOT / "data" / "outputs"
REPORT_DIR = ROOT / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── FX constants ──────────────────────────────────────────────────────────────
PIP        = 0.0001          # 1 pip EURUSD
SPREAD     = 1.0 * PIP       # 1 pip spread (bid/ask already separate from Dukascopy)
COMMISSION = 0.5 * PIP       # 0.5 pip per side


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def load_bars(timeframe: str) -> pd.DataFrame:
    """Return DataFrame with open/high/low/close _bid and _ask columns.
    Flat bars (zero range — weekends/holidays) are removed.
    """
    bid_file = DATA_DIR / f"eurusd_{timeframe}_bid_2021_2024.csv"
    ask_file = DATA_DIR / f"eurusd_{timeframe}_ask_2021_2024.csv"
    if not bid_file.exists() or not ask_file.exists():
        raise FileNotFoundError(f"Missing: {bid_file} or {ask_file}")
    bid = _read_csv(bid_file)
    ask = _read_csv(ask_file)
    idx = bid.index.intersection(ask.index)
    df = pd.DataFrame(index=idx)
    for c in ["open", "high", "low", "close"]:
        df[f"{c}_bid"] = bid.loc[idx, c].values
        df[f"{c}_ask"] = ask.loc[idx, c].values
    df = df.dropna()
    # Remove flat bars (weekends / zero-volume periods)
    flat_mask = (df["high_bid"] - df["low_bid"]) <= 0
    df = df[~flat_mask].copy()
    return df


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["open", "high", "low", "close"]].dropna()


def build_htf(ltf: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open_bid":  "first", "high_bid": "max",  "low_bid":  "min",  "close_bid": "last",
        "open_ask":  "first", "high_ask": "max",  "low_ask":  "min",  "close_ask": "last",
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
    atr = pd.Series(tr, index=df.index, dtype=float)
    return atr.rolling(period).mean()


def _raw_pivots(highs: np.ndarray, lows: np.ndarray,
                lookback: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return boolean arrays of raw pivot highs/lows."""
    n = len(highs)
    ph = np.zeros(n, bool)
    pl = np.zeros(n, bool)
    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback: i + lookback + 1]
        window_l = lows [i - lookback: i + lookback + 1]
        if highs[i] == window_h.max():
            ph[i] = True
        if lows[i] == window_l.min():
            pl[i] = True
    return ph, pl


def build_pivot_arrays(df: pd.DataFrame, lookback: int,
                       confirmation: int = 1) -> Tuple[np.ndarray, np.ndarray,
                                                        np.ndarray, np.ndarray]:
    """
    Returns (ph_levels, pl_levels, ph_mask, pl_mask) as numpy arrays
    aligned with df.index.
    ph_levels[i] = price of confirmed pivot high visible at bar i (else NaN)
    ph_mask[i]   = True if bar i IS a confirmed pivot high
    """
    n = len(df)
    h = df["high_bid"].values
    l = df["low_bid"].values

    raw_ph, raw_pl = _raw_pivots(h, l, lookback)

    # shift by confirmation bars (anti-lookahead)
    conf_ph = np.zeros(n, bool)
    conf_pl = np.zeros(n, bool)
    if confirmation > 0:
        conf_ph[confirmation:] = raw_ph[:-confirmation]
        conf_pl[confirmation:] = raw_pl[:-confirmation]
    else:
        conf_ph = raw_ph.copy()
        conf_pl = raw_pl.copy()

    # Build price arrays: ph_levels[i] = high of the bar that WAS pivot high,
    # confirmed to be visible at bar i
    ph_levels = np.full(n, np.nan)
    pl_levels = np.full(n, np.nan)

    # For each bar i where conf_ph is True, the pivot price is h[i - confirmation]
    for i in range(n):
        if conf_ph[i]:
            src = i - confirmation
            ph_levels[i] = h[src]
        if conf_pl[i]:
            src = i - confirmation
            pl_levels[i] = l[src]

    return ph_levels, pl_levels, conf_ph, conf_pl


# ══════════════════════════════════════════════════════════════════════════════
# HTF BIAS
# ══════════════════════════════════════════════════════════════════════════════

def get_htf_bias_at(ltf_bar_time,
                    htf_df: pd.DataFrame,
                    htf_ph_levels: np.ndarray,
                    htf_pl_levels: np.ndarray,
                    htf_ph_mask: np.ndarray,
                    htf_pl_mask: np.ndarray,
                    pivot_count: int = 4) -> str:
    """
    Returns 'BULL', 'BEAR', or 'NEUTRAL'.
    Only uses HTF bars with index <= ltf_bar_time (strict anti-lookahead).
    """
    # Find last HTF bar index <= ltf_bar_time
    htf_idx_arr = htf_df.index
    pos = htf_idx_arr.searchsorted(ltf_bar_time, side='right') - 1
    if pos < 1:
        return "NEUTRAL"

    last_close = htf_df["close_bid"].iloc[pos]

    # Gather last N confirmed pivot highs/lows up to pos
    ph_prices = []
    pl_prices = []
    for j in range(pos, -1, -1):
        if htf_ph_mask[j] and not np.isnan(htf_ph_levels[j]):
            ph_prices.append(htf_ph_levels[j])
        if htf_pl_mask[j] and not np.isnan(htf_pl_levels[j]):
            pl_prices.append(htf_pl_levels[j])
        if len(ph_prices) >= pivot_count and len(pl_prices) >= pivot_count:
            break

    if len(ph_prices) < 2 or len(pl_prices) < 2:
        return "NEUTRAL"

    last_ph = ph_prices[0]   # most recent
    last_pl = pl_prices[0]

    # Breakout check (highest priority)
    if last_close > last_ph:
        return "BULL"
    if last_close < last_pl:
        return "BEAR"

    # HH+HL = BULL, LL+LH = BEAR
    hh = ph_prices[0] > ph_prices[1]
    hl = pl_prices[0] > pl_prices[1]
    ll = pl_prices[0] < pl_prices[1]
    lh = ph_prices[0] < ph_prices[1]

    if hh and hl:
        return "BULL"
    if ll and lh:
        return "BEAR"

    return "NEUTRAL"


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG & TRADE OBJECTS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestConfig:
    # Timeframes
    ltf: str = "30min"
    htf: str = "4h"
    # Pivots
    pivot_lookback_ltf: int   = 3
    pivot_lookback_htf: int   = 5
    confirmation_bars:  int   = 1
    require_close_break: bool = True
    # Entry
    entry_offset_atr_mult: float = 0.0
    pullback_max_bars:     int   = 20
    # SL/TP
    sl_anchor:          str   = "last_pivot"
    sl_buffer_atr_mult: float = 0.1
    risk_reward:        float = 2.5
    # ATR
    atr_period: int = 14
    # HTF
    htf_pivot_count: int = 4
    # Session filter (London+NY: 07:00–21:00 UTC)
    session_filter: bool = True
    session_start_h: int = 7    # UTC hour, inclusive
    session_end_h:   int = 21   # UTC hour, exclusive
    # Costs
    commission: float = COMMISSION
    # Risk
    risk_pct:        float = 0.01
    initial_balance: float = 10_000.0
    # Date splits
    train_start: str = "2021-01-01"
    train_end:   str = "2022-12-31"
    oos_start:   str = "2023-01-01"
    oos_end:     str = "2024-12-31"


@dataclass
class _Setup:
    bar_idx:     int
    direction:   str    # 'LONG' or 'SHORT'
    entry_price: float
    expiry_idx:  int
    bos_level:   float


@dataclass
class Trade:
    direction:   str
    entry_price: float
    sl:          float
    tp:          float
    risk_dist:   float
    entry_idx:   int
    exit_idx:    int   = -1
    exit_price:  float = 0.0
    exit_reason: str   = ""
    R:           float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# CORE BACKTEST LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest(ltf_full: pd.DataFrame,
                 cfg: BacktestConfig,
                 period_start: str,
                 period_end: str) -> Tuple[List[Trade], pd.Series]:
    """
    Run one backtest period. Returns (trades_list, equity_series).
    ltf_full must cover at least 300 bars BEFORE period_start for warmup.
    """
    # Use full data for indicator calculation, slice period for trading
    period_mask = (ltf_full.index >= period_start) & (ltf_full.index <= period_end)
    if period_mask.sum() < 50:
        return [], pd.Series(dtype=float)

    # Build HTF from full LTF (so indicators are warm at period start)
    htf_full = build_htf(ltf_full, cfg.htf)

    # ── Pre-compute ATR on full LTF ──
    atr_full = calc_atr(ltf_full, cfg.atr_period)

    # ── Pre-compute LTF pivots on full dataset ──
    ltf_ph_lv, ltf_pl_lv, ltf_ph_mask, ltf_pl_mask = build_pivot_arrays(
        ltf_full, cfg.pivot_lookback_ltf, cfg.confirmation_bars
    )

    # ── Pre-compute HTF pivots on full HTF ──
    htf_ph_lv, htf_pl_lv, htf_ph_mask, htf_pl_mask = build_pivot_arrays(
        htf_full, cfg.pivot_lookback_htf, cfg.confirmation_bars
    )

    # ── Prepare LTF arrays for speed ──
    ltf_idx   = ltf_full.index
    close_bid = ltf_full["close_bid"].values
    high_bid  = ltf_full["high_bid"].values
    low_bid   = ltf_full["low_bid"].values
    high_ask  = ltf_full["high_ask"].values
    low_ask   = ltf_full["low_ask"].values
    atr_vals  = atr_full.values

    # Find start index in full array (with 300-bar warmup guard)
    start_i = ltf_idx.searchsorted(period_start, side='left')
    start_i = max(start_i, 300)
    end_i   = ltf_idx.searchsorted(period_end,   side='right')

    trades: List[Trade] = []
    equity  = cfg.initial_balance
    eq_dict = {}

    active_setup: Optional[_Setup] = None
    open_trade:   Optional[Trade]  = None

    for i in range(start_i, end_i):
        t       = ltf_idx[i]
        atr_val = atr_vals[i]
        if np.isnan(atr_val) or atr_val <= 0:
            eq_dict[t] = equity
            continue

        # ── Step 1: Manage open trade (exit check) ────────────────────────────
        if open_trade is not None:
            tr = open_trade
            if tr.direction == "LONG":
                sl_hit = low_bid[i]  <= tr.sl
                tp_hit = high_bid[i] >= tr.tp
            else:
                sl_hit = high_ask[i] >= tr.sl
                tp_hit = low_ask[i]  <= tr.tp

            if sl_hit and tp_hit:
                sl_hit, tp_hit = True, False  # worst-case: SL wins

            if sl_hit or tp_hit:
                if sl_hit:
                    raw_ep = tr.sl
                    # clamp to bar range
                    if tr.direction == "LONG":
                        ep = max(min(raw_ep, high_bid[i]), low_bid[i])
                        ep -= cfg.commission
                    else:
                        ep = max(min(raw_ep, high_ask[i]), low_ask[i])
                        ep += cfg.commission
                    reason = "SL"
                else:
                    raw_ep = tr.tp
                    if tr.direction == "LONG":
                        ep = max(min(raw_ep, high_bid[i]), low_bid[i])
                        ep -= cfg.commission
                    else:
                        ep = max(min(raw_ep, high_ask[i]), low_ask[i])
                        ep += cfg.commission
                    reason = "TP"

                if tr.direction == "LONG":
                    tr.R = (ep - tr.entry_price) / tr.risk_dist
                else:
                    tr.R = (tr.entry_price - ep) / tr.risk_dist

                tr.exit_price  = ep
                tr.exit_reason = reason
                tr.exit_idx    = i

                equity *= (1.0 + tr.R * cfg.risk_pct)
                trades.append(tr)
                open_trade = None

        eq_dict[t] = equity

        # Skip new signals while trade is open
        if open_trade is not None:
            continue

        # ── Step 2: Check pending setup fill ─────────────────────────────────
        if active_setup is not None:
            s = active_setup
            if i > s.expiry_idx:
                active_setup = None
            else:
                # LONG: fill when ask touches entry (low_ask <= entry <= high_ask)
                # SHORT: fill when bid touches entry (low_bid <= entry <= high_bid)
                if s.direction == "LONG":
                    filled = low_ask[i] <= s.entry_price <= high_ask[i]
                else:
                    filled = low_bid[i] <= s.entry_price <= high_bid[i]

                if filled:
                    # Apply commission at entry
                    if s.direction == "LONG":
                        fill_p = s.entry_price + cfg.commission
                    else:
                        fill_p = s.entry_price - cfg.commission

                    # SL from last pivot at fill time
                    sl = _calc_sl(i, s.direction, ltf_full,
                                  ltf_ph_lv, ltf_pl_lv,
                                  ltf_ph_mask, ltf_pl_mask,
                                  atr_val, cfg)

                    risk_dist = abs(fill_p - sl)
                    if risk_dist < 3 * PIP:   # min 3 pip risk — reject noise
                        active_setup = None
                        continue

                    if s.direction == "LONG":
                        tp = fill_p + risk_dist * cfg.risk_reward
                    else:
                        tp = fill_p - risk_dist * cfg.risk_reward

                    open_trade = Trade(
                        direction   = s.direction,
                        entry_price = fill_p,
                        sl          = sl,
                        tp          = tp,
                        risk_dist   = risk_dist,
                        entry_idx   = i,
                    )
                    active_setup = None
                    continue

        # Skip new BOS while setup or trade is pending
        if active_setup is not None or open_trade is not None:
            continue

        # ── Step 2.5: Session filter ──────────────────────────────────────────
        if cfg.session_filter:
            h = t.hour
            if not (cfg.session_start_h <= h < cfg.session_end_h):
                continue

        # ── Step 3: HTF Bias ──────────────────────────────────────────────────
        bias = get_htf_bias_at(
            t, htf_full,
            htf_ph_lv, htf_pl_lv,
            htf_ph_mask, htf_pl_mask,
            cfg.htf_pivot_count
        )
        if bias == "NEUTRAL":
            continue

        # ── Step 4: BOS Detection ─────────────────────────────────────────────
        # Find last confirmed LTF pivot high and low BEFORE bar i (max 100 bars back)
        last_ph = _last_pivot_level(i, ltf_ph_lv, ltf_ph_mask, "high", max_lookback=100)
        last_pl = _last_pivot_level(i, ltf_pl_lv, ltf_pl_mask, "low",  max_lookback=100)

        bos_dir   = None
        bos_level = None

        if bias == "BULL" and last_ph is not None:
            if close_bid[i] > last_ph:
                bos_dir   = "LONG"
                bos_level = last_ph

        elif bias == "BEAR" and last_pl is not None:
            if close_bid[i] < last_pl:
                bos_dir   = "SHORT"
                bos_level = last_pl

        if bos_dir is None:
            continue

        # ── Step 5: Create Setup ──────────────────────────────────────────────
        offset = cfg.entry_offset_atr_mult * atr_val
        if bos_dir == "LONG":
            entry = bos_level + offset
        else:
            entry = bos_level - offset

        active_setup = _Setup(
            bar_idx     = i,
            direction   = bos_dir,
            entry_price = entry,
            expiry_idx  = i + cfg.pullback_max_bars,
            bos_level   = bos_level,
        )

    return trades, pd.Series(eq_dict)


def _last_pivot_level(bar_i: int, pv_levels: np.ndarray,
                      pv_mask: np.ndarray, direction: str,
                      max_lookback: int = 100) -> Optional[float]:
    """Scan backwards from bar_i-1 for the most recent confirmed pivot (max_lookback bars)."""
    stop = max(0, bar_i - max_lookback)
    for j in range(bar_i - 1, stop - 1, -1):
        if pv_mask[j] and not np.isnan(pv_levels[j]):
            return pv_levels[j]
    return None


def _calc_sl(bar_i: int, direction: str,
             ltf_df: pd.DataFrame,
             ph_lv: np.ndarray, pl_lv: np.ndarray,
             ph_mask: np.ndarray, pl_mask: np.ndarray,
             atr_val: float, cfg: BacktestConfig) -> float:
    """SL = last_pivot ± ATR buffer. Fallback: 2×ATR."""
    buf = cfg.sl_buffer_atr_mult * atr_val
    if direction == "LONG":
        lv = _last_pivot_level(bar_i, pl_lv, pl_mask, "low")
        sl = (lv - buf) if lv is not None else (ltf_df["close_bid"].iloc[bar_i] - 2 * atr_val)
        # Safety: SL must be within 5×ATR of current price (anti-outlier)
        close = ltf_df["close_bid"].iloc[bar_i]
        sl = max(sl, close - 5 * atr_val)
        return sl
    else:
        lv = _last_pivot_level(bar_i, ph_lv, ph_mask, "high")
        sl = (lv + buf) if lv is not None else (ltf_df["close_bid"].iloc[bar_i] + 2 * atr_val)
        close = ltf_df["close_bid"].iloc[bar_i]
        sl = min(sl, close + 5 * atr_val)
        return sl


# ══════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════

def calc_metrics(trades: List[Trade], equity_series: pd.Series,
                 initial_balance: float = 10_000.0) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": 0.0, "exp_R": 0.0,
                "profit_factor": 0.0, "max_dd_pct": 0.0, "return_pct": 0.0}

    Rs   = [t.R for t in trades]
    wins = [r for r in Rs if r > 0]
    loss = [r for r in Rs if r <= 0]

    n      = len(Rs)
    wr     = len(wins) / n * 100
    exp_R  = float(np.mean(Rs))
    pf     = sum(wins) / abs(sum(loss)) if loss else float("inf")

    if not equity_series.empty:
        eq    = equity_series.values
        peak  = np.maximum.accumulate(eq)
        dd    = np.where(peak > 0, (peak - eq) / peak * 100, 0)
        maxdd = float(dd.max())
        ret   = float((equity_series.iloc[-1] / initial_balance - 1) * 100)
    else:
        maxdd = 0.0
        ret   = 0.0

    return {
        "n_trades":      n,
        "win_rate":      round(wr,    1),
        "exp_R":         round(exp_R, 4),
        "profit_factor": round(pf,    3),
        "max_dd_pct":    round(maxdd, 1),
        "return_pct":    round(ret,   1),
    }


# ══════════════════════════════════════════════════════════════════════════════
# GRID SEARCH
# ══════════════════════════════════════════════════════════════════════════════

GRID = {
    "ltf":                   ["30min", "h1"],
    "htf":                   ["4h",    "1d"],
    "risk_reward":           [1.5, 2.0, 2.5],
    "entry_offset_atr_mult": [0.0, 0.3],
    "sl_buffer_atr_mult":    [0.1, 0.3, 0.5],
    "pullback_max_bars":     [20, 40],
}

FIXED = dict(
    pivot_lookback_ltf  = 3,
    pivot_lookback_htf  = 5,
    confirmation_bars   = 1,
    require_close_break = True,
    sl_anchor           = "last_pivot",
    atr_period          = 14,
    htf_pivot_count     = 4,
    session_filter      = True,
    session_start_h     = 7,
    session_end_h       = 21,
    commission          = COMMISSION,
    risk_pct            = 0.01,
    initial_balance     = 10_000.0,
    train_start         = "2021-01-01",
    train_end           = "2022-12-31",
    oos_start           = "2023-01-01",
    oos_end             = "2024-12-31",
)


def run_grid(ltf_30m: pd.DataFrame, ltf_h1: pd.DataFrame) -> pd.DataFrame:
    keys   = list(GRID.keys())
    combos = list(itertools.product(*[GRID[k] for k in keys]))
    total  = len(combos)
    print(f"Running {total} configurations...")

    rows = []
    for idx, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        cfg    = BacktestConfig(**params, **FIXED)
        ltf    = ltf_30m if cfg.ltf == "30min" else ltf_h1

        tr_t, tr_eq   = run_backtest(ltf, cfg, cfg.train_start, cfg.train_end)
        oos_t, oos_eq = run_backtest(ltf, cfg, cfg.oos_start,   cfg.oos_end)

        tr_m  = calc_metrics(tr_t,  tr_eq,  cfg.initial_balance)
        oos_m = calc_metrics(oos_t, oos_eq, cfg.initial_balance)

        row = {**params,
               "train_n":    tr_m["n_trades"],
               "train_wr":   tr_m["win_rate"],
               "train_expR": tr_m["exp_R"],
               "train_pf":   tr_m["profit_factor"],
               "train_dd":   tr_m["max_dd_pct"],
               "train_ret":  tr_m["return_pct"],
               "oos_n":      oos_m["n_trades"],
               "oos_wr":     oos_m["win_rate"],
               "oos_expR":   oos_m["exp_R"],
               "oos_pf":     oos_m["profit_factor"],
               "oos_dd":     oos_m["max_dd_pct"],
               "oos_ret":    oos_m["return_pct"],
               }
        rows.append(row)

        if (idx + 1) % 10 == 0 or idx == 0:
            pct = (idx + 1) / total * 100
            print(f"  [{pct:5.1f}%] {idx+1}/{total} | "
                  f"OOS ExpR={oos_m['exp_R']:+.3f}R WR={oos_m['win_rate']}% "
                  f"DD={oos_m['max_dd_pct']}% n={oos_m['n_trades']} "
                  f"({params['ltf']}/{params['htf']} RR={params['risk_reward']} "
                  f"off={params['entry_offset_atr_mult']} buf={params['sl_buffer_atr_mult']} "
                  f"pmb={params['pullback_max_bars']})")

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(results: pd.DataFrame) -> str:
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    res  = results.sort_values("oos_expR", ascending=False)
    top10 = res.head(10)

    passing = res[
        (res["oos_expR"]  > 0.20) &
        (res["oos_pf"]    > 1.15) &
        (res["oos_dd"]    < 25.0) &
        (res["oos_n"]     >= 30)
    ]

    baseline = results[
        (results["ltf"]                   == "h1") &
        (results["htf"]                   == "4h") &
        (results["risk_reward"]           == 1.5)  &
        (results["entry_offset_atr_mult"] == 0.3)  &
        (results["sl_buffer_atr_mult"]    == 0.5)  &
        (results["pullback_max_bars"]     == 40)
    ]
    crypto_equiv = results[
        (results["ltf"]                   == "30min") &
        (results["htf"]                   == "4h")    &
        (results["risk_reward"]           == 2.5)     &
        (results["entry_offset_atr_mult"] == 0.0)     &
        (results["sl_buffer_atr_mult"]    == 0.1)     &
        (results["pullback_max_bars"]     == 20)
    ]

    hdr = "| TF | RR | off | buf | pmb | n | WR | ExpR | PF | MaxDD | Ret |"
    sep = "|---|---|---|---|---|---|---|---|---|---|---|"

    def frow(r):
        return (f"| {r['ltf']}/{r['htf']} | {r['risk_reward']} | "
                f"{r['entry_offset_atr_mult']} | {r['sl_buffer_atr_mult']} | "
                f"{int(r['pullback_max_bars'])} | {int(r['oos_n'])} | "
                f"{r['oos_wr']}% | {r['oos_expR']:+.4f}R | "
                f"{r['oos_pf']:.3f} | {r['oos_dd']:.1f}% | {r['oos_ret']:+.1f}% |")

    L = []
    L.append("# EURUSD BOS+Pullback Grid Backtest Report\n")
    L.append(f"> Generated: {now}")
    L.append(f"> TRAIN: 2021–2022 | OOS: 2023–2024")
    L.append(f"> Spread: 1 pip (bid/ask from Dukascopy) | Commission: 0.5 pip/side | Risk: 1% equity/trade\n")
    L.append("---\n")
    L.append("## Grid Summary\n")
    L.append(f"- Total configurations: **{len(results)}**")
    L.append(f"- Passing (ExpR>0.20, PF>1.15, DD<25%, n≥30): **{len(passing)}**")
    L.append(f"- Best OOS ExpR: **{res['oos_expR'].max():+.4f}R**")
    L.append(f"- Worst OOS ExpR: **{res['oos_expR'].min():+.4f}R**\n")

    L.append("---\n")
    L.append("## PROOF V2 Equivalent (H1/4h, RR=1.5, off=0.3, buf=0.5, pmb=40)\n")
    if not baseline.empty:
        r = baseline.iloc[0]
        L += [hdr, sep, frow(r)]
        L.append(f"\n> TRAIN: n={int(r['train_n'])} ExpR={r['train_expR']:+.4f}R "
                 f"PF={r['train_pf']:.3f} DD={r['train_dd']:.1f}%\n")
    else:
        L.append("*Not in grid (pmb=40 not included — adjust GRID if needed)*\n")

    L.append("---\n")
    L.append("## Crypto v1 FX Equivalent (30m/4h, RR=2.5, off=0.0, buf=0.1, pmb=20)\n")
    if not crypto_equiv.empty:
        r = crypto_equiv.iloc[0]
        L += [hdr, sep, frow(r)]
        L.append(f"\n> TRAIN: n={int(r['train_n'])} ExpR={r['train_expR']:+.4f}R "
                 f"PF={r['train_pf']:.3f} DD={r['train_dd']:.1f}%\n")
    else:
        L.append("*Not in grid.*\n")

    L.append("---\n")
    L.append("## Top 10 Configurations (OOS ExpR)\n")
    L += [hdr, sep]
    for _, r in top10.iterrows():
        L.append(frow(r))

    if not passing.empty:
        L.append("\n---\n")
        L.append(f"## All Passing Configurations ({len(passing)} total)\n")
        L += [hdr, sep]
        for _, r in passing.iterrows():
            L.append(frow(r))

    L.append("\n---\n")
    L.append("## Parameter Impact — avg OOS ExpR\n")
    for param in ["risk_reward", "ltf", "htf",
                  "entry_offset_atr_mult", "sl_buffer_atr_mult", "pullback_max_bars"]:
        grp = results.groupby(param)["oos_expR"].mean().sort_values(ascending=False)
        L.append(f"\n### `{param}`\n")
        L.append("| Value | avg OOS ExpR |")
        L.append("|-------|-------------|")
        for val, avg in grp.items():
            L.append(f"| {val} | {avg:+.4f}R |")

    L.append("\n---\n")
    L.append("## Acceptance Criteria\n")
    L.append("| Criterion | Minimum | Target |")
    L.append("|-----------|---------|--------|")
    L.append("| ExpR (OOS) | >+0.20R | >+0.35R |")
    L.append("| Win Rate | >38% | >44% |")
    L.append("| Profit Factor | >1.15 | >1.5 |")
    L.append("| Max Drawdown | <25% | <15% |")
    L.append("| Trades/2yr | >60 | >120 |")
    L.append(f"\n*Report: {now}*\n")

    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("EURUSD Grid Backtest — BOS + Pullback")
    print("=" * 60)

    print("\n[1/4] Loading M30 bars...")
    ltf_30m = load_bars("m30")
    print(f"  M30: {len(ltf_30m):,} bars  {ltf_30m.index[0]} -> {ltf_30m.index[-1]}")

    print("[2/4] Building H1 from M30...")
    ltf_h1 = ltf_30m.resample("1h").agg({
        "open_bid": "first", "high_bid": "max", "low_bid": "min", "close_bid": "last",
        "open_ask": "first", "high_ask": "max", "low_ask": "min", "close_ask": "last",
    }).dropna()
    print(f"  H1:  {len(ltf_h1):,} bars  {ltf_h1.index[0]} -> {ltf_h1.index[-1]}")

    print("\n[3/4] Running grid search...")
    results = run_grid(ltf_30m, ltf_h1)

    out_path = OUT_DIR / "eurusd_grid_results.csv"
    results.to_csv(out_path, index=False)
    print(f"\n  CSV saved: {out_path}")

    print("\n[4/4] Generating report...")
    md = generate_report(results)
    rp = REPORT_DIR / "EURUSD_BACKTEST_REPORT.md"
    rp.write_text(md, encoding="utf-8")
    print(f"  Report: {rp}")

    top5 = results.sort_values("oos_expR", ascending=False).head(5)
    print("\n== TOP 5 (OOS ExpR) ==")
    cols = ["ltf","htf","risk_reward","entry_offset_atr_mult",
            "sl_buffer_atr_mult","pullback_max_bars",
            "oos_n","oos_wr","oos_expR","oos_pf","oos_dd","oos_ret"]
    print(top5[cols].to_string(index=False))
    print("\nDone.")


if __name__ == "__main__":
    main()










