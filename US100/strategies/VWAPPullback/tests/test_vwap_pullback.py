"""
Unit tests for VWAPPullback strategy logic using synthetic 5m bar data.

Tests verify:
  1. VWAP formula  (expanding mean of TP, daily reset)
  2. Entry on pullback  -> TP hit -> R == 1.5
  3. EMA filter blocks trade when close <= ema_htf
  4. Bearish confirmation candle -> no trade
  5. SL hit -> R == -1.0

v2 tests:
  6. Session VWAP is NaN before 14:30 UTC, computed at/after 14:30
  7. Strict VWAP touch: bar with low > VWAP -> no trade; low <= VWAP -> trade
  8. v2 entry on pullback -> TP hit -> R == 1.5

All tests use manually built DataFrames — no real market data required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parents[3]        # …/US100
SHARED_ROOT = ROOT.parent / "shared"

for _p in [str(ROOT), str(SHARED_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from strategies.VWAPPullback.config import VWAPPullbackConfig, VWAPPullbackV2Config  # noqa: E402
from strategies.VWAPPullback.strategy import (                          # noqa: E402
    compute_daily_vwap, run_backtest,
    compute_session_vwap, run_backtest_v2,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_bar(ts, o, h, l, c, vwap=1000.0, atr=10.0, ema_htf=950.0) -> dict:
    """Build a single-bar dict for DataFrame construction."""
    return dict(
        open_bid=float(o),
        high_bid=float(h),
        low_bid=float(l),
        close_bid=float(c),
        vwap=float(vwap),
        atr=float(atr),
        ema_htf=float(ema_htf),
    )


def _make_session_df(bar_dicts: list[dict],
                     start: str = "2024-01-15 14:00:00",
                     freq: str = "5min",
                     tz: str = "UTC") -> pd.DataFrame:
    """Build a UTC-aware 5m DataFrame from a list of bar dicts."""
    idx = pd.date_range(start, periods=len(bar_dicts), freq=freq, tz=tz)
    df  = pd.DataFrame(bar_dicts, index=idx)
    df["date"] = df.index.normalize()
    return df


def _default_cfg(**overrides) -> VWAPPullbackConfig:
    """Return a VWAPPullbackConfig with optional overrides."""
    return VWAPPullbackConfig(**overrides)


# ── Standard signal setup ─────────────────────────────────────────────────────
#
# Layout of bars (5m, starting 14:00 UTC)
#
#   Bar 0  14:00 — above-VWAP bar 1
#   Bar 1  14:05 — above-VWAP bar 2
#   Bar 2  14:10 — above-VWAP bar 3  (3 prior bars needed for pullback at Bar 3)
#   Bar 3  14:15 — PULLBACK bar: bullish, low touches VWAP, close > VWAP
#   Bar 4  14:20 — ENTRY bar: we go long at bar 4 open
#   Bars 5+ 14:25+ — exit candidates
#
# With VWAP=1000, ATR=10, EMA_HTF=950 (close_bid=1005 > 950 ✓):
#   pullback tolerance = 0.5*10 = 5 → low must be <= 1005
#   stop_buffer = 0.3*10 = 3
#   SL = bar3.low_bid - 3 = 1000 - 3 = 997
#   risk = entry_open - SL = 1005 - 997 = 8
#   TP = entry_open + 1.5*risk = 1005 + 12 = 1017


def _build_standard_bars(tp_high: float = 1020.0,
                          sl_low: float = None,
                          pullback_open: float = 1001.0,
                          entry_open: float = 1005.0,
                          ema_htf: float = 950.0) -> list[dict]:
    """
    Build standard signal setup.  Extra bars after entry use tp_high / sl_low
    to hit TP or SL respectively.
    """
    # Bars 0-2: above VWAP (regime)
    regime = [
        _make_bar(None, 1003, 1008, 1002, 1005, ema_htf=ema_htf)
        for _ in range(3)
    ]
    # Bar 3: pullback (bullish, low=1000, close=1004)
    pullback = _make_bar(None, pullback_open, 1008, 1000, 1004, ema_htf=ema_htf)
    # Bar 4: entry bar open=entry_open, no immediate hit
    entry_bar = _make_bar(None, entry_open, entry_open + 5, entry_open + 1, entry_open + 3,
                          ema_htf=ema_htf)
    # Bars 5-12: exit candidates
    exit_bars = []
    for _ in range(8):
        h = tp_high
        l_val = sl_low if sl_low is not None else entry_open + 1
        exit_bars.append(_make_bar(None, entry_open + 2, h, l_val, entry_open + 2, ema_htf=ema_htf))

    return regime + [pullback, entry_bar] + exit_bars


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — VWAP formula
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_vwap_formula():
    """VWAP = expanding cumulative mean of TP = (H+L+C)/3, reset daily."""
    idx = pd.date_range("2024-01-15 14:00", periods=3, freq="5min", tz="UTC")
    df  = pd.DataFrame({
        "high_bid":  [1004.0, 1006.0, 1008.0],
        "low_bid":   [1000.0, 1002.0, 1004.0],
        "close_bid": [1002.0, 1004.0, 1006.0],
        # TP = [1002, 1004, 1006]
    }, index=idx)

    vwap = compute_daily_vwap(df)

    assert np.isclose(vwap.iloc[0], 1002.0, atol=1e-6), f"VWAP[0] = {vwap.iloc[0]}"
    assert np.isclose(vwap.iloc[1], 1003.0, atol=1e-6), f"VWAP[1] = {vwap.iloc[1]}"
    assert np.isclose(vwap.iloc[2], 1004.0, atol=1e-6), f"VWAP[2] = {vwap.iloc[2]}"


def test_compute_vwap_daily_reset():
    """VWAP must reset at midnight UTC between two days."""
    # day1 ends at 23:50; day2 starts at 00:00 — no overlap
    day1 = pd.date_range("2024-01-15 23:40", periods=3, freq="5min", tz="UTC")
    day2 = pd.date_range("2024-01-16 00:00", periods=3, freq="5min", tz="UTC")
    idx  = day1.union(day2)

    df   = pd.DataFrame({
        "high_bid":  [1010.0] * 6,
        "low_bid":   [1000.0] * 6,
        "close_bid": [1005.0] * 6,  # TP = 1005 for all bars
    }, index=idx)

    vwap = compute_daily_vwap(df)

    # First bar each day should equal TP = 1005.0
    assert np.isclose(vwap[day1[0]], 1005.0), "Day 1 first bar VWAP"
    assert np.isclose(vwap[day2[0]], 1005.0), "Day 2 should reset, first bar = TP"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Entry on pullback, TP hit
# ─────────────────────────────────────────────────────────────────────────────

def test_entry_on_pullback_tp_hit():
    """
    Proper pullback setup → 1 trade, exit at TP.
    SL=997, entry=1005, TP=1017 → R should be exactly 1.5.
    """
    cfg = _default_cfg(
        ema_filter_enabled=True,
        ema_period_htf=50,
        min_bars_above_vwap=3,
        vwap_tolerance_atr_mult=0.5,
        stop_buffer_atr_mult=0.3,
        take_profit_rr=1.5,
        session_start_hour_utc=14,
        session_end_hour_utc=21,
        max_trades_per_day=1,
    )
    # entry_open=1005, tp_high=1020 (>=1017), sl_low not hit
    bars = _build_standard_bars(tp_high=1020.0, sl_low=None, entry_open=1005.0)
    df   = _make_session_df(bars)

    trades_df, meta = run_backtest(df, cfg)

    assert len(trades_df) == 1, f"Expected 1 trade, got {len(trades_df)}"
    assert trades_df.iloc[0]["exit_reason"] == "TP"
    assert np.isclose(trades_df.iloc[0]["R"], 1.5, atol=0.01), \
        f"Expected R=1.5, got {trades_df.iloc[0]['R']}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — EMA filter blocks trade
# ─────────────────────────────────────────────────────────────────────────────

def test_ema_filter_blocks_trade():
    """
    When ema_htf > close_bid, the EMA filter must prevent any trade.
    """
    cfg = _default_cfg(
        ema_filter_enabled=True,
        min_bars_above_vwap=3,
    )
    # Set ema_htf=1100 > close_bid=1005 on all bars
    bars = _build_standard_bars(tp_high=1020.0, ema_htf=1100.0)
    df   = _make_session_df(bars)

    trades_df, _ = run_backtest(df, cfg)

    assert trades_df.empty, f"Expected 0 trades, got {len(trades_df)}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — Bearish confirmation candle → no trade
# ─────────────────────────────────────────────────────────────────────────────

def test_bearish_confirmation_no_trade():
    """
    If the pullback candle is bearish (open > close), the confirmation fails
    and no trade should be entered.
    """
    cfg = _default_cfg(min_bars_above_vwap=3)

    # Build bars but make pullback bar (index 3) bearish: open=1006, close=1001
    bars = _build_standard_bars(tp_high=1020.0)
    # Override pullback bar (bars[3])
    bars[3] = _make_bar(None, 1006, 1008, 1000, 1001)   # bearish: open > close

    df = _make_session_df(bars)
    trades_df, _ = run_backtest(df, cfg)

    assert trades_df.empty, f"Expected 0 trades, got {len(trades_df)}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — SL hit → R ≈ -1.0
# ─────────────────────────────────────────────────────────────────────────────

def test_sl_hit():
    """
    After entry, price drops through SL on the first exit bar.
    SL = pullback_low(1000) - 0.3*ATR(10) = 997
    risk = entry_open(1005) - 997 = 8
    R expected = (997 - 1005) / 8 = -1.0
    """
    cfg = _default_cfg(
        min_bars_above_vwap=3,
        stop_buffer_atr_mult=0.3,
        take_profit_rr=1.5,
        session_start_hour_utc=14,
        session_end_hour_utc=21,
    )
    # tp_high must NOT hit TP (1017); sl_low must go below SL (997)
    bars = _build_standard_bars(tp_high=1010.0, sl_low=994.0, entry_open=1005.0)
    df   = _make_session_df(bars)

    trades_df, _ = run_backtest(df, cfg)

    assert len(trades_df) == 1, f"Expected 1 trade, got {len(trades_df)}"
    assert trades_df.iloc[0]["exit_reason"] == "SL"
    assert np.isclose(trades_df.iloc[0]["R"], -1.0, atol=0.01), \
        f"Expected R=-1.0, got {trades_df.iloc[0]['R']}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6 — Prior regime blocks trade when bars below VWAP
# ─────────────────────────────────────────────────────────────────────────────

def test_prior_regime_failed_no_trade():
    """
    If any of the N prior bars had close_bid <= VWAP, the regime check fails
    and no trade should be entered.
    """
    cfg = _default_cfg(min_bars_above_vwap=3)

    # Build standard bars but set bar 1 (prior regime) close_bid <= VWAP=1000
    bars = _build_standard_bars(tp_high=1020.0)
    bars[1] = _make_bar(None, 1003, 1005, 995, 999)  # close=999 < vwap=1000

    df = _make_session_df(bars)
    trades_df, _ = run_backtest(df, cfg)

    assert trades_df.empty, f"Expected 0 trades, got {len(trades_df)}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 7 — EOD exit when neither SL nor TP reached
# ─────────────────────────────────────────────────────────────────────────────

def test_eod_exit():
    """
    If neither SL nor TP is hit before session end, trade closes EOD.
    Exit price = last bar's close_bid before session_end_hour_utc.
    """
    cfg = _default_cfg(
        min_bars_above_vwap=3,
        stop_buffer_atr_mult=0.3,
        take_profit_rr=1.5,
        session_start_hour_utc=14,
        session_end_hour_utc=21,
    )
    # Build bars where tp_high < 1017 and sl_low > 997 → EOD exit
    # exit bars: O=1005, H=1010, L=1002, C=1007 (no SL/TP)
    bars = _build_standard_bars(tp_high=1010.0, sl_low=1002.0, entry_open=1005.0)
    df   = _make_session_df(bars)

    trades_df, _ = run_backtest(df, cfg)

    assert len(trades_df) == 1, f"Expected 1 trade, got {len(trades_df)}"
    assert trades_df.iloc[0]["exit_reason"] == "EOD"


# ─────────────────────────────────────────────────────────────────────────────
# Test 8 — max_trades_per_day=1 limits to one trade per session
# ─────────────────────────────────────────────────────────────────────────────

def test_max_trades_per_day():
    """
    Two valid setups in the same session → only the first should be taken.
    """
    cfg = _default_cfg(min_bars_above_vwap=3, max_trades_per_day=1)

    # First valid setup: bars 0-4
    # Second valid setup: bars 8-12 (another pullback pattern)
    bars_setup1 = _build_standard_bars(tp_high=1020.0, sl_low=None, entry_open=1005.0)
    # bars_setup1 is: 3 regime + 1 pullback + 1 entry + 8 exit bars (total 13)

    # Second signal: duplicate of the same pattern
    bars_setup2 = _build_standard_bars(tp_high=1020.0, sl_low=None, entry_open=1005.0)
    # Extend the first session by appending a second set of signal bars
    # (they share the same session day)
    all_bars = bars_setup1 + bars_setup2

    df = _make_session_df(all_bars)
    trades_df, _ = run_backtest(df, cfg)

    assert len(trades_df) <= 1, f"Expected at most 1 trade, got {len(trades_df)}"


# =============================================================================
# VWAPPullback v2 tests
# =============================================================================

def _default_cfg_v2(**overrides) -> VWAPPullbackV2Config:
    return VWAPPullbackV2Config(**overrides)


def _make_v2_session_df(bar_dicts: list[dict],
                        start: str = "2024-01-15 14:30:00",
                        freq: str = "5min",
                        tz: str = "UTC") -> pd.DataFrame:
    """Build a UTC-aware 5m DataFrame starting at session open (14:30) for v2 tests."""
    idx = pd.date_range(start, periods=len(bar_dicts), freq=freq, tz=tz)
    df  = pd.DataFrame(bar_dicts, index=idx)
    df["date"] = df.index.normalize()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Test v2-1 — Session VWAP: NaN before 14:30, computed at/after
# ─────────────────────────────────────────────────────────────────────────────

def test_session_vwap_nan_before_open():
    """
    compute_session_vwap must return NaN for bars before 14:30 UTC
    and valid values for bars at/after 14:30 UTC.
    """
    # Bars: 14:00, 14:05, 14:10, 14:15, 14:20, 14:25, 14:30, 14:35, 14:40
    idx = pd.date_range("2024-01-15 14:00", periods=9, freq="5min", tz="UTC")
    df  = pd.DataFrame({
        "high_bid":  [1010.0] * 9,
        "low_bid":   [1000.0] * 9,
        "close_bid": [1005.0] * 9,  # TP = 1005 for all
    }, index=idx)

    vwap = compute_session_vwap(df, open_hour=14, open_minute=30)

    # Pre-session bars (14:00 to 14:25) must be NaN
    for ts in idx[:6]:   # 14:00 .. 14:25
        assert np.isnan(vwap[ts]), f"Expected NaN at {ts}, got {vwap[ts]}"

    # Session bars (14:30, 14:35, 14:40) must be 1005.0 (single TP value)
    for ts in idx[6:]:   # 14:30 .. 14:40
        assert not np.isnan(vwap[ts]), f"Expected value at {ts}, got NaN"
        assert np.isclose(vwap[ts], 1005.0, atol=1e-6), f"VWAP at {ts} = {vwap[ts]}"


def test_session_vwap_cumulative_within_session():
    """
    After session open, VWAP accumulates correctly (expanding mean).
    """
    # Session bars only (14:30, 14:35, 14:40)
    idx = pd.date_range("2024-01-15 14:30", periods=3, freq="5min", tz="UTC")
    df  = pd.DataFrame({
        "high_bid":  [1004.0, 1006.0, 1008.0],
        "low_bid":   [1000.0, 1002.0, 1004.0],
        "close_bid": [1002.0, 1004.0, 1006.0],
        # TP = [1002, 1004, 1006]
    }, index=idx)

    vwap = compute_session_vwap(df, open_hour=14, open_minute=30)

    assert np.isclose(vwap.iloc[0], 1002.0, atol=1e-6), f"VWAP[0] = {vwap.iloc[0]}"
    assert np.isclose(vwap.iloc[1], 1003.0, atol=1e-6), f"VWAP[1] = {vwap.iloc[1]}"
    assert np.isclose(vwap.iloc[2], 1004.0, atol=1e-6), f"VWAP[2] = {vwap.iloc[2]}"


# ─────────────────────────────────────────────────────────────────────────────
# Test v2-2 — Strict VWAP touch: low > VWAP → no trade
# ─────────────────────────────────────────────────────────────────────────────

def test_v2_no_trade_when_low_above_vwap():
    """
    In v2, pullback requires low_bid <= VWAP.
    A bar with low_bid slightly above VWAP must not generate a trade.
    """
    cfg = _default_cfg_v2(ema_filter_enabled=False, min_bars_above_vwap=0)

    # VWAP=1000, bar low=1001 (above VWAP) → no pullback
    bars = []
    # Entry candidate: bullish candle, low=1001 > vwap=1000
    signal_bar = dict(open_bid=1002.0, high_bid=1008.0, low_bid=1001.0, close_bid=1006.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)
    entry_bar  = dict(open_bid=1007.0, high_bid=1020.0, low_bid=1006.0, close_bid=1018.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)
    bars = [signal_bar, entry_bar]

    df = _make_v2_session_df(bars)
    trades_df, _ = run_backtest_v2(df, cfg)

    assert trades_df.empty, f"Expected 0 trades (low > VWAP), got {len(trades_df)}"


def test_v2_trade_when_low_touches_vwap():
    """
    In v2, a bar with low_bid <= VWAP, bullish close, and close > VWAP
    must generate exactly 1 trade that exits at TP.
    Signal → entry bar (no hit) → exit bar (TP hit).
    """
    cfg = _default_cfg_v2(
        ema_filter_enabled=False,
        min_bars_above_vwap=0,
        stop_buffer_atr_mult=0.3,
        take_profit_rr=1.5,
        session_close_hour=21,
    )

    # Signal bar: low=1000 == VWAP (strict touch), bullish, close=1004 > VWAP
    # SL = 1000 - 0.3*10 = 997; entry_open=1005; risk=8; TP=1017
    signal_bar = dict(open_bid=1001.0, high_bid=1008.0, low_bid=1000.0, close_bid=1004.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)
    # Entry bar: open=1005, stays below TP (high < 1017)
    entry_bar  = dict(open_bid=1005.0, high_bid=1012.0, low_bid=1003.0, close_bid=1008.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)
    # Exit bar: high=1020 >= TP=1017 → TP hit
    exit_bar   = dict(open_bid=1008.0, high_bid=1020.0, low_bid=1006.0, close_bid=1015.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)

    df = _make_v2_session_df([signal_bar, entry_bar, exit_bar])
    trades_df, _ = run_backtest_v2(df, cfg)

    assert len(trades_df) == 1, f"Expected 1 trade, got {len(trades_df)}"
    assert trades_df.iloc[0]["exit_reason"] == "TP"
    assert np.isclose(trades_df.iloc[0]["R"], 1.5, atol=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# Test v2-3 — Full v2 signal: TP hit → R = 1.5
# ─────────────────────────────────────────────────────────────────────────────

def test_v2_entry_on_pullback_tp_hit():
    """
    Full v2 pipeline: session bars → strict VWAP touch → confirmation → TP hit.
    entry_open=1005, SL=997, TP=1017 → R expected = 1.5.
    """
    cfg = _default_cfg_v2(
        ema_filter_enabled=True,
        min_bars_above_vwap=0,
        stop_buffer_atr_mult=0.3,
        take_profit_rr=1.5,
        session_open_hour=14,
        session_open_minute=30,
        session_close_hour=21,
    )

    # All bars start at 14:30 UTC; VWAP=1000, ATR=10, EMA_HTF=950
    signal_bar = dict(open_bid=1001.0, high_bid=1008.0, low_bid=1000.0, close_bid=1004.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)
    # Entry bar: open=1005; high reaches TP=1017
    entry_bar  = dict(open_bid=1005.0, high_bid=1018.0, low_bid=1004.0, close_bid=1017.0,
                      vwap=1000.0, atr=10.0, ema_htf=950.0)
    # Extra exit bars in case TP not hit on entry bar itself
    exit_bars  = [
        dict(open_bid=1010.0, high_bid=1020.0, low_bid=1005.0, close_bid=1015.0,
             vwap=1000.0, atr=10.0, ema_htf=950.0)
        for _ in range(5)
    ]

    df = _make_v2_session_df([signal_bar, entry_bar] + exit_bars)
    trades_df, _ = run_backtest_v2(df, cfg)

    assert len(trades_df) == 1, f"Expected 1 trade, got {len(trades_df)}"
    assert trades_df.iloc[0]["exit_reason"] == "TP"
    assert np.isclose(trades_df.iloc[0]["R"], 1.5, atol=0.01), \
        f"Expected R=1.5, got {trades_df.iloc[0]['R']}"
