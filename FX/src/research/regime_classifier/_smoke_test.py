"""Quick smoke test — run before full grid search."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.research.regime_classifier.backtest_with_regime import load_h1_bars, run_backtest_with_regime
from src.research.regime_classifier.classifier import RegimeConfig

print("Loading EURUSD...")
h1 = load_h1_bars("EURUSD")
print(f"  {len(h1)} bars  {h1.index[0].date()} – {h1.index[-1].date()}")

cfg = RegimeConfig(trend_enter=0.6, chop_enter=0.6, high_vol_threshold=75.0)
print("Running single backtest (EURUSD 2023-2024)...")
r = run_backtest_with_regime("EURUSD", h1, cfg, start="2023-01-01", end="2024-12-31")

mb = r.metrics_baseline
ma = r.metrics_allowed
fs = r.filter_stats
print(f"  Baseline : n={mb['n_trades']}  WR={mb['win_rate']:.1%}  ExpR={mb['expectancy_R']:+.3f}  DD={mb['max_dd_pct']:.1f}%")
print(f"  Filtered : n={ma['n_trades']}  WR={ma['win_rate']:.1%}  ExpR={ma['expectancy_R']:+.3f}  DD={ma['max_dd_pct']:.1f}%")
print(f"  Blocked  : {fs['trades_filtered_pct']}%  precision={fs['filter_precision']:.1%}")
print("Smoke test PASSED")

