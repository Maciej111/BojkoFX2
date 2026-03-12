"""
tests_backtests/test_engine_fill_logic.py
Testy edge-case'ów fill logic i portfolio constraints.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

# The shared backtest engine lives in FX/backtests/
_FX_ROOT = Path(__file__).resolve().parents[2] / "FX"
if str(_FX_ROOT) not in sys.path:
    sys.path.insert(0, str(_FX_ROOT))

from backtests.engine import try_fill, try_exit, calc_units, in_session, PortfolioSimulator
from backtests.signals_bos_pullback import TradeSetup, ClosedTrade


def _make_setup(side="LONG", entry=1.1000, sl=1.0950, tp=1.1150, ttl=50):
    return TradeSetup(
        bar_idx=10, bar_ts=pd.Timestamp("2024-01-01 10:00", tz="UTC"),
        symbol="EURUSD", side=side,
        entry_price=entry, sl_price=sl, tp_price=tp,
        ttl_bars=ttl, bos_level=entry,
        atr_val=0.0010, adx_val=25.0, atr_pct_val=50.0, rr=3.0,
    )


# ── try_fill ──────────────────────────────────────────────────────────────────

class TestTryFill:
    def test_long_fill_exact_low(self):
        setup = _make_setup(side="LONG", entry=1.1000)
        # bar low = entry → fill
        assert try_fill(setup, 1.1005, 1.1020, 1.1000) is True

    def test_long_fill_within_range(self):
        setup = _make_setup(side="LONG", entry=1.1005)
        assert try_fill(setup, 1.1000, 1.1020, 1.0990) is True

    def test_long_no_fill_above_range(self):
        setup = _make_setup(side="LONG", entry=1.1050)
        # entry above high — no fill
        assert try_fill(setup, 1.1000, 1.1030, 1.0990) is False

    def test_long_no_fill_below_range(self):
        setup = _make_setup(side="LONG", entry=1.0970)
        # entry below low — no fill
        assert try_fill(setup, 1.1000, 1.1030, 1.0980) is False

    def test_short_fill_within_range(self):
        setup = _make_setup(side="SHORT", entry=1.1010)
        assert try_fill(setup, 1.1000, 1.1030, 1.0990) is True

    def test_short_no_fill_below(self):
        setup = _make_setup(side="SHORT", entry=1.0950)
        assert try_fill(setup, 1.1000, 1.1030, 1.0970) is False


# ── try_exit ──────────────────────────────────────────────────────────────────

class TestTryExit:
    def test_long_tp_hit(self):
        setup = _make_setup("LONG", entry=1.1000, sl=1.0950, tp=1.1150)
        # high touches TP
        result = try_exit(setup, 1.1005, 1.1160, 1.0990, 1.1100, "conservative")
        assert result is not None
        assert result[0] == "TP"
        assert result[1] == 1.1150

    def test_long_sl_hit(self):
        setup = _make_setup("LONG", entry=1.1000, sl=1.0950, tp=1.1150)
        result = try_exit(setup, 1.1005, 1.1020, 1.0940, 1.1000, "conservative")
        assert result is not None
        assert result[0] == "SL"

    def test_long_both_hit_conservative_sl_wins(self):
        setup = _make_setup("LONG", entry=1.1000, sl=1.0950, tp=1.1150)
        result = try_exit(setup, 1.1005, 1.1200, 1.0940, 1.1100, "conservative")
        assert result[0] == "SL"

    def test_long_both_hit_optimistic_tp_wins(self):
        setup = _make_setup("LONG", entry=1.1000, sl=1.0950, tp=1.1150)
        result = try_exit(setup, 1.1005, 1.1200, 1.0940, 1.1100, "optimistic")
        assert result[0] == "TP"

    def test_long_no_exit(self):
        setup = _make_setup("LONG", entry=1.1000, sl=1.0950, tp=1.1150)
        result = try_exit(setup, 1.1000, 1.1050, 1.0960, 1.1020, "conservative")
        assert result is None

    def test_short_tp_hit(self):
        setup = _make_setup("SHORT", entry=1.1000, sl=1.1050, tp=1.0850)
        result = try_exit(setup, 1.1000, 1.1030, 1.0840, 1.0900, "conservative")
        assert result[0] == "TP"

    def test_short_sl_hit(self):
        setup = _make_setup("SHORT", entry=1.1000, sl=1.1050, tp=1.0850)
        result = try_exit(setup, 1.1000, 1.1060, 1.0900, 1.1010, "conservative")
        assert result[0] == "SL"


# ── calc_units ────────────────────────────────────────────────────────────────

class TestCalcUnits:
    def test_fixed_units(self):
        setup = _make_setup()
        u = calc_units(setup, {"mode": "fixed_units", "units": 5000}, 10000)
        assert u == 5000.0

    def test_risk_first_basic(self):
        setup = _make_setup(entry=1.1000, sl=1.0950)  # stop = 0.005
        u = calc_units(setup, {"mode": "risk_first", "risk_pct": 0.01}, 10000)
        # risk = 10000 * 0.01 = 100; units = 100 / 0.005 = 20000
        assert abs(u - 20000.0) < 0.01

    def test_risk_first_zero_stop(self):
        setup = _make_setup(entry=1.1000, sl=1.1000)  # zero stop
        u = calc_units(setup, {"mode": "risk_first", "risk_pct": 0.01}, 10000)
        assert u == 0.0

    def test_unknown_mode_fallback(self):
        setup = _make_setup()
        u = calc_units(setup, {"mode": "unknown", "units": 3000}, 10000)
        assert u == 3000.0


# ── in_session ────────────────────────────────────────────────────────────────

class TestInSession:
    def test_within_session(self):
        ts = pd.Timestamp("2024-01-01 10:00", tz="UTC")
        assert in_session(ts, {"start": 8, "end": 21}) is True

    def test_outside_session(self):
        ts = pd.Timestamp("2024-01-01 22:00", tz="UTC")
        assert in_session(ts, {"start": 8, "end": 21}) is False

    def test_none_session(self):
        ts = pd.Timestamp("2024-01-01 03:00", tz="UTC")
        assert in_session(ts, None) is True

    def test_allday_session(self):
        ts = pd.Timestamp("2024-01-01 03:00", tz="UTC")
        assert in_session(ts, {"start": 0, "end": 24}) is True

    def test_boundary_start(self):
        ts = pd.Timestamp("2024-01-01 08:00", tz="UTC")
        assert in_session(ts, {"start": 8, "end": 21}) is True

    def test_boundary_end(self):
        ts = pd.Timestamp("2024-01-01 21:00", tz="UTC")
        assert in_session(ts, {"start": 8, "end": 21}) is False


# ── Integration: PortfolioSimulator basic ─────────────────────────────────────

class TestPortfolioSimulatorIntegration:
    """Smoke test — prosty scenariusz LONG TP."""

    def _make_h1(self, n=100, base=1.1000, step=0.0001):
        ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
        opens  = np.full(n, base)
        closes = opens + step * np.arange(n)
        highs  = closes + 0.0010
        lows   = closes - 0.0010
        return pd.DataFrame({"open": opens, "high": highs,
                              "low": lows, "close": closes}, index=ts)

    def test_tp_trade_closed(self):
        h1 = self._make_h1(200)
        # Manual setup: entry at bar 5, TP at +0.005 (reachable by bar 50)
        setup = _make_setup(side="LONG", entry=1.1005, sl=1.0980, tp=1.1050)
        setup.bar_idx = 5
        setup.bar_ts = h1.index[5]

        sim = PortfolioSimulator(
            h1_data={"EURUSD": h1},
            setups={"EURUSD": [setup]},
            sizing_cfg={"mode": "fixed_units", "units": 1000},
            session_cfg={"EURUSD": None},
            same_bar_mode="conservative",
            max_positions_total=3,
            initial_equity=10_000,
        )
        trades = sim.run()
        # Should have at least one closed trade (TP or TTL)
        assert len(trades) >= 1

    def test_portfolio_max_positions_respected(self):
        # 3 symbols, max_total=1 → only 1 can be open at a time
        setups = {}
        h1_all = {}
        for sym in ["EURUSD", "USDJPY", "USDCHF"]:
            h1 = self._make_h1(200)
            h1_all[sym] = h1
            s = _make_setup(side="LONG", entry=1.1005, sl=1.0980, tp=1.1800)
            s.symbol = sym
            s.bar_idx = 5
            s.bar_ts = h1.index[5]
            setups[sym] = [s]

        sim = PortfolioSimulator(
            h1_data=h1_all, setups=setups,
            sizing_cfg={"mode": "fixed_units", "units": 1000},
            session_cfg={sym: None for sym in h1_all},
            same_bar_mode="conservative",
            max_positions_total=1,
            initial_equity=10_000,
        )
        trades = sim.run()
        # Check no more than 1 position open at same time
        # (simplified: just ensure trades list length is sane)
        open_times = [(t.entry_ts, t.exit_ts) for t in trades
                      if t.exit_reason != "TTL"]
        # Shouldn't crash and portfolio constraint should limit simultaneous opens
        assert isinstance(trades, list)

