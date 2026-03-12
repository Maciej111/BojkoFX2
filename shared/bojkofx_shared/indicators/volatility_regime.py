"""
volatility_regime.py
====================
Reusable volatility regime filter for algorithmic trading strategies.

Computes a boolean Series indicating whether the current volatility is
above a historical baseline.  Intended as a trade-gating condition that
prevents entering setups during structurally low-volatility environments.

Algorithm (ATR percentile — Option A):
  1. Resample LTF bars to a higher timeframe (default 1h).
  2. Compute ATR(atr_period) on the resampled bars.
  3. For each HTF bar, compute the rolling quantile of the ATR over a
     trailing window of window_days × bars_per_day bars.
  4. The regime is ACTIVE when the current ATR exceeds the
     ``percentile_threshold``-th percentile of the rolling window.
  5. Align the result back to the original LTF index via forward-fill.

Rationale:
  Momentum-breakout strategies like VCLSMB rely on volatility expansion
  after a compression phase.  During globally low-volatility regimes the
  expansion rarely materialises cleanly, leading to false signals.
  Gating entries on an elevated-volatility regime improves signal quality
  without changing the core setup logic.

Usage:
    from bojkofx_shared.indicators.volatility_regime import compute_volatility_regime

    vol_ok: pd.Series = compute_volatility_regime(
        ltf_df,
        htf_freq="1h",
        window_days=20,
        percentile_threshold=40.0,
    )
    # vol_ok is a bool Series, same index as ltf_df.
    # True  → regime active, trading allowed.
    # False → low-volatility regime, no new setups.
"""
from __future__ import annotations

import pandas as pd

from bojkofx_shared.indicators.atr import calculate_atr


def compute_volatility_regime(
    ltf_df: pd.DataFrame,
    htf_freq: str = "1h",
    atr_period: int = 14,
    window_days: int = 20,
    percentile_threshold: float = 40.0,
    bars_per_day: int = 24,
) -> pd.Series:
    """
    Return a boolean pd.Series (LTF-aligned) for the volatility regime.

    Parameters
    ----------
    ltf_df               : LTF bars DataFrame (5m or similar), UTC DatetimeIndex.
    htf_freq             : Pandas resample rule for the higher timeframe (e.g. ``"1h"``).
    atr_period           : Wilder ATR period applied to the HTF bars.
    window_days          : Rolling window length expressed in calendar days.
    percentile_threshold : ATR must exceed this percentile (0–100) of the rolling
                           window to be considered a high-volatility regime.
    bars_per_day         : Number of HTF bars per calendar day (24 for hourly).

    Returns
    -------
    pd.Series of bool, same index as *ltf_df*.
    True  → volatility is elevated, setup generation is allowed.
    False → volatility is suppressed, no new setups.
    """
    # ── 1. Resample LTF → HTF ─────────────────────────────────────────────────
    htf = ltf_df.resample(htf_freq, closed="left", label="left").agg({
        "open_bid":  "first",
        "high_bid":  "max",
        "low_bid":   "min",
        "close_bid": "last",
    }).dropna(how="all")
    htf = htf[htf["open_bid"].notna()]

    # ── 2. ATR on HTF bars ─────────────────────────────────────────────────────
    htf_atr = calculate_atr(htf, period=atr_period)

    # ── 3. Rolling threshold = N-th percentile of the ATR window ──────────────
    # pandas rolling().quantile() is vectorised (C-level), so this is fast even
    # for large windows.
    window = window_days * bars_per_day
    q = percentile_threshold / 100.0
    min_periods = max(atr_period * 2, window // 4)

    rolling_threshold = htf_atr.rolling(window, min_periods=min_periods).quantile(q)

    # ── 4. Regime flag ─────────────────────────────────────────────────────────
    regime_htf = htf_atr > rolling_threshold

    # During warmup (rolling_threshold is NaN), default to True so we do not
    # artificially suppress signals at the very start of any data slice.
    regime_htf = regime_htf.fillna(True)

    # ── 5. Forward-fill back to LTF index ─────────────────────────────────────
    # Merge the HTF boolean values onto the 5m index by aligning timestamps and
    # forward-filling: every 5m bar inherits the regime of the most recent 1h bar.
    combined_index = ltf_df.index.union(regime_htf.index)
    regime_ltf = (
        regime_htf
        .reindex(combined_index)
        .ffill()
        .reindex(ltf_df.index)
    )

    # Any remaining NaN (e.g. LTF bars before the first HTF bar) → allow trading
    regime_ltf = regime_ltf.fillna(True).astype(bool)

    return regime_ltf
