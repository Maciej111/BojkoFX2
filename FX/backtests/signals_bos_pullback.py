"""
backtests/signals_bos_pullback.py
BOS + Pullback signal generation — odtworzona logika z src/core/strategy.py,
działająca na czystych DataFrame H1 + D1 (resample z H1).
Nie importuje nic z src/.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from .indicators import (
    atr as calc_atr, adx as calc_adx, atr_percentile, adx_slope,
    adx_slope_sma,
)


@dataclass
class TradeSetup:
    """Wynik generacji sygnału — pending setup czekający na fill."""
    bar_idx:       int        # indeks baru H1 na którym powstał sygnał
    bar_ts:        pd.Timestamp
    symbol:        str
    side:          str        # "LONG" | "SHORT"
    entry_price:   float
    sl_price:      float
    tp_price:      float
    ttl_bars:      int
    bos_level:     float
    atr_val:       float
    adx_val:       float      # ADX D1 w momencie sygnału (0 jeśli nie używany)
    atr_pct_val:   float      # percentyl ATR H1 (0–100)
    rr:            float
    # ADX v2 — H4 context (0.0 jeśli nie obliczony)
    adx_h4_val:      float = 0.0   # ADX(14) na H4 w momencie sygnału
    adx_h4_rising_2: bool  = False  # ADX_H4(t) > ADX_H4(t-2)
    adx_h4_rising_3: bool  = False  # ADX_H4(t) > ADX_H4(t-3)
    adx_h4_rising_5: bool  = False  # ADX_H4(t) > ADX_H4(t-5)
    adx_h4_slope_pos: bool = False  # ADX_H4(t) > SMA(ADX_H4, 5)
    adx_d1_rising_2: bool  = False  # ADX_D1(t) > ADX_D1(t-2)
    adx_d1_rising_3: bool  = False  # ADX_D1(t) > ADX_D1(t-3)
    adx_d1_rising_5: bool  = False  # ADX_D1(t) > ADX_D1(t-5)
    adx_d1_slope_pos: bool = False  # ADX_D1(t) > SMA(ADX_D1, 5)


@dataclass
class ClosedTrade:
    """Zamknięta transakcja."""
    symbol:        str
    side:          str
    entry_ts:      pd.Timestamp
    entry_price:   float
    exit_ts:       pd.Timestamp
    exit_price:    float
    exit_reason:   str        # "TP" | "SL" | "TTL"
    sl_price:      float
    tp_price:      float
    bos_level:     float
    rr:            float
    r_multiple:    float      # zrealizowane R (>0 zysk, <0 strata, 0 = TTL)
    bars_held:     int
    atr_val:       float
    adx_val:       float
    atr_pct_val:   float
    entry_bar_idx: int
    exit_bar_idx:  int
    units:         float      # rzeczywiste units (z sizingu)
    pnl_price:     float      # PnL w jednostkach ceny × units


# ── Pivot detection ───────────────────────────────────────────────────────────

def _precompute_pivots(high: np.ndarray, low: np.ndarray,
                       lookback: int) -> tuple:
    """
    Pre-computes running last pivot high/low for every bar in O(n).

    Returns four lists of length n:
      ph_prices[i] = price of the most recent pivot high confirmed BEFORE bar i
      ph_idxs[i]   = bar index of that pivot high (or None)
      pl_prices[i] = price of the most recent pivot low confirmed BEFORE bar i
      pl_idxs[i]   = bar index of that pivot low (or None)

    A pivot at position p is *confirmed* once we reach bar p+lookback
    (the right wing is complete), so it becomes visible from bar p+lookback+1.
    """
    n = len(high)
    ph_prices: list = [None] * n
    ph_idxs:   list = [None] * n
    pl_prices: list = [None] * n
    pl_idxs:   list = [None] * n

    last_ph = last_ph_idx = None
    last_pl = last_pl_idx = None

    for i in range(n):
        # Store running state BEFORE updating (so bar i sees pivots < i)
        ph_prices[i] = last_ph
        ph_idxs[i]   = last_ph_idx
        pl_prices[i] = last_pl
        pl_idxs[i]   = last_pl_idx

        # Candidate pivot centre: p = i - lookback (confirmed at bar i)
        p = i - lookback
        if p >= lookback:
            lo_s = p - lookback
            hi_e = p + lookback + 1
            if hi_e <= n:
                window_h = high[lo_s:hi_e]
                if high[p] == window_h.max():
                    last_ph = float(high[p])
                    last_ph_idx = p
                window_l = low[lo_s:hi_e]
                if low[p] == window_l.min():
                    last_pl = float(low[p])
                    last_pl_idx = p

    return ph_prices, ph_idxs, pl_prices, pl_idxs


# ── D1 context builder ────────────────────────────────────────────────────────

def build_d1(h1: pd.DataFrame, adx_period: int = 14) -> pd.DataFrame:
    """
    Resample H1 → D1, oblicz ADX na D1 + rising/slope flags.
    Zwraca DataFrame z indeksem dziennym i kolumnami:
      open, high, low, close, adx, adx_slope,
      adx_rising_2, adx_rising_3, adx_rising_5, adx_slope_pos
    """
    d1 = h1.resample("1D").agg({
        "open":  "first",
        "high":  "max",
        "low":   "min",
        "close": "last",
    }).dropna(how="all")
    if len(d1) >= adx_period + 5:
        adx_df = calc_adx(d1, adx_period)
        adx_s  = adx_df["adx"]
        d1["adx"]          = adx_s
        d1["adx_slope"]    = adx_slope(adx_s, lag=3)          # legacy (lag=3)
        d1["adx_rising_2"] = adx_slope(adx_s, lag=2)
        d1["adx_rising_3"] = adx_slope(adx_s, lag=3)
        d1["adx_rising_5"] = adx_slope(adx_s, lag=5)
        d1["adx_slope_pos"] = adx_slope_sma(adx_s, sma_period=5)
    else:
        for col in ("adx", "adx_slope", "adx_rising_2", "adx_rising_3",
                    "adx_rising_5", "adx_slope_pos"):
            d1[col] = np.nan if col == "adx" else False
    return d1


def build_h4(h1: pd.DataFrame, adx_period: int = 14) -> pd.DataFrame:
    """
    Resample H1 → H4, oblicz ADX(14) + rising/slope flags.
    Zwraca DataFrame z indeksem H4 i kolumnami:
      open, high, low, close, adx,
      adx_rising_2, adx_rising_3, adx_rising_5, adx_slope_pos

    No-lookahead: H4 bar na czasie t zamknięty jest gdy minęły 4 pełne H1 bary
    od ostatniego zamknięcia H4. Resample('4h') robi to automatycznie.
    """
    h4 = h1.resample("4h").agg({
        "open":  "first",
        "high":  "max",
        "low":   "min",
        "close": "last",
    }).dropna(how="all")
    if len(h4) >= adx_period + 5:
        adx_df = calc_adx(h4, adx_period)
        adx_s  = adx_df["adx"]
        h4["adx"]          = adx_s
        h4["adx_rising_2"] = adx_slope(adx_s, lag=2)
        h4["adx_rising_3"] = adx_slope(adx_s, lag=3)
        h4["adx_rising_5"] = adx_slope(adx_s, lag=5)
        h4["adx_slope_pos"] = adx_slope_sma(adx_s, sma_period=5)
    else:
        for col in ("adx", "adx_rising_2", "adx_rising_3",
                    "adx_rising_5", "adx_slope_pos"):
            h4[col] = np.nan if col == "adx" else False
    return h4




# ── Main signal generator ─────────────────────────────────────────────────────

class BOSPullbackSignalGenerator:
    """
    Iteruje przez bary H1, wykrywa BOS i generuje TradeSetup.
    Parametry przekazywane jako dict (z config).

    Workflow wydajny (wielu eksperymentów):
      1. gen.generate_all(symbol, h1, d1)  → lista wszystkich setupów z pełnym metadata
      2. filter_and_adjust(setups, exp_cfg) → przefiltrowana + RR przeliczona lista
         (używana przez run_experiments.py do unikania ponownego skanowania barów)
    """

    def __init__(self, cfg: dict):
        self.pivot_lookback       = int(cfg.get("pivot_lookback", 3))
        self.entry_offset_mult    = float(cfg.get("entry_offset_atr_mult", 0.3))
        self.sl_buffer_mult       = float(cfg.get("sl_buffer_atr_mult", 0.1))
        self.base_rr              = float(cfg.get("rr", 3.0))
        self.ttl_bars             = int(cfg.get("ttl_bars", 50))
        self.atr_period           = int(cfg.get("atr_period", 14))
        self.atr_pct_window       = int(cfg.get("atr_pct_window", 100))
        # Filter gates (set by experiment runner)
        self.adx_gate:   Optional[float] = cfg.get("adx_gate")      # None = off
        self.adx_slope_gate: bool        = bool(cfg.get("adx_slope", False))
        self.atr_pct_min: float          = float(cfg.get("atr_pct_min", 0))
        self.atr_pct_max: float          = float(cfg.get("atr_pct_max", 100))
        # RR mode
        self.rr_mode: str = cfg.get("rr_mode", "fixed")

    # ── Fast full-series scan (no filters) ───────────────────────────────────

    def generate_all(self, symbol: str, h1: pd.DataFrame,
                     d1: pd.DataFrame,
                     h4: pd.DataFrame = None) -> List[TradeSetup]:
        """
        Skanuje WSZYSTKIE bary i zwraca listę setupów bez filtrów ADX/ATR-pct.
        Każdy setup zawiera pełne metadata (adx_val, adx_h4_val, atr_pct_val,
        rising/slope flags) potrzebne do późniejszego filtrowania.

        h4: opcjonalny DataFrame H4 (z build_h4). Jeśli None — pola adx_h4_* = 0/False.
        """
        from .indicators import rr_from_adx, rr_from_atr_pct

        h1 = h1.copy()
        h1["atr"] = calc_atr(h1, self.atr_period)
        h1["atr_pct"] = atr_percentile(h1["atr"], self.atr_pct_window)

        close = h1["close"].values
        high  = h1["high"].values
        low   = h1["low"].values
        atr_v = h1["atr"].values
        atr_p = h1["atr_pct"].values
        idx_arr = h1.index

        lb = self.pivot_lookback
        min_idx = lb * 2 + 1

        ph_prices, _, pl_prices, _ = _precompute_pivots(high, low, lb)

        # ── D1 ADX lookup (no-lookahead: bisect to last closed D1 bar <= H1 ts) ──
        d1_lookup: dict = {}
        for dt_idx in range(len(d1)):
            row = d1.iloc[dt_idx]
            adx_v   = float(row["adx"]) if not pd.isna(row.get("adx", float("nan"))) else 0.0
            slp     = bool(row.get("adx_slope", False))
            r2      = bool(row.get("adx_rising_2", False))
            r3      = bool(row.get("adx_rising_3", False))
            r5      = bool(row.get("adx_rising_5", False))
            slp_pos = bool(row.get("adx_slope_pos", False))
            d1_lookup[d1.index[dt_idx].normalize()] = (adx_v, slp, r2, r3, r5, slp_pos)
        d1_keys_sorted = sorted(d1_lookup.keys())

        def _get_d1_adx(ts: pd.Timestamp) -> tuple:
            day = ts.normalize()
            pos = bisect.bisect_left(d1_keys_sorted, day)
            if pos == 0:
                return 0.0, False, False, False, False, False
            return d1_lookup[d1_keys_sorted[pos - 1]]

        # ── H4 ADX lookup (no-lookahead: last closed H4 bar <= H1 ts) ──────────
        h4_lookup: dict = {}
        h4_keys_sorted: list = []
        if h4 is not None and len(h4) > 0:
            for hi4 in range(len(h4)):
                row = h4.iloc[hi4]
                adx_v   = float(row["adx"]) if not pd.isna(row.get("adx", float("nan"))) else 0.0
                r2      = bool(row.get("adx_rising_2", False))
                r3      = bool(row.get("adx_rising_3", False))
                r5      = bool(row.get("adx_rising_5", False))
                slp_pos = bool(row.get("adx_slope_pos", False))
                h4_lookup[h4.index[hi4]] = (adx_v, r2, r3, r5, slp_pos)
            h4_keys_sorted = sorted(h4_lookup.keys())

        def _get_h4_adx(ts: pd.Timestamp) -> tuple:
            if not h4_keys_sorted:
                return 0.0, False, False, False, False
            # last H4 bar whose timestamp (bar open) <= ts - 4h (closed before ts)
            pos = bisect.bisect_right(h4_keys_sorted, ts - pd.Timedelta(hours=4))
            if pos == 0:
                return 0.0, False, False, False, False
            return h4_lookup[h4_keys_sorted[pos - 1]]

        setups: List[TradeSetup] = []

        for i in range(min_idx, len(h1)):
            ts = idx_arr[i]
            atr_val = float(atr_v[i])
            if np.isnan(atr_val) or atr_val <= 0:
                continue
            atr_pct_val = float(atr_p[i]) if not np.isnan(atr_p[i]) else 50.0

            last_ph = ph_prices[i]
            last_pl = pl_prices[i]
            if last_ph is None or last_pl is None:
                continue

            # D1 context
            adx_val, _, d1_r2, d1_r3, d1_r5, d1_slp = _get_d1_adx(ts)
            # H4 context
            adx_h4_val, h4_r2, h4_r3, h4_r5, h4_slp = _get_h4_adx(ts)

            cur_close = float(close[i])

            for side, bos_level, entry_raw, sl_raw, sign in [
                ("LONG",  last_ph,
                 last_ph + self.entry_offset_mult * atr_val,
                 last_pl  - self.sl_buffer_mult   * atr_val,
                 1)
                if cur_close > last_ph else (None, None, None, None, None),
                ("SHORT", last_pl,
                 last_pl - self.entry_offset_mult * atr_val,
                 last_ph  + self.sl_buffer_mult   * atr_val,
                 -1)
                if cur_close < last_pl else (None, None, None, None, None),
            ]:
                if side is None:
                    continue
                entry = entry_raw
                sl    = sl_raw
                if side == "LONG"  and entry <= sl:
                    continue
                if side == "SHORT" and sl <= entry:
                    continue
                rr = self.base_rr
                risk = abs(entry - sl)
                tp = entry + sign * rr * risk

                setups.append(TradeSetup(
                    bar_idx=i, bar_ts=ts, symbol=symbol, side=side,
                    entry_price=entry, sl_price=sl, tp_price=tp,
                    ttl_bars=self.ttl_bars, bos_level=bos_level,
                    atr_val=atr_val, adx_val=adx_val,
                    atr_pct_val=atr_pct_val, rr=rr,
                    adx_h4_val=adx_h4_val,
                    adx_h4_rising_2=h4_r2, adx_h4_rising_3=h4_r3,
                    adx_h4_rising_5=h4_r5, adx_h4_slope_pos=h4_slp,
                    adx_d1_rising_2=d1_r2, adx_d1_rising_3=d1_r3,
                    adx_d1_rising_5=d1_r5, adx_d1_slope_pos=d1_slp,
                ))

        return setups

    # ── Legacy single-experiment generate (kept for compatibility) ────────────

    def generate(self, symbol: str, h1: pd.DataFrame,
                 d1: pd.DataFrame,
                 h4: pd.DataFrame = None) -> List[TradeSetup]:
        """
        Generates setups with current instance filter settings applied.
        For multi-experiment pipelines prefer generate_all() + filter_and_adjust().
        """
        all_s = self.generate_all(symbol, h1, d1, h4)
        return filter_and_adjust(all_s, {
            "adx_gate":    self.adx_gate,
            "adx_slope":   self.adx_slope_gate,
            "atr_pct_min": self.atr_pct_min,
            "atr_pct_max": self.atr_pct_max,
            "rr_mode":     self.rr_mode,
            "rr":          self.base_rr,
        })


# ── Per-experiment filter (O(k) where k = len(all_setups)) ───────────────────

def filter_and_adjust(
    all_setups: List[TradeSetup],
    exp: dict,
) -> List[TradeSetup]:
    """
    Filters a pre-generated list of setups according to experiment parameters
    and recalculates RR/TP.  Cheap O(k) operation.

    exp keys:
      # Legacy (ADX v1):
      adx_gate (float|None), adx_slope (bool),
      # ADX v2:
      gate_type (str): NONE | ADX_THRESHOLD | ADX_RISING | ADX_SLOPE_POS
      gate_tf   (str): D1 | H4
      adx_threshold (float): used when gate_type=ADX_THRESHOLD
      rising_k (int): k for ADX_RISING (2|3|5)
      # ADX_SOFT (research only):
      adx_soft_threshold (float|None): if set, modify RR instead of skip
      adx_soft_rr_below (float): RR when ADX < threshold (default 2.0)
      # ATR + sizing:
      atr_pct_min, atr_pct_max, rr_mode, rr
    """
    from .indicators import rr_from_adx, rr_from_atr_pct

    # ── Resolve gate parameters ──────────────────────────────────────────────
    gate_type = exp.get("gate_type", "NONE")
    gate_tf   = exp.get("gate_tf", "D1")      # "D1" | "H4"

    # Legacy compatibility: adx_gate → ADX_THRESHOLD on D1
    if gate_type == "NONE" and exp.get("adx_gate") is not None:
        gate_type = "ADX_THRESHOLD"
        gate_tf   = "D1"

    adx_threshold     = float(exp.get("adx_threshold",
                                      exp.get("adx_gate") or 0.0))
    rising_k          = int(exp.get("rising_k", 3))
    adx_soft_thr      = exp.get("adx_soft_threshold")    # None = hard gate
    adx_soft_rr_below = float(exp.get("adx_soft_rr_below", 2.0))

    adx_slope_legacy  = bool(exp.get("adx_slope", False))  # legacy D1 slope gate

    atr_min   = float(exp.get("atr_pct_min", 0))
    atr_max   = float(exp.get("atr_pct_max", 100))
    rr_mode   = exp.get("rr_mode", "fixed")
    base_rr   = float(exp.get("rr", 3.0))

    result: List[TradeSetup] = []
    for s in all_setups:

        # ── Resolve ADX value and flags for chosen TF ────────────────────────
        if gate_tf == "H4":
            adx_val_gate    = s.adx_h4_val
            rising_flags    = {2: s.adx_h4_rising_2,
                               3: s.adx_h4_rising_3,
                               5: s.adx_h4_rising_5}
            slope_pos_flag  = s.adx_h4_slope_pos
        else:  # D1
            adx_val_gate    = s.adx_val
            rising_flags    = {2: s.adx_d1_rising_2,
                               3: s.adx_d1_rising_3,
                               5: s.adx_d1_rising_5}
            slope_pos_flag  = s.adx_d1_slope_pos

        # ── Gate logic ───────────────────────────────────────────────────────
        override_rr: float | None = None  # used by ADX_SOFT

        if gate_type == "ADX_THRESHOLD":
            if adx_soft_thr is not None:
                # SOFT gate: below threshold → reduce RR instead of skip
                if adx_val_gate < adx_soft_thr:
                    override_rr = adx_soft_rr_below
                # else: use normal RR (no skip)
            else:
                # HARD gate
                if adx_val_gate < adx_threshold:
                    continue
            # Legacy slope filter on D1
            if adx_slope_legacy and not s.adx_d1_rising_3:
                continue

        elif gate_type == "ADX_RISING":
            flag = rising_flags.get(rising_k, rising_flags[3])
            if not flag:
                continue

        elif gate_type == "ADX_SLOPE_POS":
            if not slope_pos_flag:
                continue

        # elif gate_type == "NONE": pass (no filter)

        # ── ATR pct filter ───────────────────────────────────────────────────
        if not (atr_min <= s.atr_pct_val <= atr_max):
            continue

        # ── Recalculate RR ───────────────────────────────────────────────────
        if override_rr is not None:
            rr = override_rr
        elif rr_mode == "fixed":
            rr = base_rr
        elif rr_mode in ("adx_map_v1", "adx_map_v2"):
            rr = rr_from_adx(s.adx_val, rr_mode)
        elif rr_mode == "atr_pct_map":
            rr = rr_from_atr_pct(s.atr_pct_val)
        else:
            rr = base_rr

        if rr == s.rr:
            result.append(s)
        else:
            risk = abs(s.entry_price - s.sl_price)
            sign = 1 if s.side == "LONG" else -1
            new_tp = s.entry_price + sign * rr * risk
            from dataclasses import replace as dc_replace
            result.append(dc_replace(s, rr=rr, tp_price=new_tp))

    return result
