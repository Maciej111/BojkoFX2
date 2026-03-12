"""
VolatilityContractionLiquiditySweepMomentumBreakout strategy package.

Pipeline:
  IDLE → COMPRESSION (volatility contraction) → SWEEP_DETECTED (liquidity sweep)
  → MOMENTUM_CONFIRMED (breakout momentum) → IN_POSITION → IDLE
"""
from .strategy import run_vclsmb_backtest
from .config import VCLSMBConfig, default_config

__all__ = ["run_vclsmb_backtest", "VCLSMBConfig", "default_config"]
