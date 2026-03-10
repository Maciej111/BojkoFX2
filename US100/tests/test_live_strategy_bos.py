"""
Unit tests for the live strategy's BOS detection — src/core/strategy.py

Verifies that TrendFollowingStrategy.process_bar():
  - detects a BOS only when a close breaks a confirmed pivot
  - rejects BOS when HTF bias is NEUTRAL or misaligned
  - rejects BOS for counter-trend signals
  - does NOT fire on the same bar as the pivot formation (anti-lookahead)

Run: pytest tests/test_live_strategy_bos.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from src.core.strategy import TrendFollowingStrategy
from src.core.config import StrategyConfig
from src.core.models import Side


# ── Synthetic bar builder ─────────────────────────────────────────────────────

def _bars(prices: list, spread: float = 0.0001,
          start: str = "2024-01-01 00:00",
          freq: str = "1h") -> pd.DataFrame:
    """Build a minimal bar DataFrame from a list of close prices."""
    idx = pd.date_range(start, periods=len(prices), freq=freq, tz="UTC")
    close = pd.Series(prices, dtype=float, index=idx)
    df = pd.DataFrame({
        "open_bid":  close.shift(1).fillna(close),
        "high_bid":  close * 1.0005,
        "low_bid":   close * 0.9995,
        "close_bid": close,
        "open_ask":  close.shift(1).fillna(close) + spread,
        "high_ask":  close * 1.0005 + spread,
        "low_ask":   close * 0.9995 + spread,
        "close_ask": close + spread,
    }, index=idx)
    return df


def _htf_bars(prices: list, spread: float = 0.0001,
              start: str = "2024-01-01 00:00") -> pd.DataFrame:
    """4-hour bars from list of close prices."""
    return _bars(prices, spread=spread, start=start, freq="4h")


def _default_config(**kwargs) -> StrategyConfig:
    return StrategyConfig(
        pivot_lookback_ltf=3,
        pivot_lookback_htf=3,
        confirmation_bars=1,
        require_close_break=True,
        entry_offset_atr_mult=0.0,   # place entry exactly at BOS level
        sl_buffer_atr_mult=0.5,
        risk_reward=2.0,
        pullback_max_bars=40,
        **kwargs,
    )


def _bullish_htf(n: int = 50) -> pd.DataFrame:
    """HTF bars with a clear HH+HL bull sequence."""
    # Staircase up: each cycle adds +0.02 net
    prices = []
    base = 1.00
    for i in range(n):
        prices.append(round(base + i * 0.002, 5))
    # Weave a zigzag to create pivot structure
    zigzag = []
    for i, p in enumerate(prices):
        if i % 3 == 1:
            zigzag.append(p - 0.001)
        else:
            zigzag.append(p)
    return _htf_bars(zigzag)


def _bearish_htf(n: int = 50) -> pd.DataFrame:
    """HTF bars with a clear LL+LH bear sequence."""
    prices = []
    base = 1.10
    for i in range(n):
        prices.append(round(base - i * 0.002, 5))
    zigzag = []
    for i, p in enumerate(prices):
        if i % 3 == 1:
            zigzag.append(p + 0.001)
        else:
            zigzag.append(p)
    return _htf_bars(zigzag)


# ── Core BOS tests ────────────────────────────────────────────────────────────

class TestBosDetection:
    def test_no_signal_before_warmup(self):
        """No signal during the first 20 bars (insufficient history)."""
        n = 15
        prices = [1.00 + i * 0.001 for i in range(n)]
        ltf = _bars(prices)
        htf = _bullish_htf(50)
        cfg = _default_config()
        strat = TrendFollowingStrategy(cfg)

        for i in range(n):
            intents = strat.process_bar(ltf, htf, i)
            assert intents == [], f"Unexpected signal at bar {i} (warmup phase)"

    def test_no_signal_on_pivot_formation_bar(self):
        """
        A pivot is detected at bar i but confirmed only at bar i+confirmation_bars.
        No signal should fire on the pivot formation bar itself.
        """
        # Build a simple local high at bar 5, break at bar 9
        prices = [1.00, 1.01, 1.02, 1.015, 1.01,   # rising
                  1.02, 1.015,                       # slight pullback forms PH at bar 4
                  1.025, 1.03, 1.035]                # break above
        ltf = _bars(prices)
        htf = _bullish_htf(50)
        cfg = _default_config(pivot_lookback_ltf=2, confirmation_bars=1)
        strat = TrendFollowingStrategy(cfg)

        signals_per_bar = {}
        for i in range(len(prices)):
            signals_per_bar[i] = strat.process_bar(ltf, htf, i)

        # The pivot at bar 4 (idx 4) is only confirmed at bar 5 (idx 5).
        # No signal should appear at bar 4 — the pivot cannot be "known" there.
        assert signals_per_bar.get(4, []) == [], \
            "Signal fired on pivot formation bar (lookahead!)"

    def test_bos_long_requires_close_above_pivot(self):
        """BOS LONG fires only when close_bid strictly exceeds last confirmed PH."""
        # Build a clear pivot high and then break through it
        prices = [1.00, 1.01, 1.02, 1.015, 1.005,   # PH at bar 2 (high=1.02*1.0005)
                  1.01, 1.00, 1.005, 1.01, 1.015,
                  1.02, 1.025, 1.03]                  # close at 1.03 breaks py high
        ltf = _bars(prices)
        htf = _bullish_htf(50)
        cfg = _default_config(pivot_lookback_ltf=3, confirmation_bars=1)
        strat = TrendFollowingStrategy(cfg)

        found_long = False
        for i in range(len(prices)):
            intents = strat.process_bar(ltf, htf, i)
            for intent in intents:
                if intent.side == Side.LONG:
                    found_long = True
                    assert intent.entry_price > 0
                    assert intent.sl_price < intent.entry_price
                    assert intent.tp_price > intent.entry_price

        assert found_long, "Expected at least one LONG signal on bullish breakout"

    def test_bos_short_requires_close_below_pivot(self):
        """BOS SHORT fires only when close_bid strictly falls below last confirmed PL."""
        prices = [1.10, 1.09, 1.08, 1.085, 1.095,
                  1.09, 1.10, 1.095, 1.09, 1.085,
                  1.08, 1.075, 1.07]
        ltf = _bars(prices)
        htf = _bearish_htf(50)
        cfg = _default_config(pivot_lookback_ltf=3, confirmation_bars=1)
        strat = TrendFollowingStrategy(cfg)

        found_short = False
        for i in range(len(prices)):
            intents = strat.process_bar(ltf, htf, i)
            for intent in intents:
                if intent.side == Side.SHORT:
                    found_short = True
                    assert intent.sl_price > intent.entry_price
                    assert intent.tp_price < intent.entry_price

        assert found_short, "Expected at least one SHORT signal on bearish breakout"


# ── HTF bias gates ────────────────────────────────────────────────────────────

class TestHtfBiasGating:
    def _run(self, ltf_prices, htf_df, **cfg_kwargs):
        cfg = _default_config(**cfg_kwargs)
        strat = TrendFollowingStrategy(cfg)
        all_intents = []
        for i in range(len(ltf_prices)):
            all_intents.extend(strat.process_bar(
                _bars(ltf_prices), htf_df, i
            ))
        return all_intents

    def test_long_blocked_when_htf_is_neutral(self):
        """A LONG BOS must be blocked if HTF bias is NEUTRAL."""
        # Short HTF — not enough bars for confirmed pivots → NEUTRAL
        htf = _htf_bars([1.00, 1.01, 1.00, 1.01])  # only 4 bars
        ltf_prices = [1.00, 1.01, 1.02, 1.015, 1.005,
                      1.01, 1.00, 1.005, 1.01, 1.025, 1.03]
        intents = self._run(ltf_prices, htf)
        longs = [i for i in intents if i.side == Side.LONG]
        assert longs == [], f"LONG should be blocked when HTF is NEUTRAL; got {longs}"

    def test_long_blocked_when_htf_is_bear(self):
        """A LONG BOS that contradicts a BEAR HTF bias must be rejected."""
        htf = _bearish_htf(50)
        ltf_prices = [1.00, 1.01, 1.02, 1.015, 1.005,
                      1.01, 1.00, 1.005, 1.01, 1.025, 1.03]
        intents = self._run(ltf_prices, htf)
        longs = [i for i in intents if i.side == Side.LONG]
        assert longs == [], f"LONG BOS must be blocked when HTF is BEAR; got {longs}"

    def test_short_blocked_when_htf_is_bull(self):
        """A SHORT BOS that contradicts a BULL HTF bias must be rejected."""
        htf = _bullish_htf(50)
        ltf_prices = [1.10, 1.09, 1.08, 1.085, 1.095,
                      1.09, 1.10, 1.095, 1.09, 1.085, 1.075]
        intents = self._run(ltf_prices, htf)
        shorts = [i for i in intents if i.side == Side.SHORT]
        assert shorts == [], f"SHORT BOS must be blocked when HTF is BULL; got {shorts}"


# ── Entry / SL / TP sanity ────────────────────────────────────────────────────

class TestIntentSanity:
    def test_long_intent_sl_tp_ordering(self):
        """For a LONG intent: SL < entry < TP."""
        prices = [1.00, 1.01, 1.02, 1.015, 1.005,
                  1.01, 1.00, 1.005, 1.01, 1.015, 1.02, 1.025, 1.03]
        ltf = _bars(prices)
        htf = _bullish_htf(50)
        cfg = _default_config()
        strat = TrendFollowingStrategy(cfg)
        for i in range(len(prices)):
            for intent in strat.process_bar(ltf, htf, i):
                if intent.side == Side.LONG:
                    assert intent.sl_price < intent.entry_price, \
                        "LONG SL must be below entry"
                    assert intent.tp_price > intent.entry_price, \
                        "LONG TP must be above entry"

    def test_short_intent_sl_tp_ordering(self):
        """For a SHORT intent: TP < entry < SL."""
        prices = [1.10, 1.09, 1.08, 1.085, 1.095,
                  1.09, 1.10, 1.095, 1.09, 1.085,
                  1.08, 1.075, 1.07, 1.065, 1.060]
        ltf = _bars(prices)
        htf = _bearish_htf(50)
        cfg = _default_config()
        strat = TrendFollowingStrategy(cfg)
        for i in range(len(prices)):
            for intent in strat.process_bar(ltf, htf, i):
                if intent.side == Side.SHORT:
                    assert intent.sl_price > intent.entry_price, \
                        "SHORT SL must be above entry"
                    assert intent.tp_price < intent.entry_price, \
                        "SHORT TP must be below entry"

    def test_rr_ratio_honoured(self):
        """TP distance should equal risk_reward × SL distance (within float tolerance)."""
        prices = [1.00, 1.01, 1.02, 1.015, 1.005,
                  1.01, 1.00, 1.005, 1.01, 1.015, 1.02, 1.025, 1.03]
        ltf = _bars(prices)
        htf = _bullish_htf(50)
        rr = 3.0
        cfg = _default_config(risk_reward=rr)
        strat = TrendFollowingStrategy(cfg)
        for i in range(len(prices)):
            for intent in strat.process_bar(ltf, htf, i):
                risk = abs(intent.entry_price - intent.sl_price)
                reward = abs(intent.tp_price - intent.entry_price)
                assert reward == pytest.approx(rr * risk, rel=1e-6), \
                    f"R:R not honoured: risk={risk:.6f} reward={reward:.6f}"
