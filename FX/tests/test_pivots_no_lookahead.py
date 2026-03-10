"""Test Pivot Confirmation - Anti-lookahead"""
import pytest
import pandas as pd
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.structure.pivots import detect_pivots_confirmed

def test_pivot_confirmation_delay():
    """Test that pivots are confirmed only after k bars."""
    dates = pd.date_range('2024-01-01', periods=20, freq='h')
    highs = [1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 1.1, 1.2, 1.1, 1.0] + [1.0]*10
    lows = [1.0, 1.1, 1.2, 1.1, 1.0, 0.9, 1.0, 1.1, 1.0, 0.9] + [0.9]*10

    df = pd.DataFrame({'high_bid': highs, 'low_bid': lows}, index=dates)

    # Detect with confirmation=1
    ph, pl, ph_lvl, pl_lvl = detect_pivots_confirmed(df, lookback=2, confirmation_bars=1)

    # Pivot at bar 2 should be confirmed at bar 3
    assert ph.iloc[2] == False, "Pivot should NOT be confirmed at detection bar"
    assert ph.iloc[3] == True, "Pivot should be confirmed 1 bar later"

    print("✓ Pivot confirmation delay works correctly")

if __name__ == "__main__":
    test_pivot_confirmation_delay()
    print("\n✅ All pivot tests passed!")


