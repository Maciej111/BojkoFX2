"""
Signal dataclass for VCLSMB.

A Signal represents the tradeable output of the strategy at the moment
MOMENTUM_CONFIRMED is reached.  It is produced by signals.py and consumed
by strategy.py to form trade records.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    bar_idx:         int           # LTF bar index of momentum confirmation
    bar_time:        pd.Timestamp  # timestamp of that bar
    direction:       str           # "LONG" | "SHORT"
    entry_price:     float         # intended fill price
    planned_sl:      float
    planned_tp:      float
    risk_distance:   float
    range_high:      float
    range_low:       float
    sweep_bar_idx:   Optional[int]
    compression_atr: float         # ATR at momentum bar (for audit)
