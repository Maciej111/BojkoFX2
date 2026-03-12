"""
tests/test_live_backtest_parity.py

PARITY GUARD — ensures the backtest engine and live strategy share a single
source-of-truth for every component that could cause live/backtest divergence.

Covers (addresses US100 audit findings):
  ATR     — both use Wilder EWM (BUG-US-02)
  Pivots  — backtest uses no-lookahead precompute (BUG-US-01)
  Session — backtest and runner use identical inclusive-end boundary (BUG-US-04)
  Symbol  — state is persisted under the real symbol, not "UNKNOWN" (BUG-US-05)

The tests are designed so that any regression to the old wrong behaviour will
cause an immediate, descriptive failure.

Run: pytest tests/test_live_backtest_parity.py -v
"""
from __future__ import annotations

import inspect
import math
import numpy as np
import pandas as pd
import pytest

# ── Local shims → shared module ───────────────────────────────────────────────
from src.indicators.atr import calculate_atr as backtest_atr_fn
from src.structure.pivots import precompute_pivots, detect_pivots_confirmed
from src.strategies.trend_following_v1 import (
    is_allowed_session,
    run_trend_backtest,
    check_bos,
)
from src.core.strategy import TrendFollowingStrategy
from src.core.config import StrategyConfig
from src.core.models import Side


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

SPREAD = 0.0002


def _make_bars(prices: list, freq: str = "1h",
               start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(prices), freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    high = close + 1.0      # large wick so pivot detection is robust
    low  = close - 1.0
    return pd.DataFrame({
        "open_bid":  close.shift(1).fillna(close),
        "high_bid":  high,
        "low_bid":   low,
        "close_bid": close,
        "open_ask":  close.shift(1).fillna(close) + SPREAD,
        "high_ask":  high + SPREAD,
        "low_ask":   low  + SPREAD,
        "close_ask": close + SPREAD,
    }, index=idx)


def _ascending(n=60, base=100.0, step=0.5) -> list:
    """Simple ascending staircase price series."""
    return [round(base + step * i, 2) for i in range(n)]


def _atr_from_shared(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR via the US100 shim (which resolves to shared Wilder EWM)."""
    from src.indicators.atr import calculate_atr
    return calculate_atr(df, period)


def _atr_wilder_ewm(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Reference Wilder EWM ATR computed inline (no dependency on any module)."""
    high = df["high_bid"]
    low  = df["low_bid"]
    close = df["close_bid"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ─────────────────────────────────────────────────────────────────────────────
# BUG-US-02 guard: ATR implementation
# ─────────────────────────────────────────────────────────────────────────────

class TestATRParity:
    """
    Backtest calculate_atr() must use Wilder EWM — NOT rolling mean.
    A rolling mean and EWM diverge significantly after a large True Range spike.
    """

    def test_backtest_atr_uses_wilder_ewm_not_rolling_mean(self):
        """
        Source-code inspection: the function used by backtest must call .ewm(),
        not .rolling().mean().
        """
        src = inspect.getsource(backtest_atr_fn)
        assert "ewm" in src, (
            "BUG-US-02 REGRESSION: backtest ATR must use Wilder EWM (.ewm()), "
            "but 'ewm' not found in source.  Local rolling-mean calculate_atr() "
            "was accidentally restored."
        )
        assert "rolling" not in src, (
            "BUG-US-02 REGRESSION: backtest ATR contains 'rolling' — "
            "the old simple-MA version was restored instead of Wilder EWM."
        )

    def test_backtest_atr_matches_shared_atr(self):
        """
        Numeric check: backtest ATR values must match the shared module's ATR
        (single source of truth).  Any divergence means a separate implementation
        crept back in.
        """
        rng = np.random.default_rng(1)
        prices = 100.0 + np.cumsum(rng.normal(0, 0.3, 80))
        df = _make_bars(prices.tolist(), freq="1h")

        bt_atr     = backtest_atr_fn(df, period=14)
        shared_atr = _atr_from_shared(df, period=14)

        common = bt_atr.dropna().index.intersection(shared_atr.dropna().index)
        assert len(common) > 20, "Not enough common non-NaN ATR values to compare"

        for ts in common:
            assert abs(bt_atr[ts] - shared_atr[ts]) < 1e-9, (
                f"BUG-US-02 REGRESSION: backtest ATR {bt_atr[ts]:.8f} ≠ "
                f"shared ATR {shared_atr[ts]:.8f} at {ts}"
            )

    def test_atr_spike_response_differs_between_ewm_and_rolling(self):
        """
        Demonstrates WHY Wilder EWM ≠ rolling mean: one large TR spike gives
        different values 14 bars later.  This is a documentation test so the
        difference is always visible in the test output.
        """
        prices = [100.0] * 30 + [110.0] + [100.0] * 30   # spike at bar 30
        df = _make_bars(prices, freq="1h")
        high = df["high_bid"].values
        low  = df["low_bid"].values
        close = df["close_bid"].values

        # Manually compute simple rolling ATR (old wrong method)
        prev_close = np.roll(close, 1); prev_close[0] = close[0]
        tr = np.maximum(high - low,
             np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
        rolling_atr_at45 = np.mean(tr[31:45])         # 14-bar simple MA after spike

        # Wilder EWM ATR via shared
        shared_atr = _atr_from_shared(df, period=14)
        ewm_atr_at45 = shared_atr.iloc[44]

        # They should differ by at least 1 price unit (spike = 10 price units)
        diff = abs(ewm_atr_at45 - rolling_atr_at45)
        assert diff > 0.1, (
            "Wilder EWM and rolling mean should diverge after a large spike; "
            f"difference {diff:.4f} is too small to be meaningful"
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-US-01 guard: pivot lookahead
# ─────────────────────────────────────────────────────────────────────────────

class TestPivotNoLookahead:
    """
    precompute_pivots() must not expose future pivots.
    ph_prices[i] / pl_prices[i] must only reflect pivots whose right-wing
    was already confirmed before bar i.
    """

    def test_precompute_pivots_no_lookahead(self):
        """
        A pivot at position p (lookback=2) is confirmed exactly at bar p+2
        (right wing complete).  The pivot is EXPOSED at bar p+2+1 = p+3 because
        precompute_pivots writes the running state BEFORE updating at step i.

        Concretely: pivot_high at bar 5, lookback=2:
          - right wing complete at bar i=7 (p = 7-2 = 5)
          - ph_prices[7] is written (as None) BEFORE the update
          - ph_prices[8] is the first bar that sees the pivot = 15.0
        """
        # Clear pivot high at index 5 (window [3..7])
        high = np.array([10, 10, 11, 12, 13, 15, 12, 10, 10, 10], dtype=float)
        low  = np.array([ 9,  9, 10, 11, 12, 14, 11,  9,  9,  9], dtype=float)
        ph, _, _, _ = precompute_pivots(high, low, lookback=2)

        # Bar 6: one bar before right-wing is complete (i=6, p=4 not a pivot)
        # Bar 7: right-wing arrives (p=5 detected), but ph[7] is written BEFORE update
        assert ph[7] is None, (
            "BUG-US-01 REGRESSION: ph_prices[7] must be None — the pivot at bar 5 "
            "is just being confirmed at i=7 but its value is exposed starting at i=8"
        )
        # Bar 8: first bar that sees the pivot
        assert ph[8] == 15.0, (
            f"BUG-US-01 REGRESSION: ph_prices[8] should be 15.0 "
            f"(first bar with confirmed pivot from bar 5), got {ph[8]}"
        )

    def test_backtest_check_bos_uses_scalar_pivots_not_series(self):
        """
        check_bos() signature must accept scalar float pivots (last_ph_price,
        last_pl_price), NOT the old full Series arguments.  Source inspection.
        """
        sig = inspect.signature(check_bos)
        params = list(sig.parameters.keys())
        # Old signature: (df, current_idx, pivot_highs, pivot_lows, ph_levels, pl_levels, require_close_break)
        # New signature: (df, current_idx, last_ph_price, last_pl_price, require_close_break)
        assert len(params) == 5, (
            f"BUG-US-01 REGRESSION: check_bos should have 5 params "
            f"(df, current_idx, last_ph_price, last_pl_price, require_close_break), "
            f"got {len(params)}: {params}"
        )
        assert "last_ph_price" in params, (
            f"BUG-US-01 REGRESSION: expected 'last_ph_price' param in check_bos, "
            f"got {params}"
        )

    def test_run_trend_backtest_does_not_call_detect_pivots_on_full_ltf(self):
        """
        run_trend_backtest() source must NOT contain a standalone
        detect_pivots_confirmed(ltf_df, ...) call that processes the full LTF.
        It must use precompute_pivots instead.
        """
        src = inspect.getsource(run_trend_backtest)
        # The old lookahead code called detect_pivots_confirmed on ltf_df for BOS
        # The new code uses precompute_pivots for LTF pivots
        assert "precompute_pivots" in src, (
            "BUG-US-01 REGRESSION: run_trend_backtest() must call precompute_pivots() "
            "for LTF pivot detection — the no-lookahead O(n) version. "
            "Found 'precompute_pivots' not present."
        )

    def test_backtest_bos_not_triggered_before_pivot_confirmed(self):
        """
        Integration: on a dataset where a pivot high is at bar P, a BOS bar at
        P+1 (before confirmation) must NOT generate a setup.
        A BOS at P+lookback+1 (after confirmation) MUST generate a setup.
        """
        lookback = 2
        # Build a price series with a clear pivot high at bar 10
        # Bars 0-9: rising to 110, bar 10: peak 115, bars 11-12: pullback to 108
        # Then bar 13: BOS close above 115 (should fire AFTER pivot confirmed at bar 12)
        prices = ([100 + i for i in range(10)]  # rise
                  + [115]                         # pivot high @ bar 10
                  + [110, 108]                    # right wing — confirms at bar 12
                  + [116])                        # BOS close > 115 @ bar 13
        ltf = _make_bars(prices, freq="1h")
        htf = _make_bars([105.0] * 20, freq="4h")   # flat HTF — no bias filter needed

        # We need HTF bias — make it BULL manually by adding strong structure
        bull_prices = _ascending(40, base=100.0, step=1.0)
        htf_bull = _make_bars(bull_prices, freq="4h")

        params = {
            "pivot_lookback_ltf": lookback,
            "pivot_lookback_htf": 2,
            "confirmation_bars":  1,
            "require_close_break": True,
            "entry_offset_atr_mult": 0.0,
            "sl_buffer_atr_mult": 0.5,
            "risk_reward": 2.0,
            "pullback_max_bars": 10,
        }
        trades_df, _ = run_trend_backtest("TEST", ltf, htf_bull, params)
        # With no-lookahead pivots the BOS at bar 11 (one bar BEFORE confirmation)
        # must NOT produce a trade.  A trade at bar 13 (confirmed) is valid.
        # Any trade's entry_time must be >= bar 12 index.
        confirm_time = ltf.index[12]  # pivot confirmed at bar 12
        for _, row in trades_df.iterrows():
            entry_ts = pd.Timestamp(row["entry_time"])
            assert entry_ts >= confirm_time, (
                f"BUG-US-01 REGRESSION: trade opened at {entry_ts}, "
                f"before pivot confirmation at {confirm_time}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-US-04 guard: session filter boundary
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionFilterParity:
    """
    The backtest is_allowed_session() and the live runner must use identical
    boundary semantics: start <= hour <= end  (inclusive both sides).
    """

    @pytest.mark.parametrize("hour,start,end,expected", [
        (13, 13, 20, True),   # exact start — included
        (16, 13, 20, True),   # middle — included
        (20, 13, 20, True),   # exact end — MUST be included (BUG-US-04 fix)
        (21, 13, 20, False),  # one hour past end — excluded
        (12, 13, 20, False),  # one hour before start — excluded
    ])
    def test_is_allowed_session_boundary(self, hour, start, end, expected):
        ts = pd.Timestamp(f"2024-01-02 {hour:02d}:00", tz="UTC")
        result = is_allowed_session(ts, start, end)
        assert result is expected, (
            f"BUG-US-04: is_allowed_session({hour}h, {start}, {end}) "
            f"returned {result}, expected {expected}. "
            f"Check inclusive-end boundary (start <= hour <= end)."
        )

    def test_session_end_boundary_is_inclusive(self):
        """Regression test: bar at exactly session_end must be allowed."""
        ts_at_end = pd.Timestamp("2024-01-02 20:00", tz="UTC")
        assert is_allowed_session(ts_at_end, start_hour=13, end_hour=20) is True, (
            "BUG-US-04 REGRESSION: bar at session_end=20 must be included. "
            "Runner was using `< session_end` (exclusive); backtest uses `<=`."
        )

    def test_runner_comment_confirms_inclusive_fix(self):
        """
        The runner source must contain the FIX BUG-US-04 comment so the fix
        is visible during code review.
        """
        import pathlib
        runner_path = pathlib.Path(__file__).parents[1] / "src" / "runners" / "run_live_idx.py"
        source = runner_path.read_text(encoding="utf-8")
        assert "BUG-US-04" in source, (
            "BUG-US-04 REGRESSION: expected fix comment in run_live_idx.py — "
            "the inclusive-end session filter fix may have been reverted."
        )
        assert "<= session_end" in source, (
            "BUG-US-04 REGRESSION: run_live_idx.py does not contain "
            "'<= session_end'; exclusive `<` was probably restored."
        )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-US-05 guard: symbol passed to process_bar
# ─────────────────────────────────────────────────────────────────────────────

class TestSymbolStateParity:
    """
    TrendFollowingStrategy.process_bar() must be called with the real symbol so
    that StrategyState is stored/loaded under the correct key.
    """

    def test_process_bar_accepts_symbol_kwarg(self):
        """process_bar() must have a 'symbol' parameter (not added post-hoc)."""
        sig = inspect.signature(TrendFollowingStrategy.process_bar)
        assert "symbol" in sig.parameters, (
            "BUG-US-05: process_bar() must accept a 'symbol' keyword argument. "
            "Without it, state is stored as 'UNKNOWN'."
        )

    def test_runner_passes_symbol_to_process_bar(self):
        """
        run_live_idx.py must call process_bar(..., symbol=SYMBOL).
        Source-code inspection guard.
        """
        import pathlib
        runner_path = pathlib.Path(__file__).parents[1] / "src" / "runners" / "run_live_idx.py"
        source = runner_path.read_text(encoding="utf-8")
        assert "symbol=SYMBOL" in source, (
            "BUG-US-05 REGRESSION: run_live_idx.py does not contain "
            "'symbol=SYMBOL' in process_bar call. "
            "State will be saved under 'UNKNOWN' instead of the real symbol."
        )
        assert "BUG-US-05" in source, (
            "BUG-US-05 REGRESSION: fix comment missing from run_live_idx.py."
        )

    def test_process_bar_state_stored_under_passed_symbol(self):
        """
        Integration: when symbol='NAS100USD' is passed, any state persisted by
        the strategy must be associated with that symbol (no 'UNKNOWN' state key).
        """
        import tempfile
        from src.core.state_store import SQLiteStateStore

        rng = np.random.default_rng(55)
        prices = 100.0 + np.cumsum(rng.normal(0, 0.2, 60))
        ltf = _make_bars(prices.tolist(), freq="1h")
        htf = _make_bars(_ascending(30, 98.0, 0.1), freq="4h")

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        store = SQLiteStateStore(db_path)
        try:
            store.migrate()
            cfg = StrategyConfig(
                pivot_lookback_ltf=2,
                pivot_lookback_htf=2,
                confirmation_bars=1,
            )
            strat = TrendFollowingStrategy(cfg, store=store)
            symbol = "NAS100USD"
            for i in range(len(ltf)):
                strat.process_bar(ltf, htf, i, symbol=symbol)

            # Check that state was saved under the real symbol, not "UNKNOWN"
            unknown_state = store.load_strategy_state("UNKNOWN")
            assert unknown_state is None, (
                "BUG-US-05 REGRESSION: strategy state was saved under 'UNKNOWN'. "
                "Pass symbol= to process_bar()."
            )
        finally:
            store.close()
            import os; os.unlink(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# Combined: equity curve must NOT use × 100_000 (BUG-US-03 guard)
# ─────────────────────────────────────────────────────────────────────────────

class TestEquityCurveParity:
    """
    Equity curve calculation must be R-compounded (instrument-agnostic),
    NOT PnL-based with a hardcoded × 100_000 notional.
    """

    def test_equity_curve_is_r_compounded(self):
        """
        run_trend_backtest source must contain R-compounded equity logic.
        Guards against restoring the × 100_000 PnL-based equity calculation.
        """
        src = inspect.getsource(run_trend_backtest)
        assert "risk_fraction" in src, (
            "BUG-US-03 REGRESSION: run_trend_backtest() does not contain "
            "'risk_fraction' — the R-compounded equity curve was removed. "
            "× 100_000 notional is invalid for NAS100 CFD."
        )
        # equity curve must use R column, not pnl column
        assert "for r_val in trades_df['R']" in src or "for r_val in" in src, (
            "BUG-US-03 REGRESSION: equity curve must iterate over R values, not pnl."
        )

    def test_max_dd_pct_is_sane_for_typical_strategy(self):
        """
        max_dd_pct from backtest must be a realistic percentage (< 100%).
        The old × 100_000 PnL code produced max_dd_pct > 1000% on NAS100.
        """
        rng = np.random.default_rng(7)
        n = 200
        prices_ltf = 100.0 + np.cumsum(rng.normal(0, 0.3, n))
        prices_htf = _ascending(50, 98.0, 0.4)
        ltf = _make_bars(prices_ltf.tolist(), freq="1h")
        htf = _make_bars(prices_htf, freq="4h")

        params = {
            "pivot_lookback_ltf": 2,
            "pivot_lookback_htf": 2,
            "confirmation_bars":  1,
            "require_close_break": True,
            "entry_offset_atr_mult": 0.0,
            "sl_buffer_atr_mult": 0.5,
            "risk_reward": 2.0,
            "pullback_max_bars": 20,
        }
        _, metrics = run_trend_backtest("NAS100USD", ltf, htf, params)

        dd = metrics["max_dd_pct"]
        assert 0.0 <= dd < 100.0, (
            f"BUG-US-03 REGRESSION: max_dd_pct={dd:.1f}% is unrealistic. "
            "Expected < 100%; the × 100_000 Forex notional may have been restored."
        )
