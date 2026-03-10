"""
Tests for partial take-profit + break-even logic.

tests/test_partial_tp_logic.py

Verifies:
  1. TP trades with partial enabled produce R ≈ 1.5 (0.5×1R + 0.5×2R)
  2. TP trades with partial disabled produce R ≈ 2.0 (full R×RR)
  3. SL trades (no partial previously hit) always produce R ≈ -1.0
  4. partial_tp_hit=True trades record partial_exit_price / partial_exit_time
  5. Partial + final TP same bar: exit_reason='TP', partial_tp_hit=True, R≈1.5
  6. Direct SL after partial hit produces R = partial_tp_ratio * partial_tp_rr = 0.5

Run: pytest tests/test_partial_tp_logic.py -v
"""

import pytest
import pandas as pd
import numpy as np

from src.strategies.trend_following_v1 import run_trend_backtest

# ---------------------------------------------------------------------------
# Helpers (mirrors test_idx_session_and_bos_filters.py)
# ---------------------------------------------------------------------------

SPREAD = 2.0


def _make_trending_bars(n: int = 800, freq: str = "5min",
                        start: str = "2024-01-02 14:00",
                        base: float = 19_000.0,
                        atr: float = 50.0) -> pd.DataFrame:
    """
    Synthetic uptrend dataset with step sizes proportional to ATR so that
    BOS events reliably fire with require_close_break=True.
    """
    rng = np.random.default_rng(2024)
    prices = [base]
    for _ in range(1, n):
        # 10x larger steps: +8, +4, -2 — proportional to ATR so close can
        # actually break pivot highs within a reasonable bar window.
        step = rng.choice([+8.0, +4.0, -2.0], p=[0.5, 0.3, 0.2])
        prices.append(round(prices[-1] + step, 2))

    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    rng2 = np.random.default_rng(999)
    bar_range = atr * rng2.uniform(0.5, 2.0, size=n)
    high  = close + bar_range * 0.6
    low   = close - bar_range * 0.4
    open_ = close - bar_range * rng2.uniform(-0.2, 0.2, size=n)

    return pd.DataFrame(
        {
            "open_bid":  open_,
            "high_bid":  high,
            "low_bid":   low,
            "close_bid": close,
            "open_ask":  open_  + SPREAD,
            "high_ask":  high   + SPREAD,
            "low_ask":   low    + SPREAD,
            "close_ask": close  + SPREAD,
            "atr":       atr,
        },
        index=idx,
    )


def _make_bullish_htf(n: int = 240, freq: str = "4h",
                      start: str = "2023-12-01 00:00",
                      base: float = 18_000.0) -> pd.DataFrame:
    """Synthetic bullish HTF dataset — same seed as session-filter tests."""
    rng = np.random.default_rng(42)
    prices = [base]
    for _ in range(1, n):
        step = rng.choice([+200, -80], p=[0.6, 0.4])
        prices.append(round(prices[-1] + step, 2))

    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    high  = close + 150
    low   = close - 150

    return pd.DataFrame(
        {
            "open_bid":  close.shift(1).fillna(close),
            "high_bid":  high,
            "low_bid":   low,
            "close_bid": close,
            "open_ask":  close.shift(1).fillna(close) + SPREAD,
            "high_ask":  high + SPREAD,
            "low_ask":   low  + SPREAD,
            "close_ask": close + SPREAD,
            "atr":       200.0,
        },
        index=idx,
    )


# Shared base params — partial TP OFF by default
BASE_PARAMS = {
    "pivot_lookback_ltf":     3,
    "pivot_lookback_htf":     5,
    "confirmation_bars":      1,
    "require_close_break":    True,
    "entry_offset_atr_mult":  0.0,
    "pullback_max_bars":      30,
    "sl_anchor":              "last_pivot",
    "sl_buffer_atr_mult":     0.5,
    "risk_reward":            2.0,
    "use_session_filter":     False,
    "use_bos_momentum_filter": False,
    # Partial TP disabled — backwards-compat default
    "use_partial_take_profit":    False,
    "partial_tp_ratio":           0.5,
    "partial_tp_rr":              1.0,
    "final_tp_rr":                2.0,
    "move_sl_to_be_after_partial": True,
}


def _run(ltf_df, htf_df, extra_params=None):
    params = {**BASE_PARAMS, **(extra_params or {})}
    trades_df, metrics = run_trend_backtest(
        symbol="TEST",
        ltf_df=ltf_df,
        htf_df=htf_df,
        params_dict=params,
        initial_balance=10_000,
    )
    return trades_df, metrics


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPartialTpBackwardsCompat:
    """Test 1 — partial TP disabled → no behaviour change."""

    def test_partial_tp_off_produces_trades(self):
        """Sanity: backtest runs without error when partial TP is disabled."""
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, metrics = _run(ltf, htf)
        assert isinstance(trades, pd.DataFrame)

    def test_partial_tp_off_full_tp_r_equals_risk_reward(self):
        """
        Test 2 — When partial_tp is OFF, trades exiting with 'TP' should have
        R ≈ risk_reward (2.0), not 1.5.
        """
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": False})

        if len(trades) == 0:
            pytest.skip("No trades generated")
        tp_trades = trades[trades["exit_reason"] == "TP"]
        if len(tp_trades) == 0:
            pytest.skip("No TP trades in this dataset")

        for _, row in tp_trades.iterrows():
            assert abs(row["R"] - 2.0) < 0.05, (
                f"Expected R≈2.0 for full TP trade, got {row['R']:.4f}"
            )

    def test_partial_tp_off_sl_r_equals_minus_one(self):
        """Test 3 — With partial TP off, clean SL trades have R ≈ -1.0."""
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": False})

        if len(trades) == 0:
            pytest.skip("No trades generated")
        sl_trades = trades[trades["exit_reason"] == "SL"]
        if len(sl_trades) == 0:
            pytest.skip("No clean SL trades in this dataset")

        for _, row in sl_trades.iterrows():
            assert abs(row["R"] - (-1.0)) < 0.05, (
                f"Expected R≈-1.0 for clean SL trade, got {row['R']:.4f}"
            )

    def test_partial_tp_field_false_when_disabled(self):
        """Test 4 (partial) — All trades have partial_tp_hit == False when feature off."""
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": False})

        if len(trades) == 0:
            pytest.skip("No trades generated")

        assert (trades["partial_tp_hit"] == False).all(), (
            "partial_tp_hit should be False for all trades when feature is disabled"
        )


class TestPartialTpEnabled:
    """Tests 5-6 — partial TP enabled with default ratio=0.5, rr=1.0, final_rr=2.0."""

    def test_tp_trades_have_r_approx_1_5(self):
        """
        Test 5 — When partial TP is ON and both partial and final TP are hit,
        blended R = 0.5×1.0 + 0.5×2.0 = 1.5.
        """
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": True})

        if len(trades) == 0:
            pytest.skip("No trades generated")
        full_win = trades[
            (trades["exit_reason"] == "TP") & (trades["partial_tp_hit"] == True)
        ]
        if len(full_win) == 0:
            pytest.skip("No partial+full TP trades in dataset")

        expected_R = 0.5 * 1.0 + 0.5 * 2.0  # = 1.5
        for _, row in full_win.iterrows():
            assert abs(row["R"] - expected_R) < 0.05, (
                f"Expected R≈1.5 for partial+final TP trade, got {row['R']:.4f}"
            )

    def test_sl_trades_r_unchanged_at_minus_one(self):
        """
        Test 6 — Direct SL (partial never hit) still gives R ≈ -1.0 with partial TP on.
        """
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": True})

        if len(trades) == 0:
            pytest.skip("No trades generated")
        direct_sl = trades[
            (trades["exit_reason"] == "SL") & (trades["partial_tp_hit"] == False)
        ]
        if len(direct_sl) == 0:
            pytest.skip("No direct SL trades in dataset")

        for _, row in direct_sl.iterrows():
            assert abs(row["R"] - (-1.0)) < 0.05, (
                f"Expected R≈-1.0 for direct SL, got {row['R']:.4f}"
            )

    def test_partial_then_be_stop_r_equals_half(self):
        """
        Test 6b — After partial TP fires, if SL (now at BE) is later hit,
        R = partial_tp_ratio × partial_tp_rr = 0.5 × 1.0 = 0.5.
        """
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {
            "use_partial_take_profit": True,
            "move_sl_to_be_after_partial": True,
        })

        if len(trades) == 0:
            pytest.skip("No trades generated")
        be_stop = trades[trades["exit_reason"] == "SL_after_partial"]
        if len(be_stop) == 0:
            pytest.skip("No SL_after_partial trades in this dataset")

        expected_R = 0.5 * 1.0  # partial_tp_ratio * partial_tp_rr = 0.5
        for _, row in be_stop.iterrows():
            assert abs(row["R"] - expected_R) < 0.05, (
                f"Expected R≈0.5 for SL_after_partial trade, got {row['R']:.4f}"
            )

    def test_partial_hit_records_exit_price_and_time(self):
        """
        Test 4 — Trades with partial_tp_hit=True have non-null partial_exit_price
        and partial_exit_time.
        """
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": True})

        if len(trades) == 0:
            pytest.skip("No trades generated")
        partial_hit = trades[trades["partial_tp_hit"] == True]
        if len(partial_hit) == 0:
            pytest.skip("No partial TP hit trades in dataset")

        assert partial_hit["partial_exit_price"].notna().all(), (
            "partial_exit_price must be non-null for all partial_tp_hit trades"
        )
        assert partial_hit["partial_exit_time"].notna().all(), (
            "partial_exit_time must be non-null for all partial_tp_hit trades"
        )

    def test_partial_tp_max_r_less_than_full_tp(self):
        """
        Test 5b — With partial TP enabled, max R of TP trades (1.5) is lower
        than with partial TP disabled (2.0).
        """
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()

        trades_partial, _ = _run(ltf, htf, {"use_partial_take_profit": True})
        trades_full, _    = _run(ltf, htf, {"use_partial_take_profit": False})

        if len(trades_partial) == 0 or len(trades_full) == 0:
            pytest.skip("No trades generated")
        tp_partial = trades_partial[trades_partial["exit_reason"] == "TP"]
        tp_full    = trades_full[trades_full["exit_reason"] == "TP"]
        if len(tp_partial) == 0 or len(tp_full) == 0:
            pytest.skip("Not enough TP trades to compare")

        max_r_partial = tp_partial["R"].max()
        max_r_full    = tp_full["R"].max()
        assert max_r_partial < max_r_full, (
            f"Partial TP max R ({max_r_partial:.3f}) should be < full TP max R ({max_r_full:.3f})"
        )


class TestPartialTpColumnPresence:
    """Structural tests — verify new columns exist regardless of feature flag."""

    @pytest.mark.parametrize("enabled", [False, True])
    def test_new_columns_present(self, enabled):
        """New partial TP columns must appear regardless of whether the feature is on or off."""
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf, {"use_partial_take_profit": enabled})

        if len(trades) == 0:
            pytest.skip("No trades generated")

        for col in ("partial_tp_hit", "partial_exit_time", "partial_exit_price"):
            assert col in trades.columns, f"Column '{col}' missing (use_partial_take_profit={enabled})"

    def test_produce_trades_sanity(self):
        """Scaled dataset must generate at least 1 trade — sanity for all other tests."""
        ltf = _make_trending_bars()
        htf = _make_bullish_htf()
        trades, _ = _run(ltf, htf)
        assert len(trades) > 0, (
            "No trades generated — synthetic dataset scaling is insufficient."
        )
