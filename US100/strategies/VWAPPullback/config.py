"""
Strategy-specific configuration for VWAPPullback.

All shared infrastructure is reused from:
  scripts.run_backtest_idx   (load_ltf)
  bojkofx_shared.indicators.atr  (calculate_atr)
"""
from dataclasses import dataclass


@dataclass
class VWAPPullbackConfig:
    # ── Trend filter ──────────────────────────────────────────────────────────
    ema_period_htf: int = 50            # EMA period on 1h bars
    ema_filter_enabled: bool = True

    # ── VWAP anchor ───────────────────────────────────────────────────────────
    # VWAP resets at midnight UTC each day (equal-weight TP average;
    # no tick volume available for NAS100 CFD bars).
    # The session_start_hour_utc filter means signals only appear after
    # the US open, by which time the VWAP has accumulated ~14h of data.

    # ── Pullback detection ────────────────────────────────────────────────────
    vwap_tolerance_atr_mult: float = 0.5  # low_bid must reach within N*ATR of VWAP
    min_bars_above_vwap: int = 3          # require N prior bars with close > VWAP

    # ── Confirmation candle ───────────────────────────────────────────────────
    min_body_ratio: float = 0.1           # (close-open)/(high-low) >= this
    require_close_above_vwap: bool = True # confirmation bar must close > VWAP

    # ── Stop loss ─────────────────────────────────────────────────────────────
    stop_buffer_atr_mult: float = 0.3     # SL = pullback_low - N*ATR

    # ── Take profit ───────────────────────────────────────────────────────────
    take_profit_rr: float = 1.5

    # ── Session ───────────────────────────────────────────────────────────────
    session_start_hour_utc: int = 14      # ignore signals before NY open (14:30 UTC)
    session_end_hour_utc: int = 21        # EOD close at 21:00 UTC

    # ── Capacity ─────────────────────────────────────────────────────────────
    max_trades_per_day: int = 1

    # ── ATR ───────────────────────────────────────────────────────────────────
    atr_period: int = 14


# Baseline configuration used by the mini-test
BASE_CONFIG = VWAPPullbackConfig()


@dataclass
class VWAPPullbackV2Config:
    """
    VWAPPullback v2 — session-anchored VWAP with strict touch detection.

    Key changes vs v1:
      - VWAP resets at session open (14:30 UTC) not midnight
      - Pullback = strict VWAP touch: low_bid <= vwap  (no ATR buffer)
      - body_ratio requirement removed; close > open is sufficient
      - max_trades_per_day raised to 2
    """
    # ── Trend filter ──────────────────────────────────────────────────────────
    ema_period_htf: int = 50
    ema_filter_enabled: bool = True

    # ── Session VWAP anchor ───────────────────────────────────────────────────
    # VWAP resets at session open; bars before anchor = NaN.
    session_open_hour: int = 14
    session_open_minute: int = 30

    # ── Pullback detection ────────────────────────────────────────────────────
    # Strict: low_bid must actually touch VWAP (no ATR buffer)
    min_bars_above_vwap: int = 0          # 0 = disabled in v2

    # ── Confirmation candle ───────────────────────────────────────────────────
    require_close_above_vwap: bool = True # close_bid > vwap required

    # ── Stop loss ─────────────────────────────────────────────────────────────
    stop_buffer_atr_mult: float = 0.3     # SL = pullback_low - N*ATR

    # ── Take profit ───────────────────────────────────────────────────────────
    take_profit_rr: float = 1.5

    # ── Session ───────────────────────────────────────────────────────────────
    session_close_hour: int = 21          # EOD close at 21:00 UTC

    # ── Capacity ─────────────────────────────────────────────────────────────
    max_trades_per_day: int = 2

    # ── ATR ───────────────────────────────────────────────────────────────────
    atr_period: int = 14


# Baseline v2 configuration
BASE_CONFIG_V2 = VWAPPullbackV2Config()
