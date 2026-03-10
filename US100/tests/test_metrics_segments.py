"""
Test metrics computation and segmentation.
"""
import unittest
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest.metrics import (
    compute_expectancy_R,
    compute_profit_factor,
    compute_max_losing_streak,
    compute_max_drawdown,
    compute_segment_metrics,
    add_R_column
)


class TestMetricsSegments(unittest.TestCase):

    def test_expectancy_R(self):
        """Test expectancy R calculation."""
        trades_df = pd.DataFrame({
            'R': [1.5, -1.0, 2.0, -1.0, 1.0]
        })

        expectancy = compute_expectancy_R(trades_df)
        expected = (1.5 - 1.0 + 2.0 - 1.0 + 1.0) / 5
        self.assertAlmostEqual(expectancy, expected, places=3)

    def test_profit_factor(self):
        """Test profit factor calculation."""
        trades_df = pd.DataFrame({
            'pnl': [100, -50, 200, -30, 150]
        })

        pf = compute_profit_factor(trades_df)
        wins = 100 + 200 + 150  # 450
        losses = 50 + 30  # 80
        expected = wins / losses
        self.assertAlmostEqual(pf, expected, places=3)

    def test_profit_factor_no_losses(self):
        """Test profit factor when there are no losses."""
        trades_df = pd.DataFrame({
            'pnl': [100, 200, 150]
        })

        pf = compute_profit_factor(trades_df)
        self.assertEqual(pf, float('inf'))

    def test_profit_factor_no_wins(self):
        """Test profit factor when there are no wins."""
        trades_df = pd.DataFrame({
            'pnl': [-100, -200, -150]
        })

        pf = compute_profit_factor(trades_df)
        self.assertEqual(pf, 0.0)

    def test_max_losing_streak(self):
        """Test max losing streak calculation."""
        trades_df = pd.DataFrame({
            'pnl': [100, -50, -30, -20, 150, -10, -15, 200]
        })

        streak = compute_max_losing_streak(trades_df)
        self.assertEqual(streak, 3)  # Three consecutive losses

    def test_max_losing_streak_no_losses(self):
        """Test max losing streak when there are no losses."""
        trades_df = pd.DataFrame({
            'pnl': [100, 200, 150]
        })

        streak = compute_max_losing_streak(trades_df)
        self.assertEqual(streak, 0)

    def test_max_drawdown(self):
        """Test max drawdown calculation."""
        # Simulate trades that create drawdown
        trades_df = pd.DataFrame({
            'pnl': [100, 200, -500, 100, 200]  # DD after third trade
        })

        initial_balance = 1000
        max_dd_dollars, max_dd_percent = compute_max_drawdown(trades_df, initial_balance)

        # Equity: 1000 -> 1100 -> 1300 -> 800 -> 900 -> 1100
        # Peak: 1300, Trough: 800
        # DD: 500 dollars, 500/1300 = 38.46%

        self.assertAlmostEqual(max_dd_dollars, 500, places=0)
        self.assertAlmostEqual(max_dd_percent, 38.46, places=1)

    def test_add_R_column_long(self):
        """Test R column calculation for LONG trades."""
        trades_df = pd.DataFrame({
            'direction': ['LONG', 'LONG'],
            'entry_price': [1.1000, 1.2000],
            'sl': [1.0950, 1.1950],
            'pnl': [500, -500]  # Win and loss
        })

        trades_df = add_R_column(trades_df)

        # LONG: risk = entry - sl
        # Trade 1: risk = 1.1000 - 1.0950 = 0.0050, risk_dollars = 0.0050 * 100000 = 500
        # R = 500 / 500 = 1.0

        # Trade 2: risk = 1.2000 - 1.1950 = 0.0050, risk_dollars = 500
        # R = -500 / 500 = -1.0

        self.assertAlmostEqual(trades_df.iloc[0]['R'], 1.0, places=2)
        self.assertAlmostEqual(trades_df.iloc[1]['R'], -1.0, places=2)

    def test_add_R_column_short(self):
        """Test R column calculation for SHORT trades."""
        trades_df = pd.DataFrame({
            'direction': ['SHORT', 'SHORT'],
            'entry_price': [1.1000, 1.2000],
            'sl': [1.1050, 1.2050],
            'pnl': [500, -500]  # Win and loss
        })

        trades_df = add_R_column(trades_df)

        # SHORT: risk = sl - entry
        # Trade 1: risk = 1.1050 - 1.1000 = 0.0050, risk_dollars = 500
        # R = 500 / 500 = 1.0

        # Trade 2: risk = 1.2050 - 1.2000 = 0.0050, risk_dollars = 500
        # R = -500 / 500 = -1.0

        self.assertAlmostEqual(trades_df.iloc[0]['R'], 1.0, places=2)
        self.assertAlmostEqual(trades_df.iloc[1]['R'], -1.0, places=2)

    def test_segment_metrics(self):
        """Test segmentation by touch_no."""
        trades_df = pd.DataFrame({
            'touch_no': [1, 1, 2, 2, 1, 2],
            'entry_price': [1.1000, 1.1000, 1.1000, 1.1000, 1.1000, 1.1000],
            'sl': [1.0950, 1.0950, 1.0950, 1.0950, 1.0950, 1.0950],
            'pnl': [500, -500, 1000, 500, 500, -500],
            'direction': ['LONG'] * 6
        })

        trades_df = add_R_column(trades_df)

        initial_balance = 10000
        segments = compute_segment_metrics(trades_df, initial_balance, segment_col='touch_no')

        # Check segments exist
        self.assertIn('ALL', segments)
        self.assertIn('TOUCH_1', segments)
        self.assertIn('TOUCH_2', segments)

        # Check ALL
        self.assertEqual(segments['ALL']['trades_count'], 6)

        # Check TOUCH_1 (indices 0, 1, 4)
        self.assertEqual(segments['TOUCH_1']['trades_count'], 3)
        # Win rate: 2 wins / 3 = 66.67%
        self.assertAlmostEqual(segments['TOUCH_1']['win_rate'], 66.67, places=1)

        # Check TOUCH_2 (indices 2, 3, 5)
        self.assertEqual(segments['TOUCH_2']['trades_count'], 3)
        # Win rate: 2 wins / 3 = 66.67%
        self.assertAlmostEqual(segments['TOUCH_2']['win_rate'], 66.67, places=1)

    def test_segment_metrics_no_column(self):
        """Test segmentation when column doesn't exist - should return ALL only."""
        trades_df = pd.DataFrame({
            'entry_price': [1.1000, 1.1000],
            'sl': [1.0950, 1.0950],
            'pnl': [500, -500],
            'direction': ['LONG', 'LONG']
        })

        trades_df = add_R_column(trades_df)

        initial_balance = 10000
        segments = compute_segment_metrics(trades_df, initial_balance, segment_col='touch_no')

        # Should only have ALL
        self.assertIn('ALL', segments)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments['ALL']['trades_count'], 2)


if __name__ == '__main__':
    unittest.main()

