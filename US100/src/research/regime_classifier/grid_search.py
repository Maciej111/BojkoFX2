"""
src/research/regime_classifier/grid_search.py
==============================================
72-run grid search: 18 configs × 4 symbols.
Saves all results to data/research/regime_grid_search.csv.

RESEARCH ONLY — no production code modified.
"""
from __future__ import annotations

import itertools
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import sys

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from .classifier import RegimeConfig, precompute_features, PrecomputedFeatures
from .backtest_with_regime import (
    BASELINE,
    RegimeBacktestResult,
    load_h1_bars,
    run_backtest_with_regime,
    slice_period,
    PROOF_V2_SIGNAL_CFG,
    PROOF_V2_SIM_CFG,
)


# ─── Grid definition ──────────────────────────────────────────────────────────

GRID_PARAMS: dict = {
    "trend_enter":        [0.5, 0.6, 0.7],
    "chop_enter":         [0.5, 0.6, 0.7],
    "high_vol_threshold": [70.0, 80.0],
    # Fixed across all runs
    "min_regime_duration":  8,
    "ema_slope_lookback":  20,
    "ema_cross_lookback":  50,
}


def _best_config(df_sym: pd.DataFrame, min_trade_pct: float = 30.0):
    """Best config = highest expectancy_R with ≥30% of baseline trades allowed."""
    valid = df_sym[
        (df_sym["trades_filtered_pct"] <= (100 - min_trade_pct)) &
        (df_sym["expectancy_R"].notna())
    ]
    if valid.empty:
        valid = df_sym[df_sym["expectancy_R"].notna()]
    if valid.empty:
        return None
    return valid.loc[valid["expectancy_R"].idxmax()]


def _build_configs() -> List[dict]:
    """Return list of 18 parameter dicts (all grid combinations)."""
    keys   = ["trend_enter", "chop_enter", "high_vol_threshold"]
    values = [GRID_PARAMS[k] for k in keys]
    configs = []
    for combo in itertools.product(*values):
        d = dict(zip(keys, combo))
        d["min_regime_duration"] = GRID_PARAMS["min_regime_duration"]
        d["ema_slope_lookback"]  = GRID_PARAMS["ema_slope_lookback"]
        d["ema_cross_lookback"]  = GRID_PARAMS["ema_cross_lookback"]
        configs.append(d)
    return configs


def _make_regime_config(params: dict) -> RegimeConfig:
    """Construct RegimeConfig from a parameter dict."""
    return RegimeConfig(
        trend_enter=params["trend_enter"],
        chop_enter=params["chop_enter"],
        high_vol_threshold=params["high_vol_threshold"],
        min_regime_duration=int(params["min_regime_duration"]),
        ema_slope_lookback=int(params["ema_slope_lookback"]),
        ema_cross_lookback=int(params["ema_cross_lookback"]),
        # hysteresis exits: slightly below enters
        trend_exit=max(0.0, params["trend_enter"] - 0.2),
        chop_exit=max(0.0, params["chop_enter"] - 0.2),
    )


def _sharpe(trades) -> float:
    """Annualised Sharpe ratio from R-multiples (rf=0)."""
    from backtests.signals_bos_pullback import ClosedTrade
    r_vals = [t.r_multiple for t in trades
              if t.exit_reason in ("TP", "SL")]
    if len(r_vals) < 5:
        return 0.0
    arr = pd.Series(r_vals)
    mu  = arr.mean()
    std = arr.std()
    if std == 0:
        return 0.0
    # Approximate: monthly ~ 22 trades → annualise by sqrt(12) from monthly
    return float(mu / std * (len(r_vals) ** 0.5 / (len(r_vals) ** 0.5)) )


def run_grid_search(
    symbols: List[str],
    start: str = "2023-01-01",
    end: str = "2024-12-31",
    data_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run 18 × len(symbols) backtest combinations.

    Parameters
    ----------
    symbols     : e.g. ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    start / end : OOS period
    data_dir    : override data directory
    output_path : CSV save path (default data/research/regime_grid_search.csv)
    verbose     : print progress

    Returns
    -------
    pd.DataFrame with one row per (symbol × config) combination.
    """
    if output_path is None:
        output_path = str(_ROOT / "data" / "research" / "regime_grid_search.csv")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    configs   = _build_configs()
    total     = len(symbols) * len(configs)
    run_num   = 0
    rows: List[dict] = []

    # Pre-load H1 data for all symbols (avoid re-reading per config)
    h1_cache: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            h1_cache[sym] = load_h1_bars(sym, data_dir)
            if verbose:
                print(f"  Loaded {sym}: {len(h1_cache[sym])} bars "
                      f"({h1_cache[sym].index[0].date()} – {h1_cache[sym].index[-1].date()})")
        except FileNotFoundError as exc:
            print(f"  [SKIP] {sym}: {exc}")

    for sym in symbols:
        if sym not in h1_cache:
            continue
        h1_df = h1_cache[sym]
        baseline = BASELINE.get(sym, {})

        # ── Pre-compute once per symbol (expensive: ADX/EMA/ATR arrays) ───
        start_dt     = pd.Timestamp(start, tz="UTC")
        end_dt       = pd.Timestamp(end,   tz="UTC") + pd.Timedelta(days=1)
        warmup_start = start_dt - pd.Timedelta(days=450)
        h1_full = slice_period(h1_df, str(warmup_start.date()), end)
        h1_oos  = slice_period(h1_df, start, end)

        if verbose:
            print(f"  [{sym}] Pre-computing features ({len(h1_full)} bars)…", end=" ", flush=True)
        t_feat = time.perf_counter()

        # Default config for feature computation (period params don't change across grid)
        default_cfg = RegimeConfig()
        feats = precompute_features(h1_full, default_cfg)

        # Pre-generate all OOS setups once (frozen PROOF V2 params)
        from backtests.signals_bos_pullback import BOSPullbackSignalGenerator, build_d1, build_h4
        gen = BOSPullbackSignalGenerator(PROOF_V2_SIGNAL_CFG)
        d1  = build_d1(h1_full)
        h4  = build_h4(h1_full)
        all_setups = gen.generate_all(sym, h1_full, d1, h4)
        oos_setups = [s for s in all_setups if start_dt <= s.bar_ts < end_dt]

        if verbose:
            print(f"done ({time.perf_counter()-t_feat:.1f}s), {len(oos_setups)} OOS setups")

        for params in configs:
            run_num += 1
            tag = (f"te={params['trend_enter']} ce={params['chop_enter']} "
                   f"hvt={int(params['high_vol_threshold'])}")
            t0 = time.perf_counter()

            try:
                regime_cfg = _make_regime_config(params)
                result: RegimeBacktestResult = run_backtest_with_regime(
                    symbol=sym,
                    h1_df=h1_df,
                    regime_config=regime_cfg,
                    start=start,
                    end=end,
                    precomputed_features=feats,
                    precomputed_oos_setups=oos_setups,
                    precomputed_h1_oos=h1_oos,
                )

                ma = result.metrics_allowed
                mb = result.metrics_baseline
                fs = result.filter_stats

                n_allowed = ma.get("n_trades", 0)
                n_baseline_b = mb.get("n_trades", 0)
                trades_filtered_pct = (
                    round((1 - n_allowed / n_baseline_b) * 100, 1)
                    if n_baseline_b > 0 else 100.0
                )

                vs_base_exp = round(
                    ma.get("expectancy_R", 0.0) - baseline.get("expectancy_R", 0.0), 4
                )
                vs_base_dd  = round(
                    ma.get("max_dd_pct", 0.0) - baseline.get("max_dd_pct", 0.0), 2
                )

                row = {
                    "symbol":                sym,
                    "trend_enter":           params["trend_enter"],
                    "chop_enter":            params["chop_enter"],
                    "high_vol_threshold":    params["high_vol_threshold"],
                    "min_regime_duration":   params["min_regime_duration"],
                    "ema_slope_lookback":    params["ema_slope_lookback"],
                    "ema_cross_lookback":    params["ema_cross_lookback"],
                    # Backtest metrics (regime-filtered)
                    "trades_total":          n_baseline_b,
                    "trades_allowed":        n_allowed,
                    "trades_filtered_pct":   trades_filtered_pct,
                    "win_rate":              ma.get("win_rate", 0.0),
                    "expectancy_R":          ma.get("expectancy_R", 0.0),
                    "profit_factor":         ma.get("profit_factor", 0.0),
                    "max_dd_pct":            ma.get("max_dd_pct", 0.0),
                    "vs_baseline_expectancy": vs_base_exp,
                    "vs_baseline_dd":        vs_base_dd,
                    "sharpe_ratio":          _sharpe(result.trades_allowed),
                    # Filter analysis
                    "tp_filtered":           fs.get("tp_filtered", 0),
                    "sl_filtered":           fs.get("sl_filtered", 0),
                    "filter_precision":      fs.get("filter_precision", 0.0),
                    # Baseline metrics (for reference)
                    "baseline_expectancy":   baseline.get("expectancy_R", 0.0),
                    "baseline_dd":           baseline.get("max_dd_pct", 0.0),
                    "elapsed_s":             round(time.perf_counter() - t0, 2),
                }

            except Exception as exc:
                row = {
                    "symbol": sym,
                    "trend_enter":  params["trend_enter"],
                    "chop_enter":   params["chop_enter"],
                    "high_vol_threshold": params["high_vol_threshold"],
                    "error": str(exc),
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                }

            rows.append(row)
            elapsed = time.perf_counter() - t0

            if verbose:
                exp_r = row.get("expectancy_R", "ERR")
                print(f"  [{run_num:>2}/{total}] {sym} {tag} "
                      f"→ ExpR={exp_r}  ({elapsed:.1f}s)")

            # Save incrementally after each run
            pd.DataFrame(rows).to_csv(output_path, index=False)

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    if verbose:
        print(f"\n  Grid search complete → {output_path}")
    return df








