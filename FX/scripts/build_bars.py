import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.data_processing.tick_to_bars import ticks_to_bars

if __name__ == "__main__":
    ticks_to_bars()

