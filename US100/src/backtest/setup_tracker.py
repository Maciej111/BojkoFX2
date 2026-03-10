"""Setup Tracker - BOS to Pullback Entry"""
import pandas as pd
from dataclasses import dataclass
from typing import Optional

@dataclass
class PullbackSetup:
    direction: str
    bos_level: float
    bos_time: pd.Timestamp
    entry_price: float
    expiry_time: pd.Timestamp
    expiry_bar_count: int
    htf_bias: str
    ltf_pivot_type: str
    # setup_type distinguishes signal origin:
    #   'BOS'              — Break-of-Structure pullback (original path)
    #   'FLAG_CONTRACTION' — Impulse + contraction + breakout continuation
    setup_type: str = 'BOS'
    # Precomputed SL for FLAG_CONTRACTION setups (None for BOS → derived at fill time)
    sl_price: Optional[float] = None
    is_filled: bool = False
    is_expired: bool = False
    fill_time: Optional[pd.Timestamp] = None
    bars_to_fill: Optional[int] = None

class SetupTracker:
    def __init__(self):
        self.active_setup = None
        self.missed_setups = []
        self.filled_setups = []

    def has_active_setup(self):
        return self.active_setup is not None and not self.active_setup.is_filled and not self.active_setup.is_expired

    def create_setup(
        self, direction, bos_level, bos_time, entry_price, expiry_time,
        expiry_bar_count, htf_bias, ltf_pivot_type,
        setup_type: str = 'BOS',
        sl_price: Optional[float] = None,
    ):
        if self.active_setup and not self.active_setup.is_filled:
            self.active_setup.is_expired = True
            self.missed_setups.append(self.active_setup)
        self.active_setup = PullbackSetup(
            direction, bos_level, bos_time, entry_price, expiry_time,
            expiry_bar_count, htf_bias, ltf_pivot_type,
            setup_type=setup_type,
            sl_price=sl_price,
        )

    def check_fill(self, current_bar, current_time):
        if not self.has_active_setup():
            return False
        setup = self.active_setup
        if current_time >= setup.expiry_time:
            setup.is_expired = True
            self.missed_setups.append(setup)
            self.active_setup = None
            return False
        filled = False
        if setup.direction == 'LONG':
            if current_bar['low_ask'] <= setup.entry_price <= current_bar['high_ask']:
                filled = True
        elif setup.direction == 'SHORT':
            if current_bar['low_bid'] <= setup.entry_price <= current_bar['high_bid']:
                filled = True
        if filled:
            setup.is_filled = True
            setup.fill_time = current_time
            self.filled_setups.append(setup)
            return True
        return False

    def get_active_setup(self):
        return self.active_setup if self.has_active_setup() else None

    def clear_active_setup(self):
        self.active_setup = None

    def get_stats(self):
        total = len(self.filled_setups) + len(self.missed_setups)
        if total == 0:
            return {'total_setups': 0, 'filled_setups': 0, 'missed_setups': 0, 'missed_rate': 0.0, 'avg_bars_to_fill': 0.0}
        bars_list = [s.bars_to_fill for s in self.filled_setups if s.bars_to_fill is not None]
        avg_bars = sum(bars_list) / len(bars_list) if bars_list else 0.0
        return {'total_setups': total, 'filled_setups': len(self.filled_setups), 'missed_setups': len(self.missed_setups),
                'missed_rate': len(self.missed_setups) / total if total > 0 else 0.0, 'avg_bars_to_fill': avg_bars}

