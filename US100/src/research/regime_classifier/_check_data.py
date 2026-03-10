"""Check EURUSD 2025 data availability."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.research.regime_classifier.backtest_with_regime import load_h1_bars

h1 = load_h1_bars("EURUSD")
print(f"Total rows : {len(h1)}")
print(f"First      : {h1.index[0]}")
print(f"Last       : {h1.index[-1]}")
rows_2025 = h1.loc["2025-01-01":].shape[0]
print(f"2025 rows  : {rows_2025}")
print(f"2025 last  : {h1.loc['2025-01-01':].index[-1] if rows_2025 > 0 else 'N/A'}")

