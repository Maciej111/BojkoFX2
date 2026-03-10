"""
src/config/strategy_params.py

Centralized configuration for the BOS + Pullback trend-following strategy.

All parameters that affect signal generation, position sizing, risk management,
and execution are defined here. Use these dataclasses everywhere — avoid
magic numbers in strategy, backtest, and research code.

Usage
-----
    from src.config.strategy_params import StrategyParams, DEFAULT_STRATEGY_PARAMS

    # Default production configuration
    params = DEFAULT_STRATEGY_PARAMS

    # Custom configuration
    params = StrategyParams(
        risk_reward=2.5,
        filters=RegimeFilterParams(
            use_adx_filter=True,
            adx_threshold=20.0,
            use_atr_percentile_filter=True,
        ),
        slippage=SlippageParams(
            entry_slippage_pips=0.5,
            exit_slippage_pips=0.5,
        ),
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Sub-configurations
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RegimeFilterParams:
    """
    Optional regime filters applied before creating setups.

    Both live and backtest code must apply these consistently.
    When all flags are False (default), behaviour is identical to the
    unfiltered baseline — backward compatible.
    """
    # ADX gate
    use_adx_filter: bool = False
    adx_threshold: float = 20.0
    adx_timeframe: str = "H4"          # "H4" | "D1" — which TF's ADX to check
    adx_period: int = 14

    # ATR percentile filter
    use_atr_percentile_filter: bool = False
    atr_percentile_min: float = 10.0
    atr_percentile_max: float = 80.0
    atr_percentile_window: int = 100   # rolling window for percentile calculation


@dataclass
class SlippageParams:
    """
    Configurable slippage model for backtests.

    All values are in pips. The pip_size converts pips to price units.

    LONG entry:  actual_fill = entry_price + entry_slippage_pips * pip_size
    SHORT entry: actual_fill = entry_price - entry_slippage_pips * pip_size

    SL exit (LONG):  actual_exit = sl_price  - exit_slippage_pips * pip_size
    SL exit (SHORT): actual_exit = sl_price  + exit_slippage_pips * pip_size
    TP exit (LONG):  actual_exit = tp_price  - exit_slippage_pips * pip_size
    TP exit (SHORT): actual_exit = tp_price  + exit_slippage_pips * pip_size

    Default (0.0/0.0) = no slippage → results identical to pre-slippage baseline.
    """
    entry_slippage_pips: float = 0.0
    exit_slippage_pips:  float = 0.0
    pip_size:            float = 0.0001   # 0.0001 for most FX; 0.01 for JPY pairs


@dataclass
class TrailingStopParams:
    """
    Optional trailing stop configuration.

    ts_r:    R-multiple at which trailing activates (e.g. 1.5 = activates at 1.5R)
    lock_r:  R-multiple to lock in on activation (e.g. 0.5 = lock at +0.5R)
             None = lock at breakeven (0R)
    """
    enabled: bool = False
    ts_r:    float = 1.5
    lock_r:  Optional[float] = 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Master strategy parameters
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyParams:
    """
    Complete parameter set for the BOS + Pullback trend-following strategy.

    Covers pivot detection, ATR, entry/SL/TP, regime filters,
    slippage, trailing stop, and session behaviour.
    """

    # ── Pivot detection ──────────────────────────────────────────────────────
    pivot_lookback:     int  = 3     # bars required on EACH side to confirm a pivot
    pivot_lookback_htf: int  = 5     # pivot lookback for HTF bias detection
    confirmation_bars:  int  = 1     # additional bars after right-wing (legacy compat)
    require_close_break: bool = True  # BOS requires close beyond pivot level

    # ── ATR ──────────────────────────────────────────────────────────────────
    atr_period: int = 14

    # ── Entry offset ─────────────────────────────────────────────────────────
    entry_offset_atr_mult: float = 0.3   # entry = bos_level ± offset_mult * ATR

    # ── Stop loss ────────────────────────────────────────────────────────────
    sl_buffer_atr_mult: float = 0.1      # SL = last_pivot ∓ buffer_mult * ATR
    sl_anchor: str = "last_pivot"        # "last_pivot" | "pre_bos_pivot"
    sl_at_fill_time: bool = True         # SL computed at fill bar (True = live standard)

    # ── Take profit ──────────────────────────────────────────────────────────
    risk_reward: float = 3.0

    # ── Setup expiry ─────────────────────────────────────────────────────────
    ttl_bars:         int = 50   # max bars a pending setup waits for fill
    pullback_max_bars: int = 20  # legacy alias for ttl_bars (live code)

    # ── HTF bias ─────────────────────────────────────────────────────────────
    htf_pivot_count: int = 4     # number of pivots analyzed for HTF bias

    # ── Regime filters ───────────────────────────────────────────────────────
    filters: RegimeFilterParams = field(default_factory=RegimeFilterParams)

    # ── Slippage (backtest only) ──────────────────────────────────────────────
    slippage: SlippageParams = field(default_factory=SlippageParams)

    # ── Trailing stop ────────────────────────────────────────────────────────
    trailing_stop: TrailingStopParams = field(default_factory=TrailingStopParams)

    # ── Session filters (per symbol, supplied separately in config.yaml) ─────
    # Example: {"EURUSD": {"start": 8, "end": 21}, "USDJPY": {"start": 0, "end": 24}}
    session_filters: Dict[str, dict] = field(default_factory=dict)

    def as_backtest_cfg(self) -> dict:
        """Returns a flat dict compatible with BOSPullbackSignalGenerator cfg."""
        return {
            "pivot_lookback":       self.pivot_lookback,
            "entry_offset_atr_mult": self.entry_offset_atr_mult,
            "sl_buffer_atr_mult":   self.sl_buffer_atr_mult,
            "rr":                   self.risk_reward,
            "ttl_bars":             self.ttl_bars,
            "atr_period":           self.atr_period,
            "adx_gate":             self.filters.adx_threshold if self.filters.use_adx_filter else None,
            "atr_pct_min":          self.filters.atr_percentile_min if self.filters.use_atr_percentile_filter else 0,
            "atr_pct_max":          self.filters.atr_percentile_max if self.filters.use_atr_percentile_filter else 100,
        }

    def as_live_params(self) -> dict:
        """Returns a flat dict compatible with run_trend_backtest params_dict."""
        return {
            "pivot_lookback_ltf":      self.pivot_lookback,
            "pivot_lookback_htf":      self.pivot_lookback_htf,
            "confirmation_bars":       self.confirmation_bars,
            "require_close_break":     self.require_close_break,
            "entry_offset_atr_mult":   self.entry_offset_atr_mult,
            "pullback_max_bars":       self.pullback_max_bars,
            "sl_anchor":               self.sl_anchor,
            "sl_buffer_atr_mult":      self.sl_buffer_atr_mult,
            "risk_reward":             self.risk_reward,
            # Regime filters
            "use_adx_filter":          self.filters.use_adx_filter,
            "adx_threshold":           self.filters.adx_threshold,
            "adx_timeframe":           self.filters.adx_timeframe,
            "adx_period":              self.filters.adx_period,
            "use_atr_percentile_filter": self.filters.use_atr_percentile_filter,
            "atr_percentile_min":      self.filters.atr_percentile_min,
            "atr_percentile_max":      self.filters.atr_percentile_max,
            "atr_percentile_window":   self.filters.atr_percentile_window,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Production defaults
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_STRATEGY_PARAMS = StrategyParams()

# Production config with ADX + ATR filters enabled (matches best backtest result)
PRODUCTION_FILTERED_PARAMS = StrategyParams(
    filters=RegimeFilterParams(
        use_adx_filter=True,
        adx_threshold=20.0,
        adx_timeframe="H4",
        use_atr_percentile_filter=True,
        atr_percentile_min=10.0,
        atr_percentile_max=80.0,
    )
)

# Backtest with realistic slippage (0.5 pip entry, 0.5 pip exit)
REALISTIC_SLIPPAGE_PARAMS = StrategyParams(
    filters=RegimeFilterParams(
        use_adx_filter=True,
        adx_threshold=20.0,
        adx_timeframe="H4",
        use_atr_percentile_filter=True,
        atr_percentile_min=10.0,
        atr_percentile_max=80.0,
    ),
    slippage=SlippageParams(
        entry_slippage_pips=0.5,
        exit_slippage_pips=0.5,
        pip_size=0.0001,
    )
)
