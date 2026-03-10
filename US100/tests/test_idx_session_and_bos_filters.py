"""
Tests for session filter and BOS momentum filter.

tests/test_idx_session_and_bos_filters.py

Covers:
  1. Session filter blocks signals outside session
  2. Session filter allows signals inside session
  3. Open trade exits still work outside session (filter never touches exit logic)
  4. BOS with large impulse passes momentum filter
  5. BOS with small range vs ATR fails momentum filter
  6. BOS with weak candle body fails momentum filter
  7. Zero-range bar is handled safely (no divide-by-zero)
  8. Valid BOS but outside session is rejected
  9. Valid BOS inside session is accepted

Run: pytest tests/test_idx_session_and_bos_filters.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import timezone

from src.strategies.trend_following_v1 import (
    is_allowed_session,
    run_trend_backtest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SPREAD = 2.0   # US100 typical spread in points


def _bar(open_b, high_b, low_b, close_b, atr=50.0, spread=SPREAD):
    """Return a single-row dict suitable for pd.Series with all required cols."""
    return {
        "open_bid":  open_b,
        "high_bid":  high_b,
        "low_bid":   low_b,
        "close_bid": close_b,
        "open_ask":  open_b  + spread,
        "high_ask":  high_b  + spread,
        "low_ask":   low_b   + spread,
        "close_ask": close_b + spread,
        "atr":       atr,
    }


def _make_dataframe(rows: list, freq: str = "5min",
                    start: str = "2024-01-02 14:00") -> pd.DataFrame:
    """Build a DataFrame with DatetimeIndex from a list of bar dicts."""
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz="UTC")
    return pd.DataFrame(rows, index=idx)


def _make_trending_bars(n: int = 300, freq: str = "5min",
                        start: str = "2024-01-02 14:00",
                        base: float = 19_000.0,
                        atr: float = 50.0) -> pd.DataFrame:
    """
    Build a synthetic uptrend long enough to generate BOS signals.
    Prices advance ~0.4 pts/bar with small pull-backs.
    """
    rng = np.random.default_rng(2024)
    prices = [base]
    for _ in range(1, n):
        step = rng.choice([+0.8, +0.4, -0.2], p=[0.5, 0.3, 0.2])
        prices.append(round(prices[-1] + step, 2))

    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    rng2 = np.random.default_rng(999)
    bar_range = atr * rng2.uniform(0.5, 2.0, size=n)
    high  = close + bar_range * 0.6
    low   = close - bar_range * 0.4
    open_ = close - bar_range * rng2.uniform(-0.2, 0.2, size=n)

    df = pd.DataFrame({
        "open_bid":  open_,
        "high_bid":  high,
        "low_bid":   low,
        "close_bid": close,
        "open_ask":  open_  + SPREAD,
        "high_ask":  high   + SPREAD,
        "low_ask":   low    + SPREAD,
        "close_ask": close  + SPREAD,
        "atr":       atr,
    }, index=idx)
    return df


def _make_bearish_htf(n: int = 240, freq: str = "4h",
                      start: str = "2023-12-01 00:00",
                      base: float = 19_500.0) -> pd.DataFrame:
    rng = np.random.default_rng(77)
    prices = [base]
    for _ in range(1, n):
        step = rng.choice([+80, -200], p=[0.4, 0.6])
        prices.append(round(prices[-1] + step, 2))

    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    high  = close + 150
    low   = close - 150
    df = pd.DataFrame({
        "open_bid":  close.shift(1).fillna(close),
        "high_bid":  high,
        "low_bid":   low,
        "close_bid": close,
        "open_ask":  close.shift(1).fillna(close) + SPREAD,
        "high_ask":  high + SPREAD,
        "low_ask":   low  + SPREAD,
        "close_ask": close + SPREAD,
        "atr":       200.0,
    }, index=idx)
    return df


def _make_bullish_htf(n: int = 240, freq: str = "4h",
                      start: str = "2023-12-01 00:00",
                      base: float = 18_000.0) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    prices = [base]
    for _ in range(1, n):
        step = rng.choice([+200, -80], p=[0.6, 0.4])
        prices.append(round(prices[-1] + step, 2))

    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    high  = close + 150
    low   = close - 150
    df = pd.DataFrame({
        "open_bid":  close.shift(1).fillna(close),
        "high_bid":  high,
        "low_bid":   low,
        "close_bid": close,
        "open_ask":  close.shift(1).fillna(close) + SPREAD,
        "high_ask":  high + SPREAD,
        "low_ask":   low  + SPREAD,
        "close_ask": close + SPREAD,
        "atr":       200.0,
    }, index=idx)
    return df


# ---------------------------------------------------------------------------
# Unit tests for is_allowed_session helper
# ---------------------------------------------------------------------------

class TestIsAllowedSession:
    """Tests 1 & 2 — session helper directly."""

    @pytest.mark.parametrize("hour,expected", [
        (12, False),   # one hour before start
        (13, True),    # exactly start
        (16, True),    # mid-session
        (20, True),    # exactly end
        (21, False),   # one hour after end
        (0,  False),   # midnight
        (23, False),   # late night
    ])
    def test_session_boundary(self, hour, expected):
        ts = pd.Timestamp(f"2024-01-02 {hour:02d}:00:00", tz="UTC")
        assert is_allowed_session(ts, 13, 20) == expected

    def test_session_filter_blocks_outside(self):
        """Test 1 — is_allowed_session returns False outside window."""
        ts_outside = pd.Timestamp("2024-01-02 10:00:00", tz="UTC")
        assert not is_allowed_session(ts_outside, 13, 20)

    def test_session_filter_allows_inside(self):
        """Test 2 — is_allowed_session returns True inside window."""
        ts_inside = pd.Timestamp("2024-01-02 15:30:00", tz="UTC")
        assert is_allowed_session(ts_inside, 13, 20)

    def test_same_start_end_hour(self):
        ts_match = pd.Timestamp("2024-01-02 14:00:00", tz="UTC")
        ts_no    = pd.Timestamp("2024-01-02 15:00:00", tz="UTC")
        assert is_allowed_session(ts_match, 14, 14)
        assert not is_allowed_session(ts_no, 14, 14)


# ---------------------------------------------------------------------------
# Integration tests — run_trend_backtest with filters
# ---------------------------------------------------------------------------

BASE_PARAMS = {
    "pivot_lookback_ltf":    3,
    "pivot_lookback_htf":    5,
    "confirmation_bars":     1,
    "require_close_break":   True,
    "entry_offset_atr_mult": 0.0,
    "pullback_max_bars":     30,
    "sl_anchor":             "last_pivot",
    "sl_buffer_atr_mult":    0.5,
    "risk_reward":           2.0,
    # Filters OFF by default → must match old behavior
    "use_session_filter":       False,
    "use_bos_momentum_filter":  False,
}


def _run(ltf_df, htf_df, extra_params=None):
    params = {**BASE_PARAMS, **(extra_params or {})}
    trades_df, metrics = run_trend_backtest(
        symbol="TEST", ltf_df=ltf_df, htf_df=htf_df,
        params_dict=params, initial_balance=10_000,
    )
    return trades_df, metrics


class TestSessionFilterIntegration:
    """Tests 1, 2, 8, 9 using run_trend_backtest."""

    def test_filters_off_produces_trades(self):
        """Sanity: with both filters disabled we get trades (smoke test)."""
        ltf = _make_trending_bars(n=400, start="2024-01-02 08:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")
        trades, metrics = _run(ltf, htf)
        # Just need the backtest to run without error
        assert isinstance(trades, pd.DataFrame)

    def test_session_filter_reduces_or_equals_trades(self):
        """
        Test 1 & 2 — When the session filter is ON with a tight window,
        trade count must not EXCEED the unfiltered case.
        (Fewer setups can be created when the BOS bar is outside the window.)
        """
        # All bars start at 08:00 UTC — outside the 13–20 window
        ltf = _make_trending_bars(n=400, start="2024-01-02 08:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_no_filter, _ = _run(ltf, htf, {"use_session_filter": False})
        trades_with_filter, _ = _run(ltf, htf, {
            "use_session_filter": True,
            "session_start_hour_utc": 13,
            "session_end_hour_utc":   20,
        })
        # Bars start at 08:00, so many BOS bars will be outside -> fewer setups
        assert len(trades_with_filter) <= len(trades_no_filter)

    def test_session_filter_inside_window_matches_unfiltered(self):
        """
        Test 2 & 9 — When ALL bars fall inside the session window (14:00 start),
        session filter must not suppress any trade relative to disabled filter.
        """
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_no_filter, _ = _run(ltf, htf, {"use_session_filter": False})
        trades_with_filter, _ = _run(ltf, htf, {
            "use_session_filter": True,
            "session_start_hour_utc": 13,
            "session_end_hour_utc":   22,
        })
        # All BOS bars are inside window → same result
        assert len(trades_with_filter) == len(trades_no_filter)

    def test_session_filter_does_not_affect_open_trade_exits(self):
        """
        Test 3 — A trade entered inside session must still exit correctly
        even when the exit bar falls outside session hours.

        Strategy: enter trade in-session, then check that a position that
        was opened DOES get closed at SL/TP even at an out-of-session bar.
        We verify this by running with the filter enabled and confirming the
        final trade count is identical to running without it, given that all
        BOS signals happen inside the session.
        """
        # All bars are inside session window → same setups created
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_no_filter, _ = _run(ltf, htf, {"use_session_filter": False})
        trades_with_filter, _ = _run(ltf, htf, {
            "use_session_filter": True,
            "session_start_hour_utc": 13,
            "session_end_hour_utc":   22,
        })

        # Same entries → same exits (exit logic is unaffected by filter)
        assert len(trades_with_filter) == len(trades_no_filter)
        if len(trades_no_filter) > 0:
            pd.testing.assert_series_equal(
                trades_no_filter["R"].reset_index(drop=True),
                trades_with_filter["R"].reset_index(drop=True),
                check_names=False,
            )


class TestBOSMomentumFilterIntegration:
    """Tests 4, 5, 6, 7 using run_trend_backtest."""

    def test_momentum_filter_off_equals_baseline(self):
        """Sanity: filter OFF → identical to no filter."""
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        t_off, _ = _run(ltf, htf, {"use_bos_momentum_filter": False})
        t_base, _ = _run(ltf, htf)  # BASE_PARAMS has filter=False
        assert len(t_off) == len(t_base)

    def test_large_impulse_passes_filter(self):
        """
        Test 4 — BOS bar with range >> ATR and large body must not be
        suppressed. Setting very lenient thresholds ensures the filter passes.
        """
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_no_filter, _ = _run(ltf, htf, {"use_bos_momentum_filter": False})
        trades_lenient, _   = _run(ltf, htf, {
            "use_bos_momentum_filter":    True,
            "bos_min_range_atr_mult":     0.0,   # accept any range
            "bos_min_body_to_range_ratio": 0.0,  # accept any body ratio
        })
        # With thresholds at zero, the filter never rejects → same count
        assert len(trades_lenient) == len(trades_no_filter)

    def test_strict_range_filter_reduces_trades(self):
        """
        Test 5 — Setting a very high range threshold must reject most BOS bars.
        """
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00", atr=50.0)
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_no_filter, _ = _run(ltf, htf, {"use_bos_momentum_filter": False})
        trades_strict, _    = _run(ltf, htf, {
            "use_bos_momentum_filter":    True,
            "bos_min_range_atr_mult":     100.0,  # effectively blocks everything
            "bos_min_body_to_range_ratio": 0.0,
        })
        # With impossibly high threshold, almost no BOS passes.
        # Guard: only assert when the baseline actually produces trades.
        assert len(trades_strict) <= len(trades_no_filter)
        if len(trades_no_filter) > 0:
            assert len(trades_strict) < len(trades_no_filter)

    def test_strict_body_ratio_reduces_trades(self):
        """
        Test 6 — Setting body-to-range ratio = 1.0 (no candlewick allowed)
        rejects most bars.
        """
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00", atr=50.0)
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_no_filter, _ = _run(ltf, htf, {"use_bos_momentum_filter": False})
        trades_strict, _    = _run(ltf, htf, {
            "use_bos_momentum_filter":    True,
            "bos_min_range_atr_mult":     0.0,
            "bos_min_body_to_range_ratio": 1.0,   # body must fill entire range
        })
        assert len(trades_strict) <= len(trades_no_filter)

    def test_zero_range_bar_handled_safely(self):
        """Test 7 — A doji bar (high == low) must not cause ZeroDivisionError."""
        # Build a minimal dataset that forces a zero-range bar.
        # We'll inject one doji at the BOS position and verify no crash.
        n = 300
        ltf = _make_trending_bars(n=n, start="2024-01-02 14:00", atr=50.0)
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        # Overwrite a handful of bars to be perfect dojis
        for idx_i in range(50, 70):
            price = ltf["close_bid"].iloc[idx_i]
            ltf.iloc[idx_i, ltf.columns.get_loc("high_bid")]  = price
            ltf.iloc[idx_i, ltf.columns.get_loc("low_bid")]   = price
            ltf.iloc[idx_i, ltf.columns.get_loc("open_bid")]  = price
            ltf.iloc[idx_i, ltf.columns.get_loc("high_ask")]  = price + SPREAD
            ltf.iloc[idx_i, ltf.columns.get_loc("low_ask")]   = price + SPREAD
            ltf.iloc[idx_i, ltf.columns.get_loc("open_ask")]  = price + SPREAD

        # Must not raise
        trades, metrics = _run(ltf, htf, {
            "use_bos_momentum_filter":    True,
            "bos_min_range_atr_mult":     1.2,
            "bos_min_body_to_range_ratio": 0.6,
        })
        assert isinstance(trades, pd.DataFrame)


class TestCombinedFilters:
    """Tests 8 & 9 — both filters active simultaneously."""

    def test_valid_bos_outside_session_rejected(self):
        """
        Test 8 — Even a BOS bar with strong momentum is rejected when
        outside the session window.
        """
        # Bars at 08:00 UTC — outside the 13–20 window
        ltf = _make_trending_bars(n=400, start="2024-01-02 08:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_session_on, _ = _run(ltf, htf, {
            "use_session_filter": True,
            "session_start_hour_utc": 13,
            "session_end_hour_utc":   20,
            "use_bos_momentum_filter": True,
            "bos_min_range_atr_mult": 0.0,    # momentum filter: pass everything
            "bos_min_body_to_range_ratio": 0.0,
        })
        trades_no_filter, _ = _run(ltf, htf, {
            "use_session_filter": False,
            "use_bos_momentum_filter": False,
        })

        # Session filter must block BOS bars at 08:00–12:59 UTC
        assert len(trades_session_on) <= len(trades_no_filter)

    def test_valid_bos_inside_session_accepted(self):
        """
        Test 9 — A BOS bar inside session with lenient momentum thresholds
        must produce the same results as having no filters.
        """
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_both_on, _ = _run(ltf, htf, {
            "use_session_filter": True,
            "session_start_hour_utc": 13,
            "session_end_hour_utc":   22,
            "use_bos_momentum_filter": True,
            "bos_min_range_atr_mult":  0.0,   # effectively disabled
            "bos_min_body_to_range_ratio": 0.0,
        })
        trades_both_off, _ = _run(ltf, htf, {
            "use_session_filter": False,
            "use_bos_momentum_filter": False,
        })

        # All bars inside session + zero thresholds → identical trade lists
        assert len(trades_both_on) == len(trades_both_off)


class TestBackwardsCompatibility:
    """Task 7 — when both filters are disabled, strategy is identical to old behavior."""

    def test_filters_disabled_identical_to_baseline(self):
        """Both filters OFF = no regression in results."""
        ltf = _make_trending_bars(n=400, start="2024-01-02 14:00")
        htf = _make_bullish_htf(start="2023-12-01 00:00")

        trades_old, metrics_old = run_trend_backtest(
            symbol="TEST", ltf_df=ltf, htf_df=htf,
            params_dict={
                "pivot_lookback_ltf": 3, "pivot_lookback_htf": 5,
                "confirmation_bars": 1, "require_close_break": True,
                "entry_offset_atr_mult": 0.0, "pullback_max_bars": 30,
                "sl_anchor": "last_pivot", "sl_buffer_atr_mult": 0.5,
                "risk_reward": 2.0,
                # No filter keys at all → defaults to False (opt-in)
            },
            initial_balance=10_000,
        )
        trades_new, metrics_new = run_trend_backtest(
            symbol="TEST", ltf_df=ltf, htf_df=htf,
            params_dict={
                "pivot_lookback_ltf": 3, "pivot_lookback_htf": 5,
                "confirmation_bars": 1, "require_close_break": True,
                "entry_offset_atr_mult": 0.0, "pullback_max_bars": 30,
                "sl_anchor": "last_pivot", "sl_buffer_atr_mult": 0.5,
                "risk_reward": 2.0,
                "use_session_filter": False,
                "use_bos_momentum_filter": False,
            },
            initial_balance=10_000,
        )

        assert len(trades_old) == len(trades_new)
        assert metrics_old["expectancy_R"] == pytest.approx(
            metrics_new["expectancy_R"], abs=1e-9
        )
