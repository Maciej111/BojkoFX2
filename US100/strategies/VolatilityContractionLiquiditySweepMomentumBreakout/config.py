"""
Strategy-specific configuration for VCLSMB.

All shared backtest infrastructure is reused from:
- scripts.run_backtest_idx  (load_ltf, build_htf_from_ltf, filter_by_date)
- shared/bojkofx_shared/indicators/atr.py  (calculate_atr)
- shared/bojkofx_shared/indicators/ema.py  (calculate_ema)
- src/backtest/metrics.py  (compute_metrics)
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VCLSMBConfig:
    # ── Volatility contraction detector ──────────────────────────────────────
    atr_period: int = 14               # ATR period (Wilder)
    compression_lookback: int = 20     # bars to measure compression range over
    compression_atr_ratio: float = 0.6 # current ATR / rolling-max ATR must be ≤ this

    # ── Consolidation range ───────────────────────────────────────────────────
    range_window: int = 10             # bars to define the compression range high/low

    # ── Liquidity sweep detector ──────────────────────────────────────────────
    sweep_atr_mult: float = 0.5        # sweep wick must extend ≥ N×ATR beyond range (was 0.3)
    sweep_close_inside: bool = True    # close must return inside range after sweep

    # ── Momentum confirmation ─────────────────────────────────────────────────
    momentum_atr_mult: float = 1.3     # breakout bar body must be ≥ N×ATR (was 1.0)
    momentum_body_ratio: float = 0.65  # body/range must be ≥ this fraction (was 0.5)

    # ── Risk management ───────────────────────────────────────────────────────
    risk_reward: float = 2.0           # TP = entry + RR × risk
    sl_buffer_atr_mult: float = 0.3    # extra SL buffer in ATR units
    sl_anchor: str = "range_extreme"   # "range_extreme" | "sweep_wick"

    # ── Trailing stop (optional) ──────────────────────────────────────────────
    use_trailing_stop: bool = False
    trailing_atr_multiplier: float = 2.0   # trail SL N×ATR from best price
    breakeven_atr_mult: float = 1.0        # move SL to BE after N ATR profit

    # ── Higher-timeframe trend filter (optional) ──────────────────────────────
    enable_trend_filter: bool = False
    trend_ema_period: int = 50             # EMA period applied on LTF bars
    # ── Volatility regime filter (optional) ───────────────────────────────────
    # Prevents setups when the market is in a structurally low-volatility
    # regime.  ATR is computed on hourly bars; the current ATR is compared to
    # its rolling percentile over a trailing window.
    enable_volatility_filter: bool = False
    volatility_htf: str = "1h"              # resample rule for the HTF ATR
    volatility_atr_period: int = 14         # Wilder ATR period on HTF bars
    volatility_window_days: int = 20        # rolling window length (calendar days)
    volatility_percentile_threshold: float = 40.0  # min ATR percentile to allow entries
    # ── Structural liquidity location filter (PDH / PDL) ───────────────────────
    # Gates entries: the sweep extreme must lie within N×ATR of the previous
    # day's high (bear sweep) or previous day's low (bull sweep).
    enable_liquidity_location_filter: bool = False
    liquidity_level_atr_mult: float = 4.0  # proximity threshold in ATR units (range boundary vs PDH/PDL)
    liquidity_levels: list = field(default_factory=lambda: ["PDH", "PDL"])

    # ── Session filter ────────────────────────────────────────────────────────
    # Signals form in the overnight/Asian session (22-02 UTC for NQ futures).
    # Default: disabled so no signals are blocked out-of-the-box.
    use_session_filter: bool = False
    session_start_hour_utc: int = 21   # start of overnight session (UTC)
    session_end_hour_utc: int = 2      # end   of overnight session (UTC, exclusive)

    # ── BOS + Pullback continuation entry (optional) ─────────────────────────
    # After the first trade closes the machine enters TREND_EXPANSION and
    # watches for price to retrace to the breakout level.  A second entry is
    # opened with identical SL/TP logic.  Disabled by default so that existing
    # behaviour is completely unchanged when not explicitly enabled.
    enable_pullback_entry: bool = False
    pullback_atr_mult: float = 0.2     # pullback zone width in ATR units
    max_entries_per_setup: int = 2     # max total entries allowed per setup

    # ── Setup expiry ──────────────────────────────────────────────────────────
    max_bars_in_state: int = 30        # max bars to wait in any non-IDLE state

    # ── Output ────────────────────────────────────────────────────────────────
    output_dir: Optional[str] = None   # overrides default strategy output/


def default_config() -> VCLSMBConfig:
    return VCLSMBConfig()
