"""Speed benchmark: pre-compute once vs per-config."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.research.regime_classifier.backtest_with_regime import load_h1_bars, slice_period, PROOF_V2_SIGNAL_CFG
from src.research.regime_classifier.classifier import RegimeConfig, precompute_features, apply_thresholds
from backtests.signals_bos_pullback import BOSPullbackSignalGenerator, build_d1, build_h4
import pandas as pd

h1 = load_h1_bars("EURUSD")
start_dt = pd.Timestamp("2023-01-01", tz="UTC")
end_dt   = pd.Timestamp("2024-12-31", tz="UTC") + pd.Timedelta(days=1)
h1_full  = slice_period(h1, "2021-06-01", "2024-12-31")

# Time: pre-compute once
t0 = time.perf_counter()
feats = precompute_features(h1_full, RegimeConfig())
gen = BOSPullbackSignalGenerator(PROOF_V2_SIGNAL_CFG)
d1 = build_d1(h1_full); h4 = build_h4(h1_full)
all_s = gen.generate_all("EURUSD", h1_full, d1, h4)
oos_s = [s for s in all_s if start_dt <= s.bar_ts < end_dt]
t_precompute = time.perf_counter() - t0
print(f"Pre-compute: {t_precompute:.2f}s  ({len(oos_s)} OOS setups)")

# Time: apply 3 configs using cached features
configs = [
    RegimeConfig(trend_enter=0.5, chop_enter=0.5),
    RegimeConfig(trend_enter=0.6, chop_enter=0.6),
    RegimeConfig(trend_enter=0.7, chop_enter=0.7),
]
for cfg in configs:
    t1 = time.perf_counter()
    rs = apply_thresholds(feats, cfg)
    print(f"  apply_thresholds: {time.perf_counter()-t1:.2f}s  allowed={rs['trade_allowed'].sum()}")

print(f"\nEstimated total for 54 runs: {t_precompute*3 + len(configs)/3*54*1.5:.0f}s")

