"""
Tests for VolatilityContractionLiquiditySweepMomentumBreakout strategy.

Reuses:
  - Synthetic bar factory pattern from tests/test_strategy_end_to_end.py
  - project venv (pytest already installed)

Run from US100/ root:
    pytest strategies/VolatilityContractionLiquiditySweepMomentumBreakout/tests/ -v

No external data files required — all tests use synthetic bars.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

# Make the US100 package importable when running from the strategy dir
_US100 = Path(__file__).resolve().parents[3]
_SHARED = _US100.parent / "shared"
for _p in [str(_US100), str(_SHARED)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.config import VCLSMBConfig
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.feature_pipeline import build_features
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.detectors import (
    is_compression, is_liquidity_sweep_bull, is_liquidity_sweep_bear,
    is_momentum_breakout_bull, is_momentum_breakout_bear,
)
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.state_machine import (
    MachineContext, State, advance, _reset,
)
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.risk_management import (
    compute_trade_levels,
)
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.strategy import (
    run_vclsmb_backtest,
)


# ── Synthetic data helper ─────────────────────────────────────────────────────

SPREAD = 0.5  # bid/ask half-spread in points

def _make_bars(
    close_prices: list,
    high_offset: float = 2.0,
    low_offset:  float = 2.0,
    freq: str = "5min",
    start: str = "2023-01-02 14:00",
) -> pd.DataFrame:
    """
    Build minimal LTF DataFrame with bid/ask OHLC from a list of close prices.
    open = prev_close, high = close + high_offset, low = close - low_offset.
    """
    n = len(close_prices)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = np.array(close_prices, dtype=float)
    open_ = np.roll(close, 1); open_[0] = close[0]
    high  = close + high_offset
    low   = close - low_offset

    df = pd.DataFrame({
        "open_bid":  open_  - SPREAD,
        "high_bid":  high   - SPREAD,
        "low_bid":   low    - SPREAD,
        "close_bid": close  - SPREAD,
        "open_ask":  open_  + SPREAD,
        "high_ask":  high   + SPREAD,
        "low_ask":   low    + SPREAD,
        "close_ask": close  + SPREAD,
    }, index=idx)
    return df


def _make_compression_then_sweep_bull(n_compress=30, n_setup=5) -> pd.DataFrame:
    """
    Phase 1: flat, low-ATR range (compression)
    Phase 2: big bull wick sweep below range then close back inside
    Phase 3: strong bull breakout bar
    """
    rng = np.random.default_rng(42)
    # Compression: tight range around 10000
    compress = 10000 + rng.uniform(-3, 3, n_compress)
    # Sweep bar: wick way below, close back inside range
    sweep_close = 9999.0   # back inside [9997, 10003] approx range
    # Breakout bar: strong bull
    breakout_close = 10010.0

    prices = list(compress) + [sweep_close, breakout_close] + [10010 + i * 0.5 for i in range(n_setup)]
    # For sweep bar: need an explicit low far below range
    df = _make_bars(prices, high_offset=2.0, low_offset=2.0)
    # Manually set sweep bar wick to be far below range_low
    sweep_idx = n_compress
    df.iloc[sweep_idx, df.columns.get_loc("low_bid")]  = 9985.0   # 15+ pts below range
    df.iloc[sweep_idx, df.columns.get_loc("low_ask")]  = 9985.5
    # Breakout bar: close high, large body, low not reaching down
    bo_idx = n_compress + 1
    df.iloc[bo_idx, df.columns.get_loc("close_bid")]  = 10012.0
    df.iloc[bo_idx, df.columns.get_loc("close_ask")]  = 10013.0
    df.iloc[bo_idx, df.columns.get_loc("high_bid")]   = 10015.0
    df.iloc[bo_idx, df.columns.get_loc("open_bid")]   = 10001.0
    df.iloc[bo_idx, df.columns.get_loc("open_ask")]   = 10001.5
    return df


# ── Feature pipeline tests ────────────────────────────────────────────────────

class TestFeaturePipeline:
    def test_atr_column_added(self):
        df = _make_bars([10000 + i for i in range(50)])
        cfg = VCLSMBConfig(atr_period=14)
        out = build_features(df, cfg)
        assert "atr" in out.columns
        assert out["atr"].iloc[-1] > 0

    def test_range_high_low_no_lookahead(self):
        """range_high/low on bar i must not use bar i's own price."""
        df = _make_bars([10000.0] * 40)
        cfg = VCLSMBConfig(range_window=5, compression_lookback=20)
        out = build_features(df, cfg)
        # Inject a huge spike on bar 30 — range_high on bar 30 must NOT contain it
        df2 = df.copy()
        df2.iloc[30, df2.columns.get_loc("high_bid")] = 99999.0
        out2 = build_features(df2, cfg)
        assert out2["range_high"].iloc[30] == pytest.approx(out["range_high"].iloc[30], rel=1e-6)

    def test_original_not_mutated(self):
        df = _make_bars([10000 + i for i in range(50)])
        cols_before = set(df.columns)
        _ = build_features(df, VCLSMBConfig())
        assert set(df.columns) == cols_before


# ── Detector tests ────────────────────────────────────────────────────────────

class TestDetectors:
    def _compressed_row(self, cfg):
        """Build a synthetic row that triggers is_compression."""
        atr = 5.0
        # roll_max = 20.0 → ratio = 5/20 = 0.25 << 0.6 threshold → clearly compressed
        return pd.Series({
            "atr": atr,
            "atr_rolling_max": 20.0,
            "low_bid": 9998.0, "high_bid": 10002.0, "close_bid": 10000.0,
            "range_high": 10003.0, "range_low": 9997.0,
            "bar_body": 2.0, "bar_range": 4.0, "bar_body_ratio": 0.5,
        })

    def test_is_compression_true(self):
        cfg = VCLSMBConfig(compression_atr_ratio=0.6)
        row = self._compressed_row(cfg)
        assert is_compression(row, cfg)

    def test_is_compression_false_when_atr_high(self):
        cfg = VCLSMBConfig(compression_atr_ratio=0.6)
        row = pd.Series({"atr": 10.0, "atr_rolling_max": 10.0})
        # ratio = 1.0 > 0.6
        assert not is_compression(row, cfg)

    def test_is_compression_nan_safe(self):
        cfg = VCLSMBConfig()
        row = pd.Series({"atr": float("nan"), "atr_rolling_max": 10.0})
        assert not is_compression(row, cfg)

    def test_bull_sweep_detected(self):
        cfg = VCLSMBConfig(sweep_atr_mult=0.3, sweep_close_inside=True)
        atr = 10.0
        range_low = 9997.0
        row = pd.Series({
            "atr": atr,
            "range_low": range_low,
            "low_bid":   range_low - 0.4 * atr - 0.1,   # wick of 4.1 pts, > 0.3*10=3
            "close_bid": range_low + 0.5,                 # closes back inside
        })
        assert is_liquidity_sweep_bull(row, cfg)

    def test_bull_sweep_not_triggered_if_close_outside(self):
        cfg = VCLSMBConfig(sweep_atr_mult=0.3, sweep_close_inside=True)
        atr = 10.0; range_low = 9997.0
        row = pd.Series({
            "atr": atr, "range_low": range_low,
            "low_bid":   range_low - 5.0,
            "close_bid": range_low - 1.0,    # close still below range
        })
        assert not is_liquidity_sweep_bull(row, cfg)

    def test_bear_sweep_detected(self):
        cfg = VCLSMBConfig(sweep_atr_mult=0.3, sweep_close_inside=True)
        atr = 10.0; range_high = 10003.0
        row = pd.Series({
            "atr": atr, "range_high": range_high,
            "high_bid":  range_high + 4.0,
            "close_bid": range_high - 0.5,
        })
        assert is_liquidity_sweep_bear(row, cfg)

    def test_bull_momentum_breakout(self):
        cfg = VCLSMBConfig(momentum_atr_mult=1.0, momentum_body_ratio=0.5)
        atr = 10.0; range_high = 10003.0
        row = pd.Series({
            "atr": atr, "range_high": range_high,
            "close_bid":    range_high + 5.0,
            "bar_body":     11.0,
            "bar_body_ratio": 0.7,
            "bar_range":    15.0,
        })
        assert is_momentum_breakout_bull(row, cfg)

    def test_bull_momentum_fails_weak_body(self):
        cfg = VCLSMBConfig(momentum_atr_mult=1.0, momentum_body_ratio=0.5)
        atr = 10.0; range_high = 10003.0
        row = pd.Series({
            "atr": atr, "range_high": range_high,
            "close_bid":    range_high + 5.0,
            "bar_body":     4.0,           # < 1.0 * 10
            "bar_body_ratio": 0.6,
            "bar_range": 6.0,
        })
        assert not is_momentum_breakout_bull(row, cfg)


# ── State machine tests ───────────────────────────────────────────────────────

class TestStateMachine:
    def _idle_ctx(self):
        ctx = MachineContext()
        return ctx

    def _make_compression_row(self, cfg):
        atr = 5.0
        # roll_max = 20.0 → ratio = 0.25 << 0.6 → clearly compressed
        return pd.Series({
            "atr": atr,
            "atr_rolling_max": 20.0,
            "range_high": 10003.0, "range_low": 9997.0,
            "low_bid": 9999.0, "high_bid": 10001.0, "close_bid": 10000.0,
            "bar_body": 2.0, "bar_range": 4.0, "bar_body_ratio": 0.5,
        })

    def test_idle_to_compression(self):
        cfg = VCLSMBConfig()
        ctx = self._idle_ctx()
        row = self._make_compression_row(cfg)
        state = advance(ctx, row, 0, cfg)
        assert state == State.COMPRESSION

    def test_compression_timeout_resets(self):
        cfg = VCLSMBConfig(max_bars_in_state=3)
        ctx = MachineContext(state=State.COMPRESSION, bars_in_state=3)
        ctx.range_high = 10003.0
        ctx.range_low  = 9997.0
        row = self._make_compression_row(cfg)
        state = advance(ctx, row, 5, cfg)
        assert state == State.IDLE

    def test_compression_to_sweep(self):
        cfg = VCLSMBConfig(sweep_atr_mult=0.3, sweep_close_inside=True)
        ctx = MachineContext(state=State.COMPRESSION)
        ctx.range_high = 10003.0
        ctx.range_low  = 9997.0
        ctx.bars_in_state = 1
        atr = 10.0
        row = pd.Series({
            "atr": atr,
            "atr_rolling_max": 40.0,    # ratio = 10/40 = 0.25 << 0.6 → still compressed
            "range_high": 10003.0, "range_low": 9997.0,
            "low_bid":   9997.0 - 0.4 * atr - 0.1,
            "high_bid":  10002.0,
            "close_bid": 9997.5,
            "bar_body": 3.0, "bar_range": 5.0, "bar_body_ratio": 0.6,
        })
        state = advance(ctx, row, 5, cfg)
        assert state == State.SWEEP_DETECTED
        assert ctx.direction == "LONG"

    def test_sweep_invalidated_by_counter_sweep(self):
        cfg = VCLSMBConfig(sweep_atr_mult=0.3, sweep_close_inside=True)
        ctx = MachineContext(state=State.SWEEP_DETECTED, direction="LONG")
        ctx.range_high = 10003.0
        ctx.range_low  = 9997.0
        ctx.bars_in_state = 1
        atr = 10.0
        # A bearish sweep while we're waiting for bull momentum → reset
        row = pd.Series({
            "atr": atr,
            "atr_rolling_max": 40.0,    # ratio = 0.25 → compressed (prevents IDLE exit)
            "range_high": 10003.0, "range_low": 9997.0,
            "high_bid":  10003.0 + 0.4 * atr + 0.1,
            "close_bid": 10002.5,   # closes back inside
            "low_bid":   9998.0,
            "bar_body": 2.0, "bar_range": 4.0, "bar_body_ratio": 0.5,
        })
        state = advance(ctx, row, 6, cfg)
        assert state == State.IDLE


# ── Risk management tests ─────────────────────────────────────────────────────

class TestRiskManagement:
    def _ctx_long(self):
        ctx = MachineContext(state=State.MOMENTUM_CONFIRMED, direction="LONG")
        ctx.range_high = 10003.0
        ctx.range_low  = 9997.0
        ctx.sweep_low  = 9990.0
        return ctx

    def _momentum_row(self, atr=10.0):
        return pd.Series({
            "atr": atr,
            "close_bid": 10010.0,
            "close_ask": 10011.0,
        })

    def test_long_tp_greater_than_entry(self):
        cfg = VCLSMBConfig(risk_reward=2.0, sl_buffer_atr_mult=0.3, sl_anchor="range_extreme")
        ctx = self._ctx_long()
        row = self._momentum_row()
        levels = compute_trade_levels(ctx, row, cfg)
        assert levels is not None
        assert levels["planned_tp"] > levels["entry_price"]
        assert levels["planned_sl"] < levels["entry_price"]

    def test_rr_ratio_correct(self):
        cfg = VCLSMBConfig(risk_reward=2.5, sl_buffer_atr_mult=0.3, sl_anchor="range_extreme")
        ctx = self._ctx_long()
        row = self._momentum_row()
        lv = compute_trade_levels(ctx, row, cfg)
        risk   = lv["entry_price"] - lv["planned_sl"]
        reward = lv["planned_tp"] - lv["entry_price"]
        assert reward == pytest.approx(cfg.risk_reward * risk, rel=1e-6)

    def test_short_levels(self):
        cfg = VCLSMBConfig(risk_reward=2.0, sl_anchor="range_extreme")
        ctx = MachineContext(state=State.MOMENTUM_CONFIRMED, direction="SHORT")
        ctx.range_high = 10003.0
        ctx.range_low  = 9997.0
        ctx.sweep_high = 10010.0
        row = pd.Series({"atr": 10.0, "close_bid": 9990.0, "close_ask": 9991.0})
        lv = compute_trade_levels(ctx, row, cfg)
        assert lv["planned_tp"] < lv["entry_price"]
        assert lv["planned_sl"] > lv["entry_price"]


# ── End-to-end backtest tests ─────────────────────────────────────────────────

class TestBacktest:
    def test_returns_dataframe_and_metrics(self):
        df = _make_bars([10000 + i * 0.1 for i in range(200)])
        cfg = VCLSMBConfig(use_session_filter=False)
        trades_df, metrics = run_vclsmb_backtest("TEST", df, cfg)
        assert isinstance(trades_df, pd.DataFrame)
        assert isinstance(metrics, dict)
        assert "trades_count" in metrics
        assert "expectancy_R" in metrics

    def test_no_trades_on_flat_data(self):
        """Pure flat data rarely generates sweep patterns."""
        df = _make_bars([10000.0] * 200, high_offset=0.1, low_offset=0.1)
        cfg = VCLSMBConfig(use_session_filter=False, compression_atr_ratio=0.6)
        trades_df, metrics = run_vclsmb_backtest("TEST", df, cfg)
        # No sweep possible if range is zero
        assert metrics["trades_count"] == 0

    def test_trades_have_correct_rr(self):
        """All closed TP trades should have R ≈ risk_reward."""
        df = _make_compression_then_sweep_bull(n_compress=40, n_setup=60)
        cfg = VCLSMBConfig(
            use_session_filter=False,
            risk_reward=2.0,
            compression_atr_ratio=0.9,   # lenient for synthetic
            sweep_atr_mult=0.1,
            momentum_atr_mult=0.1,
            momentum_body_ratio=0.1,
            compression_lookback=15,
            range_window=8,
        )
        trades_df, metrics = run_vclsmb_backtest("TEST", df, cfg)
        tp_trades = trades_df[trades_df["exit_reason"] == "TP"] if len(trades_df) else pd.DataFrame()
        for _, t in tp_trades.iterrows():
            assert t["R"] == pytest.approx(cfg.risk_reward, rel=0.05)

    def test_trades_direction_valid(self):
        df = _make_bars([10000 + i * 0.5 for i in range(300)])
        cfg = VCLSMBConfig(use_session_filter=False)
        trades_df, _ = run_vclsmb_backtest("TEST", df, cfg)
        if len(trades_df):
            assert trades_df["direction"].isin(["LONG", "SHORT"]).all()

    def test_no_trades_outside_session(self):
        """With strict session filter 99-100h (impossible window) → 0 trades."""
        df = _make_bars([10000 + i * 0.3 for i in range(300)])
        cfg = VCLSMBConfig(
            use_session_filter=True,
            session_start_hour_utc=99,
            session_end_hour_utc=100,
            compression_atr_ratio=0.9,
            sweep_atr_mult=0.1,
            momentum_atr_mult=0.1,
            momentum_body_ratio=0.1,
        )
        trades_df, metrics = run_vclsmb_backtest("TEST", df, cfg)
        assert metrics["trades_count"] == 0

    def test_long_sl_below_entry(self):
        df = _make_compression_then_sweep_bull(n_compress=40, n_setup=60)
        cfg = VCLSMBConfig(
            use_session_filter=False,
            compression_atr_ratio=0.9, sweep_atr_mult=0.1,
            momentum_atr_mult=0.1, momentum_body_ratio=0.1,
            compression_lookback=15, range_window=8,
        )
        trades_df, _ = run_vclsmb_backtest("TEST", df, cfg)
        longs = trades_df[trades_df["direction"] == "LONG"] if len(trades_df) else pd.DataFrame()
        for _, t in longs.iterrows():
            assert t["planned_sl"] < t["entry_price"]
            assert t["planned_tp"] > t["entry_price"]
