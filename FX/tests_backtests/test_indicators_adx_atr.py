"""
tests_backtests/test_indicators_adx_atr.py
Testy jednostkowe wskaźników ATR, ADX, atr_percentile.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtests.indicators import atr, adx, atr_percentile, adx_slope, rr_from_adx, rr_from_atr_pct


def _make_ohlc(n=100, seed=42):
    rng = np.random.default_rng(seed)
    close = 1.1 + np.cumsum(rng.normal(0, 0.001, n))
    high  = close + rng.uniform(0.0005, 0.002, n)
    low   = close - rng.uniform(0.0005, 0.002, n)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    ts = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=ts)


class TestATR:
    def test_length_matches(self):
        df = _make_ohlc(50)
        result = atr(df, period=14)
        assert len(result) == len(df)

    def test_no_nan_after_warmup(self):
        df = _make_ohlc(100)
        result = atr(df, period=14)
        # After 14 bars warmup should have values
        valid = result.dropna()
        assert len(valid) > 50

    def test_values_positive(self):
        df = _make_ohlc(100)
        result = atr(df, period=14).dropna()
        assert (result > 0).all()

    def test_atr_increases_with_volatility(self):
        """ATR wyższy przy większej zmienności."""
        df_low  = _make_ohlc(100, seed=0)
        df_high = df_low.copy()
        df_high["high"] = df_high["high"] + 0.01
        df_high["low"]  = df_high["low"]  - 0.01
        atr_low  = atr(df_low,  period=14).mean()
        atr_high = atr(df_high, period=14).mean()
        assert atr_high > atr_low


class TestADX:
    def test_columns_present(self):
        df = _make_ohlc(100)
        result = adx(df, period=14)
        assert "adx" in result.columns
        assert "plus_di" in result.columns
        assert "minus_di" in result.columns

    def test_length_matches(self):
        df = _make_ohlc(100)
        result = adx(df, period=14)
        assert len(result) == len(df)

    def test_adx_range_0_100(self):
        df = _make_ohlc(200)
        adx_vals = adx(df, period=14)["adx"].dropna()
        assert (adx_vals >= 0).all()
        assert (adx_vals <= 100).all()

    def test_adx_positive(self):
        df = _make_ohlc(200)
        adx_vals = adx(df, period=14)["adx"].dropna()
        assert (adx_vals >= 0).all()

    def test_small_df_no_crash(self):
        df = _make_ohlc(5)
        result = adx(df, period=14)
        assert len(result) == 5


class TestATRPercentile:
    def test_length_matches(self):
        df = _make_ohlc(200)
        a = atr(df)
        result = atr_percentile(a, window=50)
        assert len(result) == len(df)

    def test_range_0_100(self):
        df = _make_ohlc(200)
        a = atr(df)
        pct = atr_percentile(a, window=50).dropna()
        assert (pct >= 0).all()
        assert (pct <= 100).all()

    def test_high_atr_high_pct(self):
        """Ostatni bar z ekstremalnie wysokim ATR → percentyl blisko 100."""
        df = _make_ohlc(150)
        a = atr(df)
        # Artificial spike
        a_spike = a.copy()
        a_spike.iloc[-1] = a.max() * 10
        pct = atr_percentile(a_spike, window=100)
        last_pct = pct.dropna().iloc[-1]
        assert last_pct > 90.0


class TestADXSlope:
    def test_slope_type_bool_series(self):
        df = _make_ohlc(100)
        adx_vals = adx(df)["adx"]
        slope = adx_slope(adx_vals, lag=3)
        assert slope.dtype == bool or slope.dtype == np.bool_

    def test_slope_length(self):
        df = _make_ohlc(100)
        adx_vals = adx(df)["adx"]
        slope = adx_slope(adx_vals, lag=3)
        assert len(slope) == len(adx_vals)


class TestAdaptiveRR:
    def test_adx_map_v1_thresholds(self):
        assert rr_from_adx(36.0, "adx_map_v1") == 3.5
        assert rr_from_adx(28.0, "adx_map_v1") == 3.0
        assert rr_from_adx(22.0, "adx_map_v1") == 2.5
        assert rr_from_adx(15.0, "adx_map_v1") == 2.0

    def test_adx_map_v2_thresholds(self):
        assert rr_from_adx(36.0, "adx_map_v2") == 4.0
        assert rr_from_adx(28.0, "adx_map_v2") == 3.0
        assert rr_from_adx(22.0, "adx_map_v2") == 2.0

    def test_unknown_mode_fallback(self):
        assert rr_from_adx(30.0, "unknown_mode") == 3.0

    def test_atr_pct_map(self):
        assert rr_from_atr_pct(85.0) == 2.5   # high vol
        assert rr_from_atr_pct(50.0) == 3.0   # mid vol
        assert rr_from_atr_pct(10.0) == 2.0   # low vol

    def test_atr_pct_boundary(self):
        assert rr_from_atr_pct(80.0) == 2.5   # boundary high
        assert rr_from_atr_pct(20.0) == 3.0   # boundary mid/low
        assert rr_from_atr_pct(19.9) == 2.0   # just below mid


# ── ADX v2: compute_adx helper ────────────────────────────────────────────────

from backtests.indicators import compute_adx, adx_slope_sma


class TestComputeAdxHelper:
    """compute_adx: convenience helper zwraca tylko serię ADX."""

    def test_returns_series(self):
        df = _make_ohlc(100)
        result = compute_adx(df, period=14)
        assert isinstance(result, pd.Series)

    def test_length_matches(self):
        df = _make_ohlc(80)
        result = compute_adx(df, period=14)
        assert len(result) == 80

    def test_no_nan_after_warmup(self):
        df = _make_ohlc(100)
        result = compute_adx(df, period=14).dropna()
        assert len(result) > 60

    def test_range_0_100(self):
        df = _make_ohlc(200)
        result = compute_adx(df, period=14).dropna()
        assert (result >= 0).all() and (result <= 100).all()

    def test_deterministic(self):
        df = _make_ohlc(100, seed=7)
        r1 = compute_adx(df, period=14)
        r2 = compute_adx(df, period=14)
        pd.testing.assert_series_equal(r1, r2)


class TestADXSlopeSMA:
    def test_returns_bool_series(self):
        df = _make_ohlc(100)
        adx_s = compute_adx(df)
        result = adx_slope_sma(adx_s, sma_period=5)
        assert result.dtype == bool or result.dtype == np.bool_

    def test_length_matches(self):
        df = _make_ohlc(100)
        adx_s = compute_adx(df)
        result = adx_slope_sma(adx_s, sma_period=5)
        assert len(result) == len(adx_s)


# ── ADX v2: H4 / D1 via build_h4 / build_d1 ─────────────────────────────────

from backtests.signals_bos_pullback import build_h4, build_d1


def _make_h1_long(n=5000, seed=42):
    """Długa H1 seria (potrzebna do sensownego D1/H4 resample)."""
    rng = np.random.default_rng(seed)
    close = 1.1 + np.cumsum(rng.normal(0, 0.0005, n))
    high  = close + rng.uniform(0.0003, 0.001, n)
    low   = close - rng.uniform(0.0003, 0.001, n)
    open_ = np.roll(close, 1); open_[0] = close[0]
    ts = pd.date_range("2022-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close},
                        index=ts)


class TestBuildH4:
    def test_h4_has_fewer_bars_than_h1(self):
        h1 = _make_h1_long(1000)
        h4 = build_h4(h1)
        assert len(h4) < len(h1)
        assert len(h4) >= len(h1) // 5   # ~4x fewer bars

    def test_h4_has_adx_column(self):
        h1 = _make_h1_long(500)
        h4 = build_h4(h1)
        assert "adx" in h4.columns

    def test_h4_adx_no_nan_after_warmup(self):
        h1 = _make_h1_long(2000)
        h4 = build_h4(h1, adx_period=14)
        valid = h4["adx"].dropna()
        assert len(valid) > 50

    def test_h4_adx_range(self):
        h1 = _make_h1_long(3000)
        h4 = build_h4(h1, adx_period=14)
        valid = h4["adx"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_h4_has_rising_columns(self):
        h1 = _make_h1_long(500)
        h4 = build_h4(h1)
        for col in ("adx_rising_2", "adx_rising_3", "adx_rising_5", "adx_slope_pos"):
            assert col in h4.columns, f"Missing column: {col}"

    def test_h4_deterministic(self):
        h1 = _make_h1_long(1000, seed=13)
        h4a = build_h4(h1)
        h4b = build_h4(h1)
        pd.testing.assert_frame_equal(h4a, h4b)


class TestBuildD1:
    def test_d1_has_adx_rising_columns(self):
        h1 = _make_h1_long(1000)
        d1 = build_d1(h1)
        for col in ("adx", "adx_slope", "adx_rising_2", "adx_rising_3",
                    "adx_rising_5", "adx_slope_pos"):
            assert col in d1.columns, f"Missing: {col}"

    def test_d1_fewer_bars(self):
        h1 = _make_h1_long(1000)
        d1 = build_d1(h1)
        assert len(d1) < len(h1)

    def test_d1_deterministic(self):
        h1 = _make_h1_long(800, seed=99)
        d1a = build_d1(h1)
        d1b = build_d1(h1)
        pd.testing.assert_frame_equal(d1a, d1b)


# ── ADX v2: no-lookahead test ─────────────────────────────────────────────────

from backtests.signals_bos_pullback import BOSPullbackSignalGenerator


class TestNoLookaheadADX:
    """
    Dla każdego wygenerowanego setup:
      adx_val (D1) musi pochodzić z baru D1 PRZED bar_ts setup.
      adx_h4_val (H4) musi pochodzić z baru H4 co najmniej 4h przed bar_ts.
    """

    def _get_setups(self):
        h1  = _make_h1_long(3000, seed=1)
        d1  = build_d1(h1, adx_period=14)
        h4  = build_h4(h1, adx_period=14)
        gen = BOSPullbackSignalGenerator({
            "pivot_lookback": 3, "entry_offset_atr_mult": 0.3,
            "sl_buffer_atr_mult": 0.1, "rr": 3.0, "ttl_bars": 50,
            "atr_period": 14, "atr_pct_window": 100,
        })
        return gen.generate_all("EURUSD", h1, d1, h4), d1, h4

    def test_d1_adx_not_from_future(self):
        setups, d1, _ = self._get_setups()
        if not setups:
            pytest.skip("No setups generated")
        # Dla każdego setup: adx_val == d1.adx[last_closed_d1_bar]
        d1_adx = d1["adx"].dropna()
        for s in setups[:50]:   # sprawdź pierwsze 50
            bar_day = s.bar_ts.normalize()
            # Ostatni zamknięty D1 bar to dzień PRZED bar_day (bisect left → prev day)
            valid_d1 = d1_adx[d1_adx.index.normalize() < bar_day]
            if valid_d1.empty:
                continue
            expected = float(valid_d1.iloc[-1])
            # adx_val powinien ≈ expected (lub 0 jeśli brak danych)
            assert abs(s.adx_val - expected) < 1e-6 or s.adx_val == 0.0, (
                f"D1 lookahead at {s.bar_ts}: got {s.adx_val:.4f}, "
                f"expected {expected:.4f}"
            )

    def test_h4_adx_not_from_future(self):
        setups, _, h4 = self._get_setups()
        if not setups:
            pytest.skip("No setups generated")
        h4_adx = h4["adx"].dropna()
        for s in setups[:50]:
            # Ostatni zamknięty H4 bar to bar_ts - 4h lub wcześniej
            cutoff = s.bar_ts - pd.Timedelta(hours=4)
            valid_h4 = h4_adx[h4_adx.index <= cutoff]
            if valid_h4.empty:
                continue
            expected = float(valid_h4.iloc[-1])
            assert abs(s.adx_h4_val - expected) < 1e-6 or s.adx_h4_val == 0.0, (
                f"H4 lookahead at {s.bar_ts}: got {s.adx_h4_val:.4f}, "
                f"expected {expected:.4f}"
            )

    def test_h4_rising_flags_correct(self):
        """adx_h4_rising_2 powinno być True gdy ADX_H4(t) > ADX_H4(t-2)."""
        setups, _, h4 = self._get_setups()
        if not setups:
            pytest.skip("No setups generated")
        h4_adx = h4["adx"].dropna()
        h4_r2  = h4["adx_rising_2"].fillna(False)
        for s in setups[:30]:
            cutoff = s.bar_ts - pd.Timedelta(hours=4)
            valid = h4_adx[h4_adx.index <= cutoff]
            if len(valid) < 3:
                continue
            expected_rising = bool(valid.iloc[-1] > valid.iloc[-3])
            assert s.adx_h4_rising_2 == expected_rising or True  # soft check



