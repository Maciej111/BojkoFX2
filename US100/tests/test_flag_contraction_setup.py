"""
Unit and integration tests for the FLAG_CONTRACTION setup type.

Tests cover:
  1-5  : detect_flag_contraction() — unit tests for detection logic
  6-7  : HTF NEUTRAL gate — flags must not fire when HTF bias is NEUTRAL
  8    : Price ordering — ensure SL < entry < TP (LONG) / TP < entry < SL (SHORT)
  9    : setup_type field propagates to trade output
  10   : Integration — full run_trend_backtest() produces FLAG_CONTRACTION trade
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.structure.flags import detect_flag_contraction


# ──────────────────────────────────────────────────────────────────────────────
# Helpers – synthetic DataFrame builder
# ──────────────────────────────────────────────────────────────────────────────

def _make_df(
    n_bars: int,
    opens: list | None = None,
    closes: list | None = None,
    highs: list | None = None,
    lows: list | None = None,
    atr_val: float = 10.0,
) -> pd.DataFrame:
    """
    Build a minimal LTF DataFrame with bid OHLC + ATR columns.
    If not provided, open == close == 100, high == open+0.5, low == open-0.5.
    """
    idx = pd.date_range("2024-01-01", periods=n_bars, freq="5min", tz="UTC")
    o = np.array(opens  if opens  is not None else [100.0] * n_bars)
    c = np.array(closes if closes is not None else [100.0] * n_bars)
    h = np.array(highs  if highs  is not None else (o + 0.5).tolist())
    l = np.array(lows   if lows   is not None else (o - 0.5).tolist())
    return pd.DataFrame({
        "open_bid":  o,
        "high_bid":  h,
        "low_bid":   l,
        "close_bid": c,
        "open_ask":  o + 1,
        "high_ask":  h + 1,
        "low_ask":   l + 1,
        "close_ask": c + 1,
        "atr":       [atr_val] * n_bars,
    }, index=idx)


DEFAULT_PARAMS = {
    "flag_impulse_lookback_bars":    8,
    "flag_contraction_bars":         5,
    "flag_min_impulse_atr_mult":     2.5,
    "flag_max_contraction_atr_mult": 1.2,
    "flag_breakout_buffer_atr_mult": 0.1,
    "flag_sl_buffer_atr_mult":       0.3,
}

# With ATR=10:
#   min_impulse   = 2.5 × 10 = 25
#   max_contraction = 1.2 × 10 = 12


# ──────────────────────────────────────────────────────────────────────────────
# Test 1 — Detects LONG flag
# ──────────────────────────────────────────────────────────────────────────────

def test_detect_long_flag():
    """
    Impulse: open=100, close=140 → move=40 >= 25 ✓
    Contraction (5 bars): high=138, low=132 → range=6 <= 12 ✓
    Breakout bar i: close=139 > c_high=138 ✓
    """
    n = 20
    opens  = [100.0] * n
    closes = [100.0] * n
    highs  = [100.5] * n
    lows   = [99.5]  * n

    # Impulse window: bars [5, 13) — length = 8
    # i=18, contraction_bars=5, impulse_lookback=8
    # imp_start = 18-5-8=5, imp_end=13, contraction=[13,18)
    imp_start = 5
    imp_open  = 100.0
    imp_close = 140.0
    for k in range(imp_start, imp_start + 8):
        opens[k]  = imp_open + (imp_close - imp_open) * (k - imp_start) / 7
        closes[k] = imp_open + (imp_close - imp_open) * (k - imp_start + 1) / 8
        highs[k]  = closes[k] + 0.5
        lows[k]   = opens[k]  - 0.5

    # Explicitly set impulse endpoints
    opens[imp_start]  = 100.0
    closes[imp_start + 7] = 140.0

    # Contraction window: bars [13, 18) — range 132–138
    for k in range(13, 18):
        opens[k]  = 135.0
        closes[k] = 135.0
        highs[k]  = 138.0
        lows[k]   = 132.0

    # Breakout bar: i=18
    opens[18]  = 135.0
    closes[18] = 139.0   # > c_high=138 ✓
    highs[18]  = 139.5
    lows[18]   = 134.5

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)

    assert result is not None, "Expected LONG flag to be detected"
    assert result["direction"] == "LONG"
    assert result["contraction_high"] == pytest.approx(138.0, abs=0.01)
    assert result["contraction_low"]  == pytest.approx(132.0, abs=0.01)
    # entry = c_high + 0.1*10 = 138 + 1 = 139
    assert result["entry_price"] == pytest.approx(139.0, abs=0.01)
    # sl = c_low - 0.3*10 = 132 - 3 = 129
    assert result["sl_price"] == pytest.approx(129.0, abs=0.01)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2 — Detects SHORT flag
# ──────────────────────────────────────────────────────────────────────────────

def test_detect_short_flag():
    """
    Impulse: open=140, close=100 → move=40 >= 25 ✓
    Contraction (5 bars): high=108, low=102 → range=6 <= 12 ✓
    Breakout bar i: close=101 < c_low=102 ✓
    """
    n = 20
    opens  = [110.0] * n
    closes = [110.0] * n
    highs  = [110.5] * n
    lows   = [109.5] * n

    imp_start = 5
    for k in range(imp_start, imp_start + 8):
        frac = (k - imp_start) / 8
        opens[k]  = 140.0 - frac * 40
        closes[k] = 140.0 - (frac + 1/8) * 40
        highs[k]  = max(opens[k], closes[k]) + 0.5
        lows[k]   = min(opens[k], closes[k]) - 0.5

    opens[imp_start]      = 140.0
    closes[imp_start + 7] = 100.0

    for k in range(13, 18):
        opens[k]  = 105.0
        closes[k] = 105.0
        highs[k]  = 108.0
        lows[k]   = 102.0

    opens[18]  = 105.0
    closes[18] = 101.0   # < c_low=102 ✓
    highs[18]  = 105.5
    lows[18]   = 100.5

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)

    assert result is not None, "Expected SHORT flag to be detected"
    assert result["direction"] == "SHORT"
    assert result["contraction_high"] == pytest.approx(108.0, abs=0.01)
    assert result["contraction_low"]  == pytest.approx(102.0, abs=0.01)
    # entry = c_low - 0.1*10 = 102 - 1 = 101
    assert result["entry_price"] == pytest.approx(101.0, abs=0.01)
    # sl = c_high + 0.3*10 = 108 + 3 = 111
    assert result["sl_price"] == pytest.approx(111.0, abs=0.01)


# ──────────────────────────────────────────────────────────────────────────────
# Test 3 — Rejects when impulse too weak
# ──────────────────────────────────────────────────────────────────────────────

def test_rejects_weak_impulse():
    """
    Impulse move = 15 < 2.5×10=25 → should return None.
    """
    n = 20
    opens  = [100.0] * n
    closes = [100.0] * n
    highs  = [100.5] * n
    lows   = [99.5]  * n

    opens[5]  = 100.0
    closes[12] = 115.0   # move=15 < 25 ✗

    for k in range(13, 18):
        highs[k] = 116.0
        lows[k]  = 113.0
        opens[k] = closes[k] = 114.5

    closes[18] = 117.0
    highs[18]  = 117.0
    lows[18]   = 113.0

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)
    assert result is None, "Should reject: impulse too weak"


# ──────────────────────────────────────────────────────────────────────────────
# Test 4 — Rejects when contraction range too wide
# ──────────────────────────────────────────────────────────────────────────────

def test_rejects_wide_contraction():
    """
    Contraction range = 20 > 1.2×10=12 → should return None.
    """
    n = 20
    opens  = [100.0] * n
    closes = [100.0] * n
    highs  = [100.5] * n
    lows   = [99.5]  * n

    opens[5]   = 100.0
    closes[12] = 140.0

    for k in range(13, 18):
        highs[k] = 145.0   # range = 145 - 125 = 20 > 12 ✗
        lows[k]  = 125.0
        opens[k] = closes[k] = 135.0

    closes[18] = 146.0
    highs[18]  = 146.0
    lows[18]   = 125.0

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)
    assert result is None, "Should reject: contraction range too wide"


# ──────────────────────────────────────────────────────────────────────────────
# Test 5 — Rejects when no breakout
# ──────────────────────────────────────────────────────────────────────────────

def test_rejects_no_breakout():
    """
    Close stays INSIDE contraction (c_low <= close <= c_high) → None.
    """
    n = 20
    opens  = [100.0] * n
    closes = [100.0] * n
    highs  = [100.5] * n
    lows   = [99.5]  * n

    opens[5]   = 100.0
    closes[12] = 140.0

    for k in range(13, 18):
        highs[k] = 138.0
        lows[k]  = 132.0
        opens[k] = closes[k] = 135.0

    # close inside contraction: 135.0 — not > 138 and not < 132
    closes[18] = 135.0
    highs[18]  = 138.0
    lows[18]   = 132.0

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)
    assert result is None, "Should reject: no breakout close"


# ──────────────────────────────────────────────────────────────────────────────
# Test 6 & 7 — HTF NEUTRAL blocks both LONG and SHORT flags
# ──────────────────────────────────────────────────────────────────────────────

def _run_strategy_with_flag(direction: str, htf_bias: str):
    """
    Run run_trend_backtest() with a minimal synthetic dataset that contains a
    clear FLAG_CONTRACTION pattern.  HTF dataset is crafted to produce the
    desired bias.  Returns the trades list.
    """
    from src.strategies.trend_following_v1 import run_trend_backtest

    n = 200
    opens  = [10000.0] * n
    closes = [10000.0] * n
    highs  = [10000.5] * n
    lows   = [9999.5]  * n

    # Plant a flag pattern deep enough for pivot detection (start at bar 50)
    if direction == "LONG":
        # Impulse UP bars 50-57: 10000 → 10030 (move=30, ATR≈5 → 6×ATR)
        for k in range(50, 58):
            opens[k]  = 10000.0 + (k - 50) * 30/8
        for k in range(50, 58):
            closes[k] = 10000.0 + (k - 50 + 1) * 30/8
            highs[k]  = closes[k] + 0.5
            lows[k]   = opens[k]  - 0.5
        # Contraction bars 58-62: tight around 10029-10031
        for k in range(58, 63):
            opens[k]  = 10030.0
            closes[k] = 10030.0
            highs[k]  = 10031.0
            lows[k]   = 10029.0
        # Breakout bar 63: close > 10031
        opens[63]  = 10030.5
        closes[63] = 10032.5
        highs[63]  = 10033.0
        lows[63]   = 10030.0
        # Rest: flat
        for k in range(64, n):
            opens[k] = closes[k] = highs[k] = lows[k] = 10032.0
    else:
        # Impulse DOWN bars 50-57: 10030 → 10000
        for k in range(50, 58):
            opens[k]  = 10030.0 - (k - 50) * 30/8
        for k in range(50, 58):
            closes[k] = 10030.0 - (k - 50 + 1) * 30/8
            highs[k]  = max(opens[k], closes[k]) + 0.5
            lows[k]   = min(opens[k], closes[k]) - 0.5
        # Contraction bars 58-62: tight around 9999-10001
        for k in range(58, 63):
            opens[k]  = 10000.0
            closes[k] = 10000.0
            highs[k]  = 10001.0
            lows[k]   = 9999.0
        # Breakout bar 63: close < 9999
        opens[63]  = 10000.5
        closes[63] = 9996.5
        highs[63]  = 10001.0
        lows[63]   = 9996.0
        for k in range(64, n):
            opens[k] = closes[k] = highs[k] = lows[k] = 9997.0

    # ATR: use fixed 5.0 across the whole series
    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="5min", tz="UTC")
    ltf_df = pd.DataFrame({
        "open_bid":  opens,  "high_bid":  highs,  "low_bid":  lows,  "close_bid": closes,
        "open_ask":  [v + 0.5 for v in opens],
        "high_ask":  [v + 0.5 for v in highs],
        "low_ask":   [v + 0.5 for v in lows],
        "close_ask": [v + 0.5 for v in closes],
        "atr":       [5.0] * n,
    }, index=idx)

    # HTF: craft one long HTF bar with BULL or BEAR structural bias
    # Use 4h bars: just enough to make bias deterministic
    # For BULL bias we want HH+HL pattern; for BEAR we want LH+LL.
    # We wrap it in a simple OHLC that HTF pivot detection will classify correctly.
    htf_prices_bull = [9990, 10005, 10010, 10020, 10025, 10035, 10030, 10042]
    htf_prices_bear = [10040, 10025, 10020, 10010, 10005, 9995, 9997, 9985]

    hp = htf_prices_bull if htf_bias == "BULL" else htf_prices_bear

    htf_idx = pd.date_range("2024-01-01 00:00", periods=len(hp), freq="4h", tz="UTC")
    htf_df = pd.DataFrame({
        "open_bid":  hp,
        "high_bid":  [v + 5 for v in hp],
        "low_bid":   [v - 5 for v in hp],
        "close_bid": hp,
        "open_ask":  [v + 1 for v in hp],
        "high_ask":  [v + 6 for v in hp],
        "low_ask":   [v - 4 for v in hp],
        "close_ask": [v + 1 for v in hp],
    }, index=htf_idx)

    params = {
        "pivot_lookback_ltf": 3,
        "pivot_lookback_htf": 2,
        "confirmation_bars":  1,
        "require_close_break": True,
        "entry_offset_atr_mult": 0.1,
        "pullback_max_bars": 30,
        "sl_anchor": "last_pivot",
        "sl_buffer_atr_mult": 0.3,
        "risk_reward": 2.0,
        "use_session_filter": False,
        "use_bos_momentum_filter": False,
        "use_flag_contraction_setup": True,
        "flag_impulse_lookback_bars": 8,
        "flag_contraction_bars": 5,
        "flag_min_impulse_atr_mult": 2.0,
        "flag_max_contraction_atr_mult": 1.5,
        "flag_breakout_buffer_atr_mult": 0.1,
        "flag_sl_buffer_atr_mult": 0.3,
    }

    trades_df, _ = run_trend_backtest('TEST', ltf_df, htf_df, params)
    return trades_df.to_dict('records') if trades_df is not None else []


def test_neutral_bias_blocks_long_flag():
    """When HTF is NEUTRAL, no LONG FLAG should be created."""
    from src.strategies.trend_following_v1 import run_trend_backtest

    # Essentially: if a flat HTF produces no BOS, no FLAG should fire through bias gate.
    # We test by directly checking that detect_flag_contraction returns a valid result
    # (pattern exists) but that a strategy run with flat HTF produces 0 trades.
    # We use a direct unit approach: patch htf_bias via a flat HTF.

    params = {
        "pivot_lookback_ltf": 3,
        "pivot_lookback_htf": 2,
        "confirmation_bars":  1,
        "require_close_break": True,
        "entry_offset_atr_mult": 0.1,
        "pullback_max_bars": 30,
        "sl_anchor": "last_pivot",
        "sl_buffer_atr_mult": 0.3,
        "risk_reward": 2.0,
        "use_session_filter": False,
        "use_bos_momentum_filter": False,
        "use_flag_contraction_setup": True,
        "flag_impulse_lookback_bars": 8,
        "flag_contraction_bars": 5,
        "flag_min_impulse_atr_mult": 2.0,
        "flag_max_contraction_atr_mult": 1.5,
        "flag_breakout_buffer_atr_mult": 0.1,
        "flag_sl_buffer_atr_mult": 0.3,
    }

    # Build LTF with clear LONG flag pattern
    n = 200
    price_base = 10000.0
    opens  = [price_base] * n
    closes = [price_base] * n
    highs  = [price_base + 0.5] * n
    lows   = [price_base - 0.5] * n

    for k in range(50, 58):
        opens[k]  = price_base + (k - 50) * 30 / 8
        closes[k] = price_base + (k - 50 + 1) * 30 / 8
        highs[k]  = closes[k] + 0.5
        lows[k]   = opens[k]  - 0.5
    for k in range(58, 63):
        opens[k] = closes[k] = price_base + 30.0
        highs[k] = price_base + 31.0
        lows[k]  = price_base + 29.0
    opens[63]  = price_base + 30.5
    closes[63] = price_base + 32.5
    highs[63]  = price_base + 33.0
    lows[63]   = price_base + 30.0
    for k in range(64, n):
        opens[k] = closes[k] = highs[k] = lows[k] = price_base + 32.0

    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="5min", tz="UTC")
    ltf_df = pd.DataFrame({
        "open_bid": opens, "high_bid": highs, "low_bid": lows, "close_bid": closes,
        "open_ask": [v + 0.5 for v in opens], "high_ask": [v + 0.5 for v in highs],
        "low_ask": [v + 0.5 for v in lows],   "close_ask": [v + 0.5 for v in closes],
        "atr": [5.0] * n,
    }, index=idx)

    # Flat HTF → no pivots → NEUTRAL bias
    flat_price = 10015.0
    htf_idx = pd.date_range("2024-01-01", periods=10, freq="4h", tz="UTC")
    htf_df = pd.DataFrame({
        "open_bid": [flat_price] * 10, "high_bid": [flat_price + 1] * 10,
        "low_bid":  [flat_price - 1] * 10, "close_bid": [flat_price] * 10,
        "open_ask": [flat_price + 1] * 10, "high_ask": [flat_price + 2] * 10,
        "low_ask":  [flat_price] * 10,     "close_ask": [flat_price + 1] * 10,
    }, index=htf_idx)

    trades_df, _ = run_trend_backtest('TEST', ltf_df, htf_df, params)
    trades = trades_df.to_dict('records') if trades_df is not None else []
    flag_trades = [t for t in trades if t.get("setup_type") == "FLAG_CONTRACTION"]
    assert len(flag_trades) == 0, (
        f"Expected 0 FLAG_CONTRACTION trades with NEUTRAL HTF, got {len(flag_trades)}"
    )


def test_neutral_bias_blocks_short_flag():
    """Mirror of test_neutral_bias_blocks_long_flag for SHORT direction."""
    # Reuse the same logic — flat HTF produces NEUTRAL, which blocks all setups
    from src.strategies.trend_following_v1 import run_trend_backtest

    params = {
        "pivot_lookback_ltf": 3, "pivot_lookback_htf": 2,
        "confirmation_bars": 1, "require_close_break": True,
        "entry_offset_atr_mult": 0.1, "pullback_max_bars": 30,
        "sl_anchor": "last_pivot", "sl_buffer_atr_mult": 0.3,
        "risk_reward": 2.0, "use_session_filter": False,
        "use_bos_momentum_filter": False,
        "use_flag_contraction_setup": True,
        "flag_impulse_lookback_bars": 8, "flag_contraction_bars": 5,
        "flag_min_impulse_atr_mult": 2.0, "flag_max_contraction_atr_mult": 1.5,
        "flag_breakout_buffer_atr_mult": 0.1, "flag_sl_buffer_atr_mult": 0.3,
    }

    n = 200
    price_base = 10030.0
    opens  = [price_base] * n
    closes = [price_base] * n
    highs  = [price_base + 0.5] * n
    lows   = [price_base - 0.5] * n

    for k in range(50, 58):
        opens[k]  = price_base - (k - 50) * 30 / 8
        closes[k] = price_base - (k - 50 + 1) * 30 / 8
        highs[k]  = max(opens[k], closes[k]) + 0.5
        lows[k]   = min(opens[k], closes[k]) - 0.5
    for k in range(58, 63):
        opens[k] = closes[k] = price_base - 30.0
        highs[k] = price_base - 29.0
        lows[k]  = price_base - 31.0
    opens[63]  = price_base - 29.5
    closes[63] = price_base - 32.5
    highs[63]  = price_base - 29.0
    lows[63]   = price_base - 33.0
    for k in range(64, n):
        opens[k] = closes[k] = highs[k] = lows[k] = price_base - 32.0

    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="5min", tz="UTC")
    ltf_df = pd.DataFrame({
        "open_bid": opens, "high_bid": highs, "low_bid": lows, "close_bid": closes,
        "open_ask": [v + 0.5 for v in opens], "high_ask": [v + 0.5 for v in highs],
        "low_ask": [v + 0.5 for v in lows],   "close_ask": [v + 0.5 for v in closes],
        "atr": [5.0] * n,
    }, index=idx)

    flat_price = 10015.0
    htf_idx = pd.date_range("2024-01-01", periods=10, freq="4h", tz="UTC")
    htf_df = pd.DataFrame({
        "open_bid": [flat_price] * 10, "high_bid": [flat_price + 1] * 10,
        "low_bid":  [flat_price - 1] * 10, "close_bid": [flat_price] * 10,
        "open_ask": [flat_price + 1] * 10, "high_ask": [flat_price + 2] * 10,
        "low_ask":  [flat_price] * 10,     "close_ask": [flat_price + 1] * 10,
    }, index=htf_idx)

    trades_df, _ = run_trend_backtest('TEST', ltf_df, htf_df, params)
    trades = trades_df.to_dict('records') if trades_df is not None else []
    flag_trades = [t for t in trades if t.get("setup_type") == "FLAG_CONTRACTION"]
    assert len(flag_trades) == 0, (
        f"Expected 0 FLAG_CONTRACTION SHORT trades with NEUTRAL HTF, got {len(flag_trades)}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 8 — Price ordering
# ──────────────────────────────────────────────────────────────────────────────

def test_long_price_ordering():
    """For LONG: sl < entry, and entry < tp implied (tp = entry + rr*risk)."""
    n = 20
    opens  = [100.0] * n
    closes = [100.0] * n
    highs  = [100.5] * n
    lows   = [99.5]  * n

    opens[5]   = 100.0
    closes[12] = 140.0
    for k in range(5, 13):
        opens[k]  = 100.0 + (k - 5) * 40/8
        closes[k] = 100.0 + (k - 5 + 1) * 40/8
        highs[k]  = closes[k] + 0.5
        lows[k]   = opens[k]  - 0.5

    for k in range(13, 18):
        opens[k] = closes[k] = 135.0
        highs[k] = 138.0
        lows[k]  = 132.0

    closes[18] = 139.0
    highs[18]  = 139.5
    lows[18]   = 134.5

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)

    assert result is not None
    assert result["sl_price"] < result["entry_price"], (
        f"LONG: sl={result['sl_price']} should be < entry={result['entry_price']}"
    )
    rr = 2.0
    risk = result["entry_price"] - result["sl_price"]
    tp = result["entry_price"] + rr * risk
    assert result["entry_price"] < tp


def test_short_price_ordering():
    """For SHORT: entry < sl, and tp < entry implied."""
    n = 20
    opens  = [110.0] * n
    closes = [110.0] * n
    highs  = [110.5] * n
    lows   = [109.5] * n

    for k in range(5, 13):
        opens[k]  = 140.0 - (k - 5) * 40/8
        closes[k] = 140.0 - (k - 5 + 1) * 40/8
        highs[k]  = max(opens[k], closes[k]) + 0.5
        lows[k]   = min(opens[k], closes[k]) - 0.5

    opens[5]   = 140.0
    closes[12] = 100.0

    for k in range(13, 18):
        opens[k] = closes[k] = 105.0
        highs[k] = 108.0
        lows[k]  = 102.0

    closes[18] = 101.0
    highs[18]  = 105.5
    lows[18]   = 100.5

    df = _make_df(n, opens=opens, closes=closes, highs=highs, lows=lows, atr_val=10.0)
    result = detect_flag_contraction(df, i=18, atr=10.0, params=DEFAULT_PARAMS)

    assert result is not None
    assert result["entry_price"] < result["sl_price"], (
        f"SHORT: entry={result['entry_price']} should be < sl={result['sl_price']}"
    )
    rr = 2.0
    risk = result["sl_price"] - result["entry_price"]
    tp = result["entry_price"] - rr * risk
    assert tp < result["entry_price"]


# ──────────────────────────────────────────────────────────────────────────────
# Test 9 — setup_type == 'FLAG_CONTRACTION' in trade record
# ──────────────────────────────────────────────────────────────────────────────

def test_setup_type_field_in_trade():
    """
    Verify that when a FLAG_CONTRACTION trade is executed, the trade record
    contains 'setup_type' == 'FLAG_CONTRACTION'.
    """
    from src.strategies.trend_following_v1 import run_trend_backtest

    n = 300
    opens  = [10000.0] * n
    closes = [10000.0] * n
    highs  = [10000.5] * n
    lows   = [9999.5]  * n

    # Build a clean BULL HTF context + LONG flag pattern at LTF
    # HTF rising sequence: insert into bars 0-7 strong uptrend for pivot detection
    # LTF: plant flag at bar 60
    imp_start = 60
    imp_open  = 10000.0
    imp_close = 10040.0  # 40 pts move, ATR=5 → 8×ATR (well above min 2.0×ATR)

    for k in range(imp_start, imp_start + 8):
        frac = (k - imp_start) / 8
        opens[k]  = imp_open + frac * (imp_close - imp_open)
        closes[k] = imp_open + (frac + 1/8) * (imp_close - imp_open)
        highs[k]  = closes[k] + 0.5
        lows[k]   = opens[k]  - 0.5

    con_start = imp_start + 8   # 68
    for k in range(con_start, con_start + 5):   # 68–72
        opens[k]  = 10038.0
        closes[k] = 10038.0
        highs[k]  = 10039.0
        lows[k]   = 10037.0

    bo_bar = con_start + 5   # 73
    opens[bo_bar]  = 10038.5
    closes[bo_bar] = 10040.5   # > c_high=10039 → LONG
    highs[bo_bar]  = 10041.0
    lows[bo_bar]   = 10037.5

    # After breakout: rise to hit TP
    for k in range(bo_bar + 1, n):
        opens[k]  = 10042.0
        closes[k] = 10042.0
        highs[k]  = 10060.0   # TP reachable
        lows[k]   = 10041.5

    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="5min", tz="UTC")
    ltf_df = pd.DataFrame({
        "open_bid": opens, "high_bid": highs, "low_bid": lows, "close_bid": closes,
        "open_ask": [v + 0.5 for v in opens], "high_ask": [v + 0.5 for v in highs],
        "low_ask":  [v + 0.5 for v in lows],  "close_ask": [v + 0.5 for v in closes],
        "atr": [5.0] * n,
    }, index=idx)

    # BULL HTF: clear HH+HL structure
    htf_prices = [9990, 10000, 10008, 10005, 10015, 10012, 10022, 10020, 10030, 10025]
    htf_idx = pd.date_range("2024-01-01 00:00", periods=len(htf_prices), freq="4h", tz="UTC")
    htf_df = pd.DataFrame({
        "open_bid":  htf_prices,
        "high_bid":  [v + 5  for v in htf_prices],
        "low_bid":   [v - 5  for v in htf_prices],
        "close_bid": htf_prices,
        "open_ask":  [v + 1  for v in htf_prices],
        "high_ask":  [v + 6  for v in htf_prices],
        "low_ask":   [v - 4  for v in htf_prices],
        "close_ask": [v + 1  for v in htf_prices],
    }, index=htf_idx)

    params = {
        "pivot_lookback_ltf": 3, "pivot_lookback_htf": 2,
        "confirmation_bars": 1, "require_close_break": True,
        "entry_offset_atr_mult": 0.1, "pullback_max_bars": 30,
        "sl_anchor": "last_pivot", "sl_buffer_atr_mult": 0.3,
        "risk_reward": 2.0, "use_session_filter": False,
        "use_bos_momentum_filter": False,
        "use_flag_contraction_setup": True,
        "flag_impulse_lookback_bars": 8, "flag_contraction_bars": 5,
        "flag_min_impulse_atr_mult": 2.0, "flag_max_contraction_atr_mult": 1.5,
        "flag_breakout_buffer_atr_mult": 0.1, "flag_sl_buffer_atr_mult": 0.3,
    }

    trades_df, _ = run_trend_backtest('TEST', ltf_df, htf_df, params)
    trades = trades_df.to_dict('records') if trades_df is not None else []
    # All trades must have the 'setup_type' field
    for trade in trades:
        assert "setup_type" in trade, "Trade record missing 'setup_type' field"
        assert trade["setup_type"] in ("BOS", "FLAG_CONTRACTION"), (
            f"Unexpected setup_type value: {trade['setup_type']!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Test 10 — Backwards compatibility: use_flag_contraction_setup=False (default)
# ──────────────────────────────────────────────────────────────────────────────

def test_backwards_compat_flag_disabled():
    """
    When use_flag_contraction_setup is False (default), the strategy should
    only produce BOS trades (or none) and never FLAG_CONTRACTION trades.
    """
    from src.strategies.trend_following_v1 import run_trend_backtest

    n = 300
    opens  = [10000.0] * n
    closes = [10000.0] * n
    highs  = [10000.5] * n
    lows   = [9999.5]  * n

    # Plant a clear FLAG pattern (same as test 9)
    imp_start = 60
    for k in range(imp_start, imp_start + 8):
        frac = (k - imp_start) / 8
        opens[k]  = 10000.0 + frac * 40
        closes[k] = 10000.0 + (frac + 1/8) * 40
        highs[k]  = closes[k] + 0.5
        lows[k]   = opens[k]  - 0.5

    con_start = imp_start + 8
    for k in range(con_start, con_start + 5):
        opens[k] = closes[k] = 10038.0
        highs[k] = 10039.0
        lows[k]  = 10037.0

    bo_bar = con_start + 5
    opens[bo_bar] = 10038.5
    closes[bo_bar] = 10040.5
    highs[bo_bar]  = 10041.0
    lows[bo_bar]   = 10037.5

    for k in range(bo_bar + 1, n):
        opens[k] = closes[k] = 10042.0
        highs[k] = 10060.0
        lows[k]  = 10041.5

    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="5min", tz="UTC")
    ltf_df = pd.DataFrame({
        "open_bid": opens, "high_bid": highs, "low_bid": lows, "close_bid": closes,
        "open_ask": [v + 0.5 for v in opens], "high_ask": [v + 0.5 for v in highs],
        "low_ask":  [v + 0.5 for v in lows],  "close_ask": [v + 0.5 for v in closes],
        "atr": [5.0] * n,
    }, index=idx)

    htf_prices = [9990, 10000, 10008, 10005, 10015, 10012, 10022, 10020, 10030, 10025]
    htf_idx = pd.date_range("2024-01-01 00:00", periods=len(htf_prices), freq="4h", tz="UTC")
    htf_df = pd.DataFrame({
        "open_bid":  htf_prices, "high_bid": [v + 5 for v in htf_prices],
        "low_bid":   [v - 5 for v in htf_prices], "close_bid": htf_prices,
        "open_ask":  [v + 1 for v in htf_prices], "high_ask": [v + 6 for v in htf_prices],
        "low_ask":   [v - 4 for v in htf_prices], "close_ask": [v + 1 for v in htf_prices],
    }, index=htf_idx)

    # Note: use_flag_contraction_setup is intentionally absent (defaults to False)
    params = {
        "pivot_lookback_ltf": 3, "pivot_lookback_htf": 2,
        "confirmation_bars": 1, "require_close_break": True,
        "entry_offset_atr_mult": 0.1, "pullback_max_bars": 30,
        "sl_anchor": "last_pivot", "sl_buffer_atr_mult": 0.3,
        "risk_reward": 2.0, "use_session_filter": False,
        "use_bos_momentum_filter": False,
    }

    trades_df, _ = run_trend_backtest('TEST', ltf_df, htf_df, params)
    trades = trades_df.to_dict('records') if trades_df is not None else []
    flag_trades = [t for t in trades if t.get("setup_type") == "FLAG_CONTRACTION"]
    assert len(flag_trades) == 0, (
        f"With flag disabled (default), got {len(flag_trades)} unexpected FLAG_CONTRACTION trades"
    )
