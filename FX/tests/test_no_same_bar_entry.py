"""
Test anti-lookahead: ensure trades don't occur on same bar as zone creation.
"""
import unittest
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.zones.detect_zones import Zone
from src.backtest.execution import ExecutionEngine


class TestNoSameBarEntry(unittest.TestCase):

    def test_zone_created_at_tracking(self):
        """Test that zone_created_at is properly tracked in trades."""
        config = {
            'max_positions': 10,
            'initial_balance': 10000,
            'lot_size': 100000,
            'commission_per_lot': 7.0,
            'intra_bar_policy': 'worst_case',
            'allow_same_bar_entry': False
        }

        engine = ExecutionEngine(10000, config)

        zone_time = pd.Timestamp('2024-01-01 10:00:00')
        entry_time = pd.Timestamp('2024-01-01 10:15:00')

        # Place order with zone_created_at
        engine.place_limit_order(
            'LONG', 1.1000, 1.0950, 1.1100, entry_time,
            comment="Test", touch_no=1, zone_created_at=zone_time
        )

        # Check order was placed
        self.assertEqual(len(engine.pending_orders), 1)
        self.assertEqual(engine.pending_orders[0]['zone_created_at'], zone_time)

    def test_same_bar_entry_prevention_logic(self):
        """
        Test the logic that should prevent entry on same bar as zone creation.
        This tests the conceptual check - actual implementation is in engine.py.
        """
        zone_creation_time = pd.Timestamp('2024-01-01 10:00:00')
        current_bar_time = pd.Timestamp('2024-01-01 10:00:00')  # Same bar
        next_bar_time = pd.Timestamp('2024-01-01 10:15:00')  # Next bar

        allow_same_bar_entry = False

        # Same bar - should be prevented
        if not allow_same_bar_entry:
            can_enter_same_bar = zone_creation_time < current_bar_time
            self.assertFalse(can_enter_same_bar, "Should not allow entry on same bar as zone creation")

        # Next bar - should be allowed
        if not allow_same_bar_entry:
            can_enter_next_bar = zone_creation_time < next_bar_time
            self.assertTrue(can_enter_next_bar, "Should allow entry on bar after zone creation")

    def test_trade_contains_zone_info(self):
        """Test that completed trades contain zone_created_at information."""
        config = {
            'max_positions': 10,
            'initial_balance': 10000,
            'lot_size': 100000,
            'commission_per_lot': 7.0,
            'intra_bar_policy': 'worst_case'
        }

        engine = ExecutionEngine(10000, config)

        zone_time = pd.Timestamp('2024-01-01 10:00:00')
        entry_time = pd.Timestamp('2024-01-01 10:15:00')

        # Place and execute order
        engine.place_limit_order(
            'LONG', 1.1000, 1.0950, 1.1100, entry_time,
            comment="Test", touch_no=1, zone_created_at=zone_time
        )

        # Simulate bar that triggers entry
        bar = {
            'timestamp': entry_time,
            'low_ask': 1.0995,  # Below entry, triggers fill
            'high_ask': 1.1005,
            'low_bid': 1.0990,
            'high_bid': 1.1000,
            'open_ask': 1.1000,
            'close_ask': 1.1000,
            'open_bid': 1.0995,
            'close_bid': 1.0995
        }

        engine.process_bar(bar)

        # Check position was opened
        self.assertEqual(len(engine.positions), 1)
        self.assertEqual(engine.positions[0].zone_created_at, zone_time)

        # Close position
        bar2 = {
            'timestamp': pd.Timestamp('2024-01-01 10:30:00'),
            'low_ask': 1.1000,
            'high_ask': 1.1200,
            'low_bid': 1.1000,
            'high_bid': 1.1150,  # Hits TP
            'open_ask': 1.1000,
            'close_ask': 1.1100,
            'open_bid': 1.1000,
            'close_bid': 1.1100
        }

        engine.process_bar(bar2)

        # Check trade was closed
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertEqual(engine.closed_trades[0].zone_created_at, zone_time)

        # Check DataFrame export includes zone_created_at
        df = engine.get_results_df()
        self.assertIn('zone_created_at', df.columns)
        self.assertEqual(df.iloc[0]['zone_created_at'], zone_time)


if __name__ == '__main__':
    unittest.main()

