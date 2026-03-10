"""Test BOS Pullback Setup Creation and Fill"""
import pytest
import pandas as pd
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest.setup_tracker import SetupTracker

def test_setup_creation_and_fill():
    """Test setup creation and fill logic."""
    tracker = SetupTracker()

    # Create setup
    tracker.create_setup(
        direction='LONG',
        bos_level=1.1000,
        bos_time=pd.Timestamp('2024-01-01 10:00'),
        entry_price=1.1030,
        expiry_time=pd.Timestamp('2024-01-01 14:00'),
        expiry_bar_count=4,
        htf_bias='BULL',
        ltf_pivot_type='pivot_high'
    )

    assert tracker.has_active_setup(), "Setup should be active after creation"

    # Try fill with bar that touches entry
    bar = pd.Series({
        'low_ask': 1.1025,
        'high_ask': 1.1050,
        'low_bid': 1.1020,
        'high_bid': 1.1045
    })

    filled = tracker.check_fill(bar, pd.Timestamp('2024-01-01 11:00'))
    assert filled == True, "Setup should be filled when price touches entry"
    assert tracker.get_active_setup() is None, "Active setup should be cleared after fill"
    assert len(tracker.filled_setups) == 1, "Filled setup should be recorded"

    print("✓ Setup creation and fill works correctly")

if __name__ == "__main__":
    test_setup_creation_and_fill()
    print("\n✅ All setup tests passed!")

