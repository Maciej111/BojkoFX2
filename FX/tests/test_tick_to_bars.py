import unittest
import pandas as pd
import numpy as np
import os
import shutil
import sys
from unittest.mock import patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.data_processing.tick_to_bars import ticks_to_bars

class TestTickToBars(unittest.TestCase):
    def setUp(self):
        self.test_dir = 'test_data'
        self.raw_dir = os.path.join(self.test_dir, 'raw')
        self.bars_dir = os.path.join(self.test_dir, 'bars')
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.bars_dir, exist_ok=True)

        # Create dummy ticks
        self.ticks_csv = os.path.join(self.raw_dir, 'ticks.csv')
        df = pd.DataFrame({
            'timestamp': [
                pd.Timestamp('2024-01-01 10:00:00'),
                pd.Timestamp('2024-01-01 10:05:00'),
                pd.Timestamp('2024-01-01 10:14:59'),
                pd.Timestamp('2024-01-01 10:15:01') # Next bar
            ],
            'bid': [1.0, 1.2, 1.1, 1.5],
            'ask': [1.1, 1.3, 1.2, 1.6],
            'bv': [1, 1, 1, 1],
            'av': [1, 1, 1, 1]
        })
        # Format for dukascopy-node can vary, let's use header
        df.to_csv(self.ticks_csv, index=False)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('src.data_processing.tick_to_bars.load_config')
    def test_resample(self, mock_config):
        mock_config.return_value = {
            'data': {
                'raw_dir': self.raw_dir,
                'bars_dir': self.bars_dir,
                'symbol': 'TEST'
            }
        }

        # Run
        ticks_to_bars()

        # Check output
        bars_file = os.path.join(self.bars_dir, 'TEST_m15_bars.csv')
        self.assertTrue(os.path.exists(bars_file))

        df = pd.read_csv(bars_file, index_col=0, parse_dates=True)

        # Should have 2 bars?
        # 10:00 to 10:15 -> 1 bar (10:00:00) containing 10:00:00, 10:05:00, 10:14:59.
        # 10:15:01 -> Next bar (10:15:00)

        # Bar 1 (10:00):
        # Open Bid: 1.0
        # High Bid: 1.2
        # Low Bid: 1.0
        # Close Bid: 1.1 (last tick at 10:14:59)

        self.assertIn(pd.Timestamp('2024-01-01 10:00:00'), df.index)
        row1 = df.loc[pd.Timestamp('2024-01-01 10:00:00')]

        self.assertAlmostEqual(row1['open_bid'], 1.0)
        self.assertAlmostEqual(row1['high_bid'], 1.2)
        self.assertAlmostEqual(row1['close_bid'], 1.1)

        # Bar 2 (10:15):
        # Starts 10:15:01
        self.assertIn(pd.Timestamp("2024-01-01 10:15:00"), df.index)

    def test_resample_alt_columns(self):
        # Test with askPrice/bidPrice
        alt_ticks_csv = os.path.join(self.raw_dir, 'ticks_alt.csv')
        df = pd.DataFrame({
            'timestamp': [
                pd.Timestamp('2024-01-01 10:00:00'),
                pd.Timestamp('2024-01-01 10:14:59')
            ],
            'bidPrice': [1.0, 1.1],
            'askPrice': [1.1, 1.2],
            'bv': [1, 1],
            'av': [1, 1]
        })
        df.to_csv(alt_ticks_csv, index=False)

        # Patch load_config to point to this new file or just test logic?
        # ticks_to_bars picks the first csv. If I have multiple it might pick wrong one.
        # Let's clear raw dir first
        for f in os.listdir(self.raw_dir):
            os.remove(os.path.join(self.raw_dir, f))

        df.to_csv(alt_ticks_csv, index=False)

        with patch('src.data_processing.tick_to_bars.load_config') as mock_config:
            mock_config.return_value = {
                'data': {
                    'raw_dir': self.raw_dir,
                    'bars_dir': self.bars_dir,
                    'symbol': 'TEST'
                }
            }
            res = ticks_to_bars()

        bars_file = os.path.join(self.bars_dir, 'TEST_m15_bars.csv')
        self.assertTrue(os.path.exists(bars_file))
        df_bars = pd.read_csv(bars_file)
        self.assertIn('close_bid', df_bars.columns)

if __name__ == '__main__':
    unittest.main()

