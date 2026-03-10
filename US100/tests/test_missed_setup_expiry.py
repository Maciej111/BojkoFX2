"""Test Missed Setup Expiry Logic"""
import pytest
import pandas as pd
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest.setup_tracker import SetupTracker

def test_setup_expiry():
    """Test that setup expires after max bars."""
    tracker = SetupTracker()

    tracker.create_setup(
        direction='SHORT',
        bos_level=1.2000,
        bos_time=pd.Timestamp('2024-01-01 10:00'),
        entry_price=1.1970,
        expiry_time=pd.Timestamp('2024-01-01 12:00'),
        expiry_bar_count=2,
        htf_bias='BEAR',
        ltf_pivot_type='pivot_low'
    )

    assert tracker.has_active_setup(), "Setup should be active"

    # Check fill AFTER expiry
    bar = pd.Series({
        'low_ask': 1.1960,
        'high_ask': 1.1990,
        'low_bid': 1.1955,
        'high_bid': 1.1985
    })

    # Try to fill after expiry time
    filled = tracker.check_fill(bar, pd.Timestamp('2024-01-01 13:00'))

    assert filled == False, "Setup should NOT fill after expiry"
    assert tracker.get_active_setup() is None, "Active setup should be cleared"
    assert len(tracker.missed_setups) == 1, "Missed setup should be recorded"

    stats = tracker.get_stats()
    assert stats['missed_setups'] == 1, "Stats should show 1 missed setup"
    assert stats['missed_rate'] == 1.0, "Missed rate should be 100%"

    print("✓ Setup expiry works correctly")

if __name__ == "__main__":
    test_setup_expiry()
    print("\n✅ All expiry tests passed!")

