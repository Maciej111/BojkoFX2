"""
src/research/regime_classifier/classifier.py
=============================================
Market Regime Classifier — RESEARCH ONLY, no production code touched.

Classifies each H1 bar into one of:
    TREND_UP | TREND_DOWN | RANGE | HIGH_VOL_CHOP | HIGH_VOL_TREND

Features:
  - ADX(14) — Wilder
  - EMA(200) slope (tanh-normalised)
  - Distance from EMA(200) in ATR units
  - EMA crossings (last N bars)
  - Net/Total move ratio (choppiness)
  - ATR percentile (lookback 252 bars)

Multi-timeframe: H4 derived from H1 by resampling every 4 bars.
No lookahead bias: at bar t, only bars[0..t] are used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd


# ─── Config ───────────────────────────────────────────────────────────────────

@dataclass
class RegimeConfig:
    # Feature params
    adx_period: int = 14
    ema_period: int = 200
    atr_period: int = 14
    ema_slope_lookback: int = 20
    ema_cross_lookback: int = 50
    atr_percentile_lookback: int = 252

    # Scoring weights (must sum to 1.0 for trend_score)
    adx_weight: float = 0.4
    slope_weight: float = 0.3
    distance_weight: float = 0.3

    # Decision thresholds
    trend_enter: float = 0.6
    trend_exit: float = 0.4
    chop_enter: float = 0.6
    chop_exit: float = 0.4
    high_vol_threshold: float = 75.0   # ATR percentile (0-100)

    # Stability
    min_regime_duration: int = 8       # bars


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class RegimeResult:
    label: str               # TREND_UP / TREND_DOWN / RANGE / HIGH_VOL_CHOP / HIGH_VOL_TREND
    trend_score: float       # 0.0 – 1.0
    chop_score: float        # 0.0 – 1.0
    volatility_score: float  # 0.0 – 1.0  (ATR pct / 100)
    confidence: float        # 0.0 – 1.0
    regime_duration: int     # bars in current regime
    macro_label: str         # regime on H4 (derived from H1)
    micro_label: str         # regime on H1


# ─── Low-level indicator helpers (standalone, no external deps) ───────────────

def _wilder_atr(high: np.ndarray, low: np.ndarray,
                close: np.ndarray, period: int) -> np.ndarray:
    """Wilder-smoothed ATR.  Returns array same length as inputs."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i]  - close[i - 1]))
    atr = np.empty(n)
    atr[:period] = np.nan
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        alpha = 1.0 / period
        for i in range(period, n):
            atr[i] = atr[i - 1] * (1 - alpha) + tr[i] * alpha
    return atr


def _wilder_adx(high: np.ndarray, low: np.ndarray,
                close: np.ndarray, period: int) -> np.ndarray:
    """Wilder-smoothed ADX(period).  Returns ADX array."""
    n = len(close)
    alpha = 1.0 / period

    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up   = high[i]  - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm[i]  = up   if (up > down and up > 0)   else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0

    atr_arr = _wilder_atr(high, low, close, period)

    # Wilder smooth DM
    plus_dm_s  = np.empty(n); plus_dm_s[:]  = np.nan
    minus_dm_s = np.empty(n); minus_dm_s[:] = np.nan
    if n >= period:
        plus_dm_s[period - 1]  = np.sum(plus_dm[:period])
        minus_dm_s[period - 1] = np.sum(minus_dm[:period])
        for i in range(period, n):
            plus_dm_s[i]  = plus_dm_s[i - 1]  * (1 - alpha) + plus_dm[i]  * alpha
            minus_dm_s[i] = minus_dm_s[i - 1] * (1 - alpha) + minus_dm[i] * alpha

    with np.errstate(invalid="ignore", divide="ignore"):
        plus_di  = 100 * plus_dm_s  / np.where(atr_arr == 0, np.nan, atr_arr)
        minus_di = 100 * minus_dm_s / np.where(atr_arr == 0, np.nan, atr_arr)
        dx = 100 * np.abs(plus_di - minus_di) / np.where(
            (plus_di + minus_di) == 0, np.nan, (plus_di + minus_di))

    dx = np.nan_to_num(dx, nan=0.0)
    adx_arr = np.empty(n); adx_arr[:] = np.nan
    p2 = 2 * period - 1
    if n >= p2:
        adx_arr[p2 - 1] = np.mean(dx[period - 1: p2])
        for i in range(p2, n):
            adx_arr[i] = adx_arr[i - 1] * (1 - alpha) + dx[i] * alpha
    return adx_arr


def _ema(close: np.ndarray, period: int) -> np.ndarray:
    """Standard EMA (exponential, adjust=False)."""
    alpha = 2.0 / (period + 1)
    result = np.empty(len(close))
    result[:] = np.nan
    if len(close) < period:
        return result
    result[period - 1] = np.mean(close[:period])
    for i in range(period, len(close)):
        result[i] = result[i - 1] * (1 - alpha) + close[i] * alpha
    return result


def _percentile_rank(value: float, history: np.ndarray) -> float:
    """Returns 0-100 percentile rank of value within history."""
    valid = history[~np.isnan(history)]
    if len(valid) == 0:
        return 50.0
    return float(np.sum(valid <= value) / len(valid) * 100)


# ─── Core Classifier ──────────────────────────────────────────────────────────

class MarketRegimeClassifier:
    """
    Stateful single-symbol classifier.  Call update(bars) repeatedly
    (or once with the full DataFrame for bulk pre-computation).

    Parameters
    ----------
    config : RegimeConfig
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        self.config: RegimeConfig = config or RegimeConfig()
        # Internal hysteresis state
        self.current_regime: Optional[str] = None
        self.regime_bar_count: int = 0

    def reset(self) -> None:
        """Reset hysteresis state (call between symbols in batch mode)."""
        self.current_regime = None
        self.regime_bar_count = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, bars: pd.DataFrame) -> RegimeResult:
        """
        Classify the LAST bar in *bars*.

        Parameters
        ----------
        bars : pd.DataFrame
            Columns required: timestamp (index or column), close.
            Optional: high, low (used for ATR; fallback: ±0.5% of close).
            Sorted ascending.  Minimum 250 rows before a meaningful result.

        Returns
        -------
        RegimeResult for the last bar.
        """
        cfg = self.config
        df = bars.copy()

        # ── Normalise columns ──────────────────────────────────────────────
        df.columns = [c.lower() for c in df.columns]
        # Accept bid_close / bid_high / bid_low variants
        for src, dst in [("bid_close", "close"),
                         ("bid_high",  "high"),
                         ("bid_low",   "low")]:
            if src in df.columns and dst not in df.columns:
                df[dst] = df[src]

        if "close" not in df.columns:
            raise ValueError("bars must contain a 'close' (or 'bid_close') column")

        close = df["close"].values.astype(float)
        n = len(close)

        # Fallback high/low if absent
        if "high" in df.columns:
            high = df["high"].values.astype(float)
        else:
            high = close * 1.005
        if "low" in df.columns:
            low = df["low"].values.astype(float)
        else:
            low = close * 0.995

        # ── Feature computation (uses all bars up to t, no lookahead) ──────
        adx_arr  = _wilder_adx(high, low, close, cfg.adx_period)
        ema_arr  = _ema(close, cfg.ema_period)
        atr_arr  = _wilder_atr(high, low, close, cfg.atr_period)

        # ── Extract scalar features for the last bar ───────────────────────
        adx_val  = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 0.0
        ema_val  = float(ema_arr[-1]) if not np.isnan(ema_arr[-1]) else close[-1]
        atr_val  = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else \
                   float(np.nanmean(atr_arr[-20:]))

        # EMA slope (tanh normalised)
        lb_slope = cfg.ema_slope_lookback
        if n >= lb_slope + 1 and not np.isnan(ema_arr[-lb_slope - 1]):
            ema_old  = float(ema_arr[-lb_slope - 1])
            slope_raw = (ema_val - ema_old) / ema_old if ema_old != 0 else 0.0
            slope_norm = float(np.tanh(slope_raw * 100))
        else:
            slope_norm = 0.0

        # Distance from EMA in ATR units, clipped to [-1, 1]
        if atr_val > 0:
            distance = (close[-1] - ema_val) / atr_val
            distance_norm = float(np.clip(distance / 3.0, -1.0, 1.0))
        else:
            distance_norm = 0.0

        # EMA crossings in last N bars
        lb_cross = min(cfg.ema_cross_lookback, n - 1)
        crossings = 0
        if lb_cross > 1:
            sub_close = close[-(lb_cross + 1):]
            sub_ema   = ema_arr[-(lb_cross + 1):]
            above_prev = sub_close[0] > sub_ema[0]
            for k in range(1, len(sub_close)):
                if np.isnan(sub_ema[k]):
                    continue
                above_now = sub_close[k] > sub_ema[k]
                if above_now != above_prev:
                    crossings += 1
                above_prev = above_now
        crossing_norm = float(
            np.clip(crossings / max(cfg.ema_cross_lookback / 5.0, 1.0), 0.0, 1.0)
        )

        # Net/total move ratio (choppiness), last N bars
        lb_chop = min(cfg.ema_cross_lookback, n - 1)
        sub_c = close[-lb_chop - 1:]
        net_move = abs(sub_c[-1] - sub_c[0])
        total_move = float(np.sum(np.abs(np.diff(sub_c))))
        if total_move > 0:
            chop_ratio = float(np.clip(1.0 - net_move / total_move, 0.0, 1.0))
        else:
            chop_ratio = 0.5

        # ATR percentile (0-100)
        pct_lb = min(cfg.atr_percentile_lookback, n)
        atr_pct = _percentile_rank(atr_val, atr_arr[-pct_lb:])

        # ── Scores ──────────────────────────────────────────────────────────
        adx_norm           = float(np.clip((adx_val - 15.0) / 25.0, 0.0, 1.0))
        slope_component    = abs(slope_norm)
        distance_component = abs(distance_norm)

        trend_score = (
            cfg.adx_weight      * adx_norm +
            cfg.slope_weight    * slope_component +
            cfg.distance_weight * distance_component
        )
        chop_score      = 0.5 * crossing_norm + 0.5 * chop_ratio
        volatility_score = atr_pct / 100.0

        # ── Regime decision ──────────────────────────────────────────────────
        label = self._decide_regime(
            trend_score, chop_score, volatility_score, slope_norm, atr_pct
        )

        # ── Confidence ──────────────────────────────────────────────────────
        if label in ("TREND_UP", "TREND_DOWN"):
            confidence = trend_score * (1.0 - chop_score)
        elif label == "RANGE":
            confidence = chop_score * (1.0 - trend_score)
        else:  # HIGH_VOL_*
            confidence = volatility_score
        confidence = float(np.clip(confidence, 0.0, 1.0))

        return RegimeResult(
            label=label,
            trend_score=round(trend_score, 4),
            chop_score=round(chop_score, 4),
            volatility_score=round(volatility_score, 4),
            confidence=round(confidence, 4),
            regime_duration=self.regime_bar_count,
            macro_label="",    # filled by compute_regime_series
            micro_label=label,
        )

    # ── Internal decision logic ───────────────────────────────────────────────

    def _decide_regime(
        self,
        trend_score: float,
        chop_score: float,
        volatility_score: float,
        slope_norm: float,
        atr_pct: float,
    ) -> str:
        cfg = self.config

        # HIGH_VOL overlay (checked first)
        if atr_pct > cfg.high_vol_threshold:
            if chop_score > cfg.chop_enter:
                candidate = "HIGH_VOL_CHOP"
            else:
                candidate = "HIGH_VOL_TREND"
        # TREND
        elif trend_score > cfg.trend_enter and chop_score < cfg.chop_exit:
            if slope_norm > 0.05:
                candidate = "TREND_UP"
            elif slope_norm < -0.05:
                candidate = "TREND_DOWN"
            else:
                candidate = "TREND_UP"   # fallback for flat slope
        # RANGE
        elif chop_score > cfg.chop_enter and trend_score < cfg.trend_exit:
            candidate = "RANGE"
        else:
            # Hysteresis: keep current if zone is ambiguous
            candidate = self.current_regime or "RANGE"

        # Minimum duration enforcement
        if candidate != self.current_regime:
            if self.regime_bar_count < cfg.min_regime_duration:
                # Not long enough in previous regime — stay
                candidate = self.current_regime or "RANGE"
            else:
                self.current_regime = candidate
                self.regime_bar_count = 0

        self.regime_bar_count += 1
        return self.current_regime or "RANGE"


# ─── MTF helpers ──────────────────────────────────────────────────────────────

def _resample_h1_to_h4(h1_df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive H4 bars from H1 by grouping every 4 consecutive bars.
    Returns DataFrame with columns: open, high, low, close.
    Index is the timestamp of the first H1 bar in each group.
    """
    df = h1_df.copy()
    df.columns = [c.lower() for c in df.columns]
    for src, dst in [("bid_close", "close"), ("bid_high", "high"), ("bid_low", "low"),
                     ("bid_open", "open")]:
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]

    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df.index = pd.to_datetime(df["timestamp"], utc=True)
        elif "datetime" in df.columns:
            df.index = pd.to_datetime(df["datetime"], utc=True)

    # Ensure tz-aware
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")

    h4 = df[["open", "high", "low", "close"]].resample("4h").agg({
        "open":  "first",
        "high":  "max",
        "low":   "min",
        "close": "last",
    }).dropna(how="all")
    return h4


def is_trade_allowed(macro: str, micro: str) -> bool:
    """
    Trade filter based on MTF regime.
    Returns False (block) if macro is ranging/choppy or micro is high-vol-chop.
    """
    if macro in ("RANGE", "HIGH_VOL_CHOP"):
        return False
    if micro == "HIGH_VOL_CHOP":
        return False
    return True


# ─── Pre-computed feature cache (amortise expensive indicator work) ──────────

from dataclasses import field as _dc_field

@dataclass
class PrecomputedFeatures:
    """
    All expensive indicator arrays computed once per symbol.
    Stored as numpy arrays aligned to the H1 bar index.
    Pass to apply_thresholds() with different RegimeConfig objects.
    """
    index: object          # pd.DatetimeIndex
    close: object          # np.ndarray
    adx_arr: object        # np.ndarray
    ema_arr: object        # np.ndarray
    atr_arr: object        # np.ndarray
    # Per-bar scalars derived from arrays (computed once, fast to re-threshold)
    slope_norm_arr:    object   # np.ndarray  tanh-normalized EMA slope
    distance_norm_arr: object   # np.ndarray  distance from EMA in ATR units, clipped
    crossing_norm_arr: object   # np.ndarray  EMA crossing rate, normalized
    chop_ratio_arr:    object   # np.ndarray  net/total move ratio
    atr_pct_arr:       object   # np.ndarray  ATR percentile 0-100
    # H4 derived features (macro)
    h4_index:      object       # pd.DatetimeIndex
    h4_slope_norm: object       # np.ndarray
    h4_dist_norm:  object       # np.ndarray
    h4_cross_norm: object       # np.ndarray
    h4_chop_ratio: object       # np.ndarray
    h4_atr_pct:    object       # np.ndarray
    h4_adx_norm:   object       # np.ndarray  (adx-15)/25 clipped 0-1


def precompute_features(
    bars_df: pd.DataFrame,
    config: Optional[RegimeConfig] = None,
) -> "PrecomputedFeatures":
    """
    Compute all indicator arrays once.  Expensive (seconds), but called only
    once per symbol.  The result is reused across all 18 grid configs.
    """
    cfg = config or RegimeConfig()
    df = bars_df.copy()
    df.columns = [c.lower() for c in df.columns]
    for src, dst in [("bid_close", "close"), ("bid_high", "high"),
                     ("bid_low", "low"), ("bid_open", "open")]:
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]

    if not isinstance(df.index, pd.DatetimeIndex):
        ts_col = next((c for c in ("datetime", "timestamp", "time", "date")
                       if c in df.columns), None)
        if ts_col:
            df.index = pd.to_datetime(df[ts_col], utc=True)
        else:
            df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]

    close = df["close"].values.astype(float)
    high  = df["high"].values.astype(float)  if "high"  in df.columns else close * 1.005
    low   = df["low"].values.astype(float)   if "low"   in df.columns else close * 0.995
    n = len(close)

    adx_arr = _wilder_adx(high, low, close, cfg.adx_period)
    ema_arr = _ema(close, cfg.ema_period)
    atr_arr = _wilder_atr(high, low, close, cfg.atr_period)

    # ── EMA slope ─────────────────────────────────────────────────────────
    lb_sl = cfg.ema_slope_lookback
    slope_norm_arr = np.zeros(n)
    for i in range(lb_sl, n):
        if np.isnan(ema_arr[i]) or np.isnan(ema_arr[i - lb_sl]):
            continue
        ema_old = float(ema_arr[i - lb_sl])
        if ema_old != 0:
            slope_norm_arr[i] = float(np.tanh((ema_arr[i] - ema_old) / ema_old * 100))

    # ── Distance from EMA ─────────────────────────────────────────────────
    distance_norm_arr = np.zeros(n)
    for i in range(n):
        atr_i = float(atr_arr[i]) if not np.isnan(atr_arr[i]) else 0.0
        ema_i = float(ema_arr[i]) if not np.isnan(ema_arr[i]) else close[i]
        if atr_i > 0:
            distance_norm_arr[i] = float(np.clip((close[i] - ema_i) / atr_i / 3.0, -1.0, 1.0))

    # ── EMA crossings ─────────────────────────────────────────────────────
    lb_cr = cfg.ema_cross_lookback
    crossing_norm_arr = np.zeros(n)
    norm_denom = max(lb_cr / 5.0, 1.0)
    for i in range(1, n):
        lb = min(lb_cr, i)
        sub_c = close[i - lb: i + 1]
        sub_e = ema_arr[i - lb: i + 1]
        crossings = 0
        above_p = sub_c[0] > sub_e[0]
        for k in range(1, len(sub_c)):
            if np.isnan(sub_e[k]):
                continue
            above_n = sub_c[k] > sub_e[k]
            if above_n != above_p:
                crossings += 1
            above_p = above_n
        crossing_norm_arr[i] = float(np.clip(crossings / norm_denom, 0.0, 1.0))

    # ── Choppiness ratio ──────────────────────────────────────────────────
    chop_ratio_arr = np.full(n, 0.5)
    for i in range(1, n):
        lb = min(lb_cr, i)
        sub_ch = close[i - lb: i + 1]
        nm = abs(sub_ch[-1] - sub_ch[0])
        tm = float(np.sum(np.abs(np.diff(sub_ch))))
        if tm > 0:
            chop_ratio_arr[i] = float(np.clip(1.0 - nm / tm, 0.0, 1.0))

    # ── ATR percentile ────────────────────────────────────────────────────
    pct_lb = cfg.atr_percentile_lookback
    atr_pct_arr = np.full(n, 50.0)
    for i in range(n):
        if np.isnan(atr_arr[i]):
            continue
        start_i = max(0, i - pct_lb + 1)
        hist = atr_arr[start_i: i + 1]
        atr_pct_arr[i] = _percentile_rank(float(atr_arr[i]), hist)

    # ── H4 features ───────────────────────────────────────────────────────
    h4_df = _resample_h1_to_h4(df)
    h4_close = h4_df["close"].values.astype(float)
    h4_high  = h4_df["high"].values.astype(float)  if "high" in h4_df.columns else h4_close * 1.005
    h4_low   = h4_df["low"].values.astype(float)   if "low"  in h4_df.columns else h4_close * 0.995
    h4_n = len(h4_close)

    h4_adx_arr = _wilder_adx(h4_high, h4_low, h4_close, cfg.adx_period)
    h4_ema_arr = _ema(h4_close, cfg.ema_period)
    h4_atr_arr = _wilder_atr(h4_high, h4_low, h4_close, cfg.atr_period)

    h4_slope_norm = np.zeros(h4_n)
    for j in range(lb_sl, h4_n):
        if not np.isnan(h4_ema_arr[j]) and not np.isnan(h4_ema_arr[j - lb_sl]):
            eo = float(h4_ema_arr[j - lb_sl])
            if eo != 0:
                h4_slope_norm[j] = float(np.tanh((h4_ema_arr[j] - eo) / eo * 100))

    h4_dist_norm = np.zeros(h4_n)
    for j in range(h4_n):
        a = float(h4_atr_arr[j]) if not np.isnan(h4_atr_arr[j]) else 0.0
        e = float(h4_ema_arr[j]) if not np.isnan(h4_ema_arr[j]) else h4_close[j]
        if a > 0:
            h4_dist_norm[j] = float(np.clip((h4_close[j] - e) / a / 3.0, -1.0, 1.0))

    h4_cross_norm = np.zeros(h4_n)
    for j in range(1, h4_n):
        lb = min(lb_cr, j)
        sc = h4_close[j - lb: j + 1]
        se = h4_ema_arr[j - lb: j + 1]
        cr = 0; ap = sc[0] > se[0]
        for k in range(1, len(sc)):
            if np.isnan(se[k]): continue
            an = sc[k] > se[k]
            if an != ap: cr += 1
            ap = an
        h4_cross_norm[j] = float(np.clip(cr / norm_denom, 0.0, 1.0))

    h4_chop_ratio = np.full(h4_n, 0.5)
    for j in range(1, h4_n):
        lb = min(lb_cr, j)
        sc = h4_close[j - lb: j + 1]
        nm = abs(sc[-1] - sc[0])
        tm = float(np.sum(np.abs(np.diff(sc))))
        if tm > 0:
            h4_chop_ratio[j] = float(np.clip(1.0 - nm / tm, 0.0, 1.0))

    h4_atr_pct = np.full(h4_n, 50.0)
    for j in range(h4_n):
        if np.isnan(h4_atr_arr[j]): continue
        s = max(0, j - pct_lb + 1)
        h4_atr_pct[j] = _percentile_rank(float(h4_atr_arr[j]), h4_atr_arr[s: j + 1])

    h4_adx_norm = np.clip((np.nan_to_num(h4_adx_arr) - 15.0) / 25.0, 0.0, 1.0)

    return PrecomputedFeatures(
        index=df.index,
        close=close,
        adx_arr=adx_arr,
        ema_arr=ema_arr,
        atr_arr=atr_arr,
        slope_norm_arr=slope_norm_arr,
        distance_norm_arr=distance_norm_arr,
        crossing_norm_arr=crossing_norm_arr,
        chop_ratio_arr=chop_ratio_arr,
        atr_pct_arr=atr_pct_arr,
        h4_index=h4_df.index,
        h4_slope_norm=h4_slope_norm,
        h4_dist_norm=h4_dist_norm,
        h4_cross_norm=h4_cross_norm,
        h4_chop_ratio=h4_chop_ratio,
        h4_atr_pct=h4_atr_pct,
        h4_adx_norm=h4_adx_norm,
    )


def apply_thresholds(
    feats: "PrecomputedFeatures",
    config: RegimeConfig,
) -> pd.DataFrame:
    """
    Apply regime decision thresholds to pre-computed features.
    Fully vectorised — O(n) numpy ops only, no Python loops over bars.

    Returns same schema as compute_regime_series().
    """
    cfg = config
    n = len(feats.close)

    # ── Vectorised scores ─────────────────────────────────────────────────
    adx_norm = np.clip((np.nan_to_num(feats.adx_arr) - 15.0) / 25.0, 0.0, 1.0)
    trend_sc  = (cfg.adx_weight      * adx_norm
               + cfg.slope_weight    * np.abs(feats.slope_norm_arr)
               + cfg.distance_weight * np.abs(feats.distance_norm_arr))
    chop_sc   = 0.5 * feats.crossing_norm_arr + 0.5 * feats.chop_ratio_arr
    atr_pct   = feats.atr_pct_arr
    slope_n   = feats.slope_norm_arr

    # ── Vectorised candidate regime (no hysteresis yet) ───────────────────
    # Priority order (same as _decide_regime):
    # 1. HIGH_VOL_CHOP  : atr_pct > hvt AND chop_sc > chop_enter
    # 2. HIGH_VOL_TREND : atr_pct > hvt
    # 3. TREND_UP       : trend_sc > trend_enter AND chop_sc < chop_exit AND slope > 0.05
    # 4. TREND_DOWN     : trend_sc > trend_enter AND chop_sc < chop_exit AND slope < -0.05
    # 5. TREND_UP (flat): trend_sc > trend_enter AND chop_sc < chop_exit
    # 6. RANGE          : chop_sc > chop_enter AND trend_sc < trend_exit
    # 7. RANGE (default)

    # Integer labels (must be defined before use)
    TREND_UP   = 0
    TREND_DOWN = 1
    RANGE      = 2
    HV_CHOP    = 3
    HV_TREND   = 4

    te = cfg.trend_enter; tx = cfg.trend_exit
    ce = cfg.chop_enter;  cx = cfg.chop_exit
    hvt = cfg.high_vol_threshold

    cand = np.full(n, RANGE, dtype=np.int8)   # default = RANGE

    # Apply in reverse priority (last write wins, so high priority goes last)
    is_range  = (chop_sc > ce) & (trend_sc < tx)
    is_tup    = (trend_sc > te) & (chop_sc < cx) & (slope_n >= -0.05)   # includes flat
    is_tdown  = (trend_sc > te) & (chop_sc < cx) & (slope_n < -0.05)
    is_hv     = atr_pct > hvt
    is_hv_chop  = is_hv & (chop_sc > ce)
    is_hv_trend = is_hv & ~(chop_sc > ce)

    cand[is_range]    = RANGE
    cand[is_tup]      = TREND_UP
    cand[is_tdown]    = TREND_DOWN
    cand[is_hv_trend] = HV_TREND
    cand[is_hv_chop]  = HV_CHOP

    # Warmup: first 250 bars → RANGE
    cand[:250] = RANGE

    # ── Apply hysteresis (min_regime_duration) ────────────────────────────
    # Python loop over regime changes only (typically <<n events)
    min_dur = cfg.min_regime_duration
    regime_arr = cand.copy()
    cur = RANGE
    run = 0
    for i in range(n):
        c = int(cand[i])
        if c != cur:
            if run >= min_dur:
                cur = c
                run = 0
            # else: keep cur (hysteresis)
        regime_arr[i] = cur
        run += 1

    # ── H4 macro (vectorised same way) ────────────────────────────────────
    h4_n    = len(feats.h4_adx_norm)
    h4_ts   = feats.h4_index

    h4_ts_c = 0.5 * feats.h4_cross_norm + 0.5 * feats.h4_chop_ratio
    h4_ts_s = (cfg.adx_weight      * feats.h4_adx_norm
             + cfg.slope_weight    * np.abs(feats.h4_slope_norm)
             + cfg.distance_weight * np.abs(feats.h4_dist_norm))

    h4_cand = np.full(h4_n, RANGE, dtype=np.int8)
    h4_cand[250:] = RANGE
    h4_is_range  = (h4_ts_c > ce) & (h4_ts_s < tx)
    h4_is_tup    = (h4_ts_s > te) & (h4_ts_c < cx) & (feats.h4_slope_norm >= -0.05)
    h4_is_tdown  = (h4_ts_s > te) & (h4_ts_c < cx) & (feats.h4_slope_norm < -0.05)
    h4_is_hv     = feats.h4_atr_pct > hvt
    h4_cand[h4_is_range]  = RANGE
    h4_cand[h4_is_tup]    = TREND_UP
    h4_cand[h4_is_tdown]  = TREND_DOWN
    h4_cand[h4_is_hv & ~(h4_ts_c > ce)] = HV_TREND
    h4_cand[h4_is_hv &  (h4_ts_c > ce)] = HV_CHOP
    h4_cand[:250] = RANGE

    h4_regime = h4_cand.copy()
    cur = RANGE; run = 0
    for j in range(h4_n):
        c = int(h4_cand[j])
        if c != cur:
            if run >= min_dur:
                cur = c; run = 0
        h4_regime[j] = cur
        run += 1

    _LABELS = ["TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOL_CHOP", "HIGH_VOL_TREND"]

    # Build macro lookup array: for each H1 bar index, find macro regime
    # (last H4 bar whose open-time <= h1_ts - 4h)
    h1_ts_np  = feats.index
    h4_ts_np  = feats.h4_index
    h4_cutoff = h4_ts_np  # H4 bar timestamps

    # Vectorised searchsorted for H4 macro lookup
    h1_cutoff = h1_ts_np - pd.Timedelta(hours=4)
    h4_pos    = np.searchsorted(h4_cutoff, h1_cutoff, side="right") - 1
    # Clip to valid range
    h4_pos_valid = np.clip(h4_pos, 0, h4_n - 1)
    macro_arr = h4_regime[h4_pos_valid]
    macro_arr[h4_pos < 0] = RANGE   # no H4 bar yet → RANGE

    # ── Trade allowed ─────────────────────────────────────────────────────
    # Allowed when: macro not RANGE/HV_CHOP AND micro not HV_CHOP
    macro_ok  = ~np.isin(macro_arr, [RANGE, HV_CHOP])
    micro_ok  = regime_arr != HV_CHOP
    trade_ok  = macro_ok & micro_ok
    trade_ok[:250] = False  # warmup

    # ── Build DataFrame ───────────────────────────────────────────────────
    result = pd.DataFrame({
        "regime":       [_LABELS[int(r)] for r in regime_arr],
        "trend_score":  np.round(trend_sc, 4),
        "chop_score":   np.round(chop_sc, 4),
        "vol_score":    np.round(atr_pct / 100.0, 4),
        "macro_regime": [_LABELS[int(r)] for r in macro_arr],
        "trade_allowed": trade_ok,
    }, index=feats.index)
    result.index.name = "timestamp"
    return result


# ─── Bulk pre-computation ─────────────────────────────────────────────────────

def compute_regime_series(
    bars_df: pd.DataFrame,
    config: Optional[RegimeConfig] = None,
) -> pd.DataFrame:
    """
    Pre-compute regime for every H1 bar in *bars_df*.

    Parameters
    ----------
    bars_df : pd.DataFrame
        H1 OHLC bars.  Columns: close (required), high, low (optional).
        Index or 'datetime'/'timestamp' column is used as the timestamp.
        Sorted ascending, UTC.
    config : RegimeConfig or None

    Returns
    -------
    pd.DataFrame with columns:
        timestamp, regime, trend_score, chop_score, vol_score,
        macro_regime, trade_allowed
    One row per H1 bar.
    """
    cfg = config or RegimeConfig()
    df = bars_df.copy()
    df.columns = [c.lower() for c in df.columns]
    for src, dst in [("bid_close", "close"), ("bid_high", "high"),
                     ("bid_low", "low"), ("bid_open", "open")]:
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]

    # Build proper DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        ts_col = next((c for c in ("datetime", "timestamp", "time", "date")
                       if c in df.columns), None)
        if ts_col:
            df.index = pd.to_datetime(df[ts_col], utc=True)
        else:
            df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # ── Pre-compute all feature arrays over full series (vectorised) ──────────
    close = df["close"].values.astype(float)
    high  = df["high"].values.astype(float)  if "high"  in df.columns else close * 1.005
    low   = df["low"].values.astype(float)   if "low"   in df.columns else close * 0.995
    n = len(close)

    adx_arr  = _wilder_adx(high, low, close, cfg.adx_period)
    ema_arr  = _ema(close, cfg.ema_period)
    atr_arr  = _wilder_atr(high, low, close, cfg.atr_period)

    # Pre-compute H4 regime series for macro_label
    h4_df    = _resample_h1_to_h4(df)
    macro_clf = MarketRegimeClassifier(cfg)
    macro_clf.reset()

    # Build macro series: for each H4 bar compute regime
    h4_close = h4_df["close"].values.astype(float)
    h4_high  = h4_df["high"].values.astype(float) if "high" in h4_df.columns else h4_close * 1.005
    h4_low   = h4_df["low"].values.astype(float)  if "low"  in h4_df.columns else h4_close * 0.995
    h4_n = len(h4_close)

    h4_adx = _wilder_adx(h4_high, h4_low, h4_close, cfg.adx_period)
    h4_ema = _ema(h4_close, cfg.ema_period)
    h4_atr = _wilder_atr(h4_high, h4_low, h4_close, cfg.atr_period)

    # Per H4 bar: build macro regime (simple scalar approach, no full DataFrame rebuild)
    h4_regimes: list = []
    for j in range(h4_n):
        if j < 250:
            h4_regimes.append("RANGE")
            continue
        adx_j  = float(h4_adx[j]) if not np.isnan(h4_adx[j]) else 0.0
        ema_j  = float(h4_ema[j]) if not np.isnan(h4_ema[j]) else h4_close[j]
        atr_j  = float(h4_atr[j]) if not np.isnan(h4_atr[j]) else float(np.nanmean(h4_atr[max(0, j-20):j+1]))

        lb_sl  = min(cfg.ema_slope_lookback, j)
        ema_old = float(h4_ema[j - lb_sl]) if lb_sl > 0 and not np.isnan(h4_ema[j - lb_sl]) else ema_j
        slope_raw = (ema_j - ema_old) / ema_old if ema_old != 0 else 0.0
        slope_norm_j = float(np.tanh(slope_raw * 100))

        dist_j = float(np.clip((h4_close[j] - ema_j) / atr_j / 3.0, -1.0, 1.0)) if atr_j > 0 else 0.0

        lb_cr = min(cfg.ema_cross_lookback, j)
        crossings_j = 0
        if lb_cr > 1:
            sub_c_j = h4_close[j - lb_cr: j + 1]
            sub_e_j = h4_ema[j - lb_cr: j + 1]
            above_p = sub_c_j[0] > sub_e_j[0]
            for k in range(1, len(sub_c_j)):
                if np.isnan(sub_e_j[k]):
                    continue
                above_n = sub_c_j[k] > sub_e_j[k]
                if above_n != above_p:
                    crossings_j += 1
                above_p = above_n
        cr_norm_j = float(np.clip(crossings_j / max(cfg.ema_cross_lookback / 5.0, 1.0), 0.0, 1.0))

        lb_chop_j = min(cfg.ema_cross_lookback, j)
        sub_chop = h4_close[j - lb_chop_j: j + 1]
        nm_j = abs(sub_chop[-1] - sub_chop[0])
        tm_j = float(np.sum(np.abs(np.diff(sub_chop)))) if len(sub_chop) > 1 else 1.0
        chop_j = float(np.clip(1.0 - nm_j / tm_j, 0.0, 1.0)) if tm_j > 0 else 0.5

        pct_lb_j = min(cfg.atr_percentile_lookback, j + 1)
        atr_pct_j = _percentile_rank(atr_j, h4_atr[j - pct_lb_j + 1: j + 1])

        adx_norm_j    = float(np.clip((adx_j - 15.0) / 25.0, 0.0, 1.0))
        trend_sc_j    = cfg.adx_weight * adx_norm_j + cfg.slope_weight * abs(slope_norm_j) + cfg.distance_weight * abs(dist_j)
        chop_sc_j     = 0.5 * cr_norm_j + 0.5 * chop_j

        h4_regimes.append(
            macro_clf._decide_regime(trend_sc_j, chop_sc_j, atr_pct_j / 100.0,
                                     slope_norm_j, atr_pct_j)
        )

    # Build lookup: H1 timestamp → macro regime
    # For each H1 bar, use the LAST CLOSED H4 bar before it (no-lookahead)
    h4_ts_arr = h4_df.index.to_list()
    h4_reg_series = pd.Series(h4_regimes, index=h4_df.index)

    def _macro_at(ts: pd.Timestamp) -> str:
        """Last closed H4 bar at or before ts - 4h."""
        cutoff = ts - pd.Timedelta(hours=4)
        pos = pd.Index(h4_ts_arr).searchsorted(cutoff, side="right")
        if pos == 0:
            return "RANGE"
        return str(h4_reg_series.iloc[pos - 1])

    # ── Row-by-row classification (H1 bars) ──────────────────────────────────
    clf = MarketRegimeClassifier(cfg)
    clf.reset()

    rows: list = []
    min_bars = 250  # warmup
    for i in range(n):
        ts_i = df.index[i]

        if i < min_bars:
            rows.append({
                "timestamp":   ts_i,
                "regime":      "RANGE",
                "trend_score": 0.0,
                "chop_score":  0.5,
                "vol_score":   0.5,
                "macro_regime": "RANGE",
                "trade_allowed": False,
            })
            # Still advance the hysteresis state
            clf.regime_bar_count += 1
            continue

        # Scalar features for bar i (using precomputed arrays — no lookahead)
        adx_i  = float(adx_arr[i]) if not np.isnan(adx_arr[i]) else 0.0
        ema_i  = float(ema_arr[i]) if not np.isnan(ema_arr[i]) else close[i]
        atr_i  = float(atr_arr[i]) if not np.isnan(atr_arr[i]) else float(np.nanmean(atr_arr[max(0, i-20):i+1]))

        lb_sl  = min(cfg.ema_slope_lookback, i)
        ema_old = float(ema_arr[i - lb_sl]) if lb_sl > 0 and not np.isnan(ema_arr[i - lb_sl]) else ema_i
        slope_raw = (ema_i - ema_old) / ema_old if ema_old != 0 else 0.0
        slope_norm_i = float(np.tanh(slope_raw * 100))

        dist_i = float(np.clip((close[i] - ema_i) / atr_i / 3.0, -1.0, 1.0)) if atr_i > 0 else 0.0

        lb_cr  = min(cfg.ema_cross_lookback, i)
        crossings_i = 0
        if lb_cr > 1:
            sub_c2 = close[i - lb_cr: i + 1]
            sub_e2 = ema_arr[i - lb_cr: i + 1]
            above_p2 = sub_c2[0] > sub_e2[0]
            for k in range(1, len(sub_c2)):
                if np.isnan(sub_e2[k]):
                    continue
                above_n2 = sub_c2[k] > sub_e2[k]
                if above_n2 != above_p2:
                    crossings_i += 1
                above_p2 = above_n2
        cr_norm_i = float(np.clip(crossings_i / max(cfg.ema_cross_lookback / 5.0, 1.0), 0.0, 1.0))

        lb_ch  = min(cfg.ema_cross_lookback, i)
        sub_ch = close[i - lb_ch: i + 1]
        nm_i   = abs(sub_ch[-1] - sub_ch[0])
        tm_i   = float(np.sum(np.abs(np.diff(sub_ch)))) if len(sub_ch) > 1 else 1.0
        chop_i = float(np.clip(1.0 - nm_i / tm_i, 0.0, 1.0)) if tm_i > 0 else 0.5

        pct_lb_i = min(cfg.atr_percentile_lookback, i + 1)
        atr_pct_i = _percentile_rank(atr_i, atr_arr[i - pct_lb_i + 1: i + 1])

        adx_norm_i = float(np.clip((adx_i - 15.0) / 25.0, 0.0, 1.0))
        trend_sc_i = (cfg.adx_weight * adx_norm_i
                      + cfg.slope_weight * abs(slope_norm_i)
                      + cfg.distance_weight * abs(dist_i))
        chop_sc_i  = 0.5 * cr_norm_i + 0.5 * chop_i
        vol_sc_i   = atr_pct_i / 100.0

        micro = clf._decide_regime(trend_sc_i, chop_sc_i, vol_sc_i, slope_norm_i, atr_pct_i)
        macro = _macro_at(ts_i)

        rows.append({
            "timestamp":    ts_i,
            "regime":       micro,
            "trend_score":  round(trend_sc_i, 4),
            "chop_score":   round(chop_sc_i, 4),
            "vol_score":    round(vol_sc_i, 4),
            "macro_regime": macro,
            "trade_allowed": is_trade_allowed(macro, micro),
        })

    result = pd.DataFrame(rows)
    result.set_index("timestamp", inplace=True)
    return result





