import sys
import os

# Add project root to sys path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.backtest.engine import run_backtest

if __name__ == "__main__":
    print("Running Supply & Demand Backtest...")
    run_backtest()

