import unittest
from datetime import datetime
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.backtest.execution import ExecutionEngine, Trade

class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        self.config = {
            'max_positions': 1,
            'lot_size': 100000,
            'commission_per_lot': 7.0,
            'intra_bar_policy': 'worst_case'
        }
        self.engine = ExecutionEngine(10000, self.config)
        self.timestamp = datetime(2024, 1, 1, 10, 0)

    def test_long_limit_entry(self):
        # Place Buy Limit at 1.1000
        self.engine.place_limit_order('LONG', 1.1000, 1.0950, 1.1100, self.timestamp)

        # Bar with low_ask = 1.1000 -> Should fill
        bar = {
            'timestamp': self.timestamp,
            'open_bid': 1.1010, 'high_bid': 1.1020, 'low_bid': 1.0990, 'close_bid': 1.1010,
            'open_ask': 1.1011, 'high_ask': 1.1021, 'low_ask': 1.1000, 'close_ask': 1.1011
        }
        self.engine.process_bar(bar)

        self.assertEqual(len(self.engine.positions), 1)
        self.assertEqual(self.engine.positions[0].entry_price, 1.1000)

    def test_long_sl_hit(self):
        # Open Long
        self.engine.place_limit_order('LONG', 1.1000, 1.0950, 1.1100, self.timestamp)
        # Fill
        bar_fill = {
            'timestamp': self.timestamp,
            'open_bid': 1.1000, 'high_bid': 1.1000, 'low_bid': 1.1000, 'close_bid': 1.1000,
            'open_ask': 1.1000, 'high_ask': 1.1000, 'low_ask': 1.1000, 'close_ask': 1.1000
        }
        self.engine.process_bar(bar_fill)

        # Next bar hits SL (Bid drops to 1.0950)
        bar_sl = {
            'timestamp': self.timestamp,
            'open_bid': 1.1000, 'high_bid': 1.1000, 'low_bid': 1.0950, 'close_bid': 1.0950,
            'open_ask': 1.1001, 'high_ask': 1.1001, 'low_ask': 1.0951, 'close_ask': 1.0951
        }
        self.engine.process_bar(bar_sl)

        self.assertEqual(len(self.engine.positions), 0)
        self.assertEqual(len(self.engine.closed_trades), 1)
        self.assertEqual(self.engine.closed_trades[0].status, 'SL')

if __name__ == '__main__':
    unittest.main()

