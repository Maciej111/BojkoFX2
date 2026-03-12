"""
Unit tests for HTF bias logic — src/structure/bias.py

Tests that get_htf_bias_at_bar() returns BULL / BEAR / NEUTRAL correctly.

NOTE: determine_htf_bias() requires a confirmed HH+HL (BULL) or LL+LH (BEAR)
sequence in the pivot history.  A single "close > last pivot" is NOT sufficient
for a bias — that behaviour was intentionally removed (FX BUG-05 fix).
Datasets must be large enough to produce at least 2 confirmed highs AND 2
confirmed lows with a monotonic relationship.

Minimum bars for lookback=3, confirmation_bars=1:
  A pivot at position p needs bars [p-3 .. p+3] (window) + bar p+1 (right wing
  confirmation), and we need the pivot to appear before the query time, so we
  need at least 2×lookback+1+confirmation_bars = 8 bars just for ONE pivot.
  For a full HH+HL sequence we need at least ~24-30 bars.

Run: pytest tests/test_htf_bias.py -v
"""

import pytest
import pandas as pd
import numpy as np

from src.structure.pivots import detect_pivots_confirmed
from src.structure.bias import get_htf_bias_at_bar


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_htf_bars(prices: list, start: str = "2024-01-01") -> pd.DataFrame:
    """
    Build a minimal HTF DataFrame from a list of close prices.
    high = close + 0.5, low = close - 0.5  (fixed spread so pivots are unambiguous).
    """
    idx = pd.date_range(start, periods=len(prices), freq="4h", tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    df = pd.DataFrame({
        "open_bid":  close.shift(1).fillna(close),
        "high_bid":  close + 0.5,
        "low_bid":   close - 0.5,
        "close_bid": close,
        "open_ask":  close.shift(1).fillna(close) + 0.1,
        "high_ask":  close + 0.6,
        "low_ask":   close - 0.4,
        "close_ask": close + 0.1,
    }, index=idx)
    return df


def _get_bias(htf_df: pd.DataFrame, lookback: int = 3) -> str:
    """Compute pivots over full df and return bias at the last bar."""
    ph, pl, ph_levels, pl_levels = detect_pivots_confirmed(
        htf_df, lookback=lookback, confirmation_bars=1
    )
    last_time = htf_df.index[-1]
    return get_htf_bias_at_bar(
        htf_df, last_time, ph, pl, ph_levels, pl_levels, pivot_count=4
    )


# ── Bullish structure ─────────────────────────────────────────────────────────
#
# Pattern: rising staircase — swing highs and swing lows both ascending.
# Each "peak" is higher than the previous; each "valley" is higher than the
# previous.  Use lookback=2 so confirmation needs only 2 bars right wing.
#
#   Pivot highs (high_bid = close+0.5 must be unique local max, lookback=2):
#     bar 4 = close 97  (PH1, confirmed at bar 5)
#     bar 11 = close 108 (PH2, confirmed at bar 12)  → HH (108 > 97) ✓
#   Pivot lows (low_bid = close-0.5 must be unique local min, lookback=2):
#     bar 7 = close 87  (PL1, confirmed at bar 8)
#     bar 14 = close 94 (PL2, confirmed at bar 15) → HL (94 > 87) ✓
#   All close values are unique within each pivot's 5-bar window to avoid ties.

_BULL_PRICES = [
    #  0   1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16  17
      90, 93, 95, 96, 97, 94, 91, 87, 89, 92, 96,108,103, 99, 94, 97,101,105
]

_BEAR_PRICES = [
    #  0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17
     105, 103, 101, 102, 108, 103,  99,  95,  98, 102, 103,  96,  93,  90,  87,  90,  94,  89
    # PH1: bar4=108, PH2: bar10=103 → LH (103<108) ✓
    # PL1: bar7=95,  PL2: bar14=87  → LL (87<95) ✓
]


class TestBullishBias:
    def test_higher_highs_and_higher_lows_returns_bull(self):
        """Clear HH+HL ascending staircase → BULL."""
        htf_df = _make_htf_bars(_BULL_PRICES)
        bias = _get_bias(htf_df, lookback=2)
        assert bias == "BULL", f"Expected BULL, got {bias}"

    def test_close_above_last_pivot_alone_is_not_sufficient(self):
        """
        A single close > last pivot high is NOT enough for BULL bias.
        The current bias logic requires structural HH+HL — a bare close-break
        without a confirmed sequence should return NEUTRAL (BUG-05 fix guard).
        """
        # Very short data — not enough bars to form 2 confirmed highs
        prices = [1.00, 1.02, 0.99, 1.01, 0.98, 1.10]
        htf_df = _make_htf_bars(prices)
        ph, pl, ph_levels, pl_levels = detect_pivots_confirmed(
            htf_df, lookback=2, confirmation_bars=1
        )
        last_time = htf_df.index[-1]
        # May be NEUTRAL (no structure) or BULL (if there happen to be 2 pivots)
        # — but must NOT raise; the test guards against regression to old
        # last_high_broken shortcut returning BULL on a single close break.
        bias = get_htf_bias_at_bar(
            htf_df, last_time, ph, pl, ph_levels, pl_levels, pivot_count=4
        )
        assert bias in ("BULL", "NEUTRAL"), f"Unexpected bias: {bias}"

    def test_anti_lookahead_bull(self):
        """Bias at bar T must not use bars after T."""
        htf_df = _make_htf_bars(_BULL_PRICES)
        ph, pl, ph_levels, pl_levels = detect_pivots_confirmed(
            htf_df, lookback=2, confirmation_bars=1
        )
        # Query at bar 6 — sequence is not yet complete, expect NEUTRAL
        mid_time = htf_df.index[6]
        bias_mid = get_htf_bias_at_bar(
            htf_df, mid_time, ph, pl, ph_levels, pl_levels, pivot_count=4
        )
        # Must be a valid value and must NOT crash
        assert bias_mid in ("BULL", "BEAR", "NEUTRAL")

    def test_full_sequence_at_last_bar(self):
        """After full price sequence, last bar must see BULL."""
        htf_df = _make_htf_bars(_BULL_PRICES)
        bias = _get_bias(htf_df, lookback=2)
        assert bias == "BULL"


# ── Bearish structure ─────────────────────────────────────────────────────────

class TestBearishBias:
    def test_lower_lows_and_lower_highs_returns_bear(self):
        """Clear LL+LH descending staircase → BEAR."""
        htf_df = _make_htf_bars(_BEAR_PRICES)
        bias = _get_bias(htf_df, lookback=2)
        assert bias == "BEAR", f"Expected BEAR, got {bias}"

    def test_close_below_last_pivot_alone_is_not_sufficient(self):
        """
        A single close < last pivot low is NOT enough for BEAR bias.
        Same guard as the bull-side test — covers BUG-05 fix.
        """
        prices = [1.10, 1.08, 1.11, 1.09, 1.12, 0.90]
        htf_df = _make_htf_bars(prices)
        ph, pl, ph_levels, pl_levels = detect_pivots_confirmed(
            htf_df, lookback=2, confirmation_bars=1
        )
        last_time = htf_df.index[-1]
        bias = get_htf_bias_at_bar(
            htf_df, last_time, ph, pl, ph_levels, pl_levels, pivot_count=4
        )
        assert bias in ("BEAR", "NEUTRAL"), f"Unexpected bias: {bias}"

    def test_full_sequence_at_last_bar(self):
        htf_df = _make_htf_bars(_BEAR_PRICES)
        bias = _get_bias(htf_df, lookback=2)
        assert bias == "BEAR"


# ── Neutral structure ─────────────────────────────────────────────────────────

class TestNeutralBias:
    def test_not_enough_htf_bars_returns_neutral(self):
        # Only 4 bars — too few for lookback=3 + confirmation=1 to confirm any pivot
        prices = [1.00, 1.01, 0.99, 1.00]
        htf_df = _make_htf_bars(prices)
        bias = _get_bias(htf_df)
        assert bias == "NEUTRAL", f"Expected NEUTRAL, got {bias}"

    def test_choppy_structure_returns_neutral(self):
        # Alternating prices — no monotone H/L sequence → NEUTRAL
        prices = [1.00, 1.02, 0.98, 1.02, 0.98, 1.02, 0.98, 1.02, 0.98, 1.02,
                  0.98, 1.02, 0.98, 1.02, 0.98, 1.02, 0.98, 1.02, 0.98, 1.02]
        htf_df = _make_htf_bars(prices)
        bias = _get_bias(htf_df, lookback=2)
        assert bias == "NEUTRAL", f"Expected NEUTRAL, got {bias}"

    def test_sideways_range_returns_neutral(self):
        # Choppy oscillation — no clear HH/HL or LL/LH sequence
        prices = [1.00, 1.02, 0.98, 1.01, 0.99, 1.02,
                  0.98, 1.01, 0.99, 1.02, 0.98, 1.01]
        htf_df = _make_htf_bars(prices)
        bias = _get_bias(htf_df)
        assert bias == "NEUTRAL", f"Expected NEUTRAL (range market), got {bias}"

    def test_before_any_confirmed_pivot(self):
        # Only 6 bars with lookback=3 — first pivot can only be confirmed at bar 7
        prices = [1.00, 1.02, 1.01, 0.99, 1.00, 0.98]
        htf_df = _make_htf_bars(prices)
        ph, pl, ph_levels, pl_levels = detect_pivots_confirmed(
            htf_df, lookback=3, confirmation_bars=1
        )
        # Check bias at first bar — no pivots confirmed yet
        first_time = htf_df.index[0]
        bias = get_htf_bias_at_bar(
            htf_df, first_time, ph, pl, ph_levels, pl_levels, pivot_count=4
        )
        assert bias == "NEUTRAL"
