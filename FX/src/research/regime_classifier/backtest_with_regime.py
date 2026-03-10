"""
src/research/regime_classifier/backtest_with_regime.py
=======================================================
Backtest integration: wraps the existing BOS+Pullback backtest engine
by pre-filtering trade signals with the regime classifier.

RESEARCH ONLY — does NOT modify any production code.

Usage
-----
from src.research.regime_classifier.backtest_with_regime import run_backtest_with_regime

result = run_backtest_with_regime(
    symbol="EURUSD",
    h1_df=eurusd_h1,
    regime_config=cfg,
    start="2023-01-01",
    end="2024-12-31",
)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import sys

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from backtests.engine import PortfolioSimulator
from backtests.signals_bos_pullback import (
    BOSPullbackSignalGenerator,
    ClosedTrade,
    TradeSetup,
    build_d1,
    build_h4,
    filter_and_adjust,
)
from backtests.metrics import calc_metrics

from .classifier import (
    RegimeConfig, compute_regime_series, is_trade_allowed,
    PrecomputedFeatures, precompute_features, apply_thresholds,
)


# ─── Frozen PROOF V2 strategy parameters ─────────────────────────────────────

PROOF_V2_SIGNAL_CFG: dict = {
    "pivot_lookback":        3,
    "entry_offset_atr_mult": 0.3,
    "sl_buffer_atr_mult":    0.1,
    "rr":                    3.0,
    "ttl_bars":              50,
    "atr_period":            14,
    "atr_pct_window":        100,
    "rr_mode":               "fixed",
}

PROOF_V2_SIM_CFG: dict = {
    "sizing": {"mode": "fixed_units", "units": 5000},
    "same_bar_mode": "conservative",
    "max_positions_total": 3,
    "max_positions_per_symbol": 1,
    "initial_equity": 10_000.0,
}

# Baseline Proof V2 results (from prompt, used for delta calculations)
BASELINE: Dict[str, dict] = {
    "EURUSD": {"n_trades": 234, "win_rate": 0.466, "expectancy_R": 0.212,
               "profit_factor": 1.03, "max_dd_pct": 17.0},
    "GBPUSD": {"n_trades": 200, "win_rate": 0.485, "expectancy_R": 0.572,
               "profit_factor": 1.71, "max_dd_pct": 26.9},
    "USDJPY": {"n_trades": 225, "win_rate": 0.498, "expectancy_R": 0.300,
               "profit_factor": 1.14, "max_dd_pct": 16.2},
    "XAUUSD": {"n_trades": 220, "win_rate": 0.482, "expectancy_R": 0.178,
               "profit_factor": 1.22, "max_dd_pct": 19.1},
}


# ─── Data loading helper ──────────────────────────────────────────────────────

def load_h1_bars(symbol: str, data_dir: Optional[str] = None) -> pd.DataFrame:
    """
    Load H1 bars for a symbol.  Searches data/bars_validated/ first,
    then data/raw_dl_fx/download/m60/.

    Returns DataFrame with columns: open, high, low, close.
    Index: tz-aware UTC DatetimeIndex.
    """
    if data_dir is None:
        data_dir = str(_ROOT / "data")

    base = Path(data_dir)
    sym_l = symbol.lower()

    candidates = [
        # m60 bid data — same source used by PROOF V2 backtests (highest priority)
        base / "raw_dl_fx" / "download" / "m60" / f"{sym_l}_m60_bid_2021_2025.csv",
        base / "raw_dl_fx" / "download" / "m60" / f"{sym_l}_m60_bid_2021_2024.csv",
        # validated bars fallback
        base / "bars_validated" / f"{sym_l}_1h_validated.csv",
        base / "bars_validated" / f"{sym_l}_h1_bars.csv",
        base / "bars" / f"{sym_l}_h1_bars.csv",
    ]

    path = next((p for p in candidates if p.exists() and p.stat().st_size > 100), None)
    if path is None:
        raise FileNotFoundError(
            f"No H1 data found for {symbol} (checked {len(candidates)} paths, "
            f"all missing or empty). Searched:\n" + "\n".join(str(p) for p in candidates)
        )

    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]

    # Normalise bid_* → open/high/low/close
    for src, dst in [("bid_open", "open"), ("bid_high", "high"),
                     ("bid_low", "low"), ("bid_close", "close")]:
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]

    # Parse timestamp
    ts_col = next((c for c in ("datetime", "timestamp", "time", "date")
                   if c in df.columns), None)
    if ts_col is None:
        ts_col = df.columns[0]

    try:
        first = float(df[ts_col].iloc[0])
        df.index = pd.to_datetime(df[ts_col], unit="ms", utc=True) \
                   if first > 1e10 \
                   else pd.to_datetime(df[ts_col], utc=True)
    except (ValueError, TypeError):
        df.index = pd.to_datetime(df[ts_col], utc=True)

    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")

    # Keep only OHLC
    keep = [c for c in ("open", "high", "low", "close") if c in df.columns]
    df = df[keep].copy()
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def slice_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Slice DataFrame to [start, end] inclusive."""
    return df.loc[start:end].copy()


# ─── Core backtest function ───────────────────────────────────────────────────

@dataclass
class RegimeBacktestResult:
    symbol: str
    trades_baseline: List[ClosedTrade]
    trades_allowed: List[ClosedTrade]
    trades_filtered: List[ClosedTrade]
    metrics_baseline: dict
    metrics_allowed: dict
    regime_series: pd.DataFrame   # timestamp → regime/scores
    filter_stats: dict            # TP/SL filtered counts


def run_backtest_with_regime(
    symbol: str,
    h1_df: pd.DataFrame,
    regime_config: RegimeConfig,
    start: str = "2023-01-01",
    end: str = "2024-12-31",
    signal_cfg: Optional[dict] = None,
    sim_cfg: Optional[dict] = None,
    # Optional pre-computed objects for speed in grid search
    precomputed_features: Optional[PrecomputedFeatures] = None,
    precomputed_oos_setups: Optional[List[TradeSetup]] = None,
    precomputed_h1_oos: Optional[pd.DataFrame] = None,
) -> RegimeBacktestResult:
    """
    Run BOS+Pullback backtest and split trades by regime filter.

    Steps
    -----
    1. Generate all signals (unfiltered) using PROOF V2 parameters.
    2. Pre-compute regime series for full date range.
    3. Filter trades: mark each as ALLOWED or FILTERED based on regime
       at the signal bar (entry intent bar, before fill).
    4. Simulate portfolio for ALLOWED trades only.
    5. Return both metric sets.
    """
    if signal_cfg is None:
        signal_cfg = PROOF_V2_SIGNAL_CFG.copy()
    if sim_cfg is None:
        sim_cfg = PROOF_V2_SIM_CFG.copy()

    start_dt = pd.Timestamp(start, tz="UTC")
    end_dt   = pd.Timestamp(end,   tz="UTC") + pd.Timedelta(days=1)
    warmup_start = start_dt - pd.Timedelta(days=450)

    # ── Use pre-computed objects if provided (fast grid search path) ───────
    if precomputed_oos_setups is not None and precomputed_h1_oos is not None:
        oos_setups = precomputed_oos_setups
        h1_oos     = precomputed_h1_oos
    else:
        h1_full = slice_period(h1_df, str(warmup_start.date()), end)
        h1_oos  = slice_period(h1_df, start, end)
        if len(h1_full) < 250:
            raise ValueError(f"{symbol}: not enough bars ({len(h1_full)}) for warmup")
        gen = BOSPullbackSignalGenerator(signal_cfg)
        d1  = build_d1(h1_full)
        h4  = build_h4(h1_full)
        all_setups: List[TradeSetup] = gen.generate_all(symbol, h1_full, d1, h4)
        oos_setups = [s for s in all_setups if start_dt <= s.bar_ts < end_dt]

    # ── Regime series: use apply_thresholds if features pre-computed ───────
    if precomputed_features is not None:
        regime_series = apply_thresholds(precomputed_features, regime_config)
    else:
        h1_full = slice_period(h1_df, str(warmup_start.date()), end)
        regime_series = compute_regime_series(h1_full, regime_config)

    regime_oos = regime_series.loc[start:] if start in regime_series.index or True else regime_series

    # ── 4. Simulate BASELINE (all OOS signals, no regime filter) ──────────────
    sim_baseline = PortfolioSimulator(
        h1_data={symbol: h1_oos},
        setups={symbol: oos_setups},
        sizing_cfg=sim_cfg["sizing"],
        session_cfg={},
        same_bar_mode=sim_cfg.get("same_bar_mode", "conservative"),
        max_positions_total=sim_cfg.get("max_positions_total", 3),
        max_positions_per_symbol=sim_cfg.get("max_positions_per_symbol", 1),
        initial_equity=sim_cfg.get("initial_equity", 10_000.0),
    )
    trades_baseline = sim_baseline.run()
    metrics_baseline = calc_metrics(trades_baseline, label=f"{symbol}_baseline")

    # ── 5. Filter setups by regime at signal bar ───────────────────────────────
    allowed_setups: List[TradeSetup] = []
    for setup in oos_setups:
        # Look up regime at the bar that generated the signal
        try:
            # Use the last available regime at or before bar_ts
            idx_pos = regime_series.index.searchsorted(setup.bar_ts, side="right")
            if idx_pos == 0:
                allowed_setups.append(setup)  # no data yet — allow
                continue
            row = regime_series.iloc[idx_pos - 1]
            allowed = bool(row["trade_allowed"])
        except (KeyError, IndexError):
            allowed = True

        if allowed:
            allowed_setups.append(setup)

    # ── 6. Simulate FILTERED (regime-allowed signals only) ────────────────────
    sim_allowed = PortfolioSimulator(
        h1_data={symbol: h1_oos},
        setups={symbol: allowed_setups},
        sizing_cfg=sim_cfg["sizing"],
        session_cfg={},
        same_bar_mode=sim_cfg.get("same_bar_mode", "conservative"),
        max_positions_total=sim_cfg.get("max_positions_total", 3),
        max_positions_per_symbol=sim_cfg.get("max_positions_per_symbol", 1),
        initial_equity=sim_cfg.get("initial_equity", 10_000.0),
    )
    trades_allowed = sim_allowed.run()
    metrics_allowed = calc_metrics(trades_allowed, label=f"{symbol}_regime_filtered")

    # ── 7. Compute filter stats (which TP/SL trades were filtered out) ────────
    allowed_entry_ts = {t.entry_ts for t in trades_allowed}
    trades_filtered  = [t for t in trades_baseline
                        if t.entry_ts not in allowed_entry_ts
                        and t.exit_reason != "TTL"]
    tp_filtered  = sum(1 for t in trades_filtered if t.exit_reason == "TP")
    sl_filtered  = sum(1 for t in trades_filtered if t.exit_reason == "SL")
    total_filtered = len(trades_filtered)
    precision = sl_filtered / total_filtered if total_filtered > 0 else 0.0

    filter_stats = {
        "setups_baseline":       len(oos_setups),
        "setups_allowed":        len(allowed_setups),
        "setups_filtered_pct":   round(
            (1 - len(allowed_setups) / len(oos_setups)) * 100, 1
        ) if oos_setups else 0.0,
        # alias used by grid_search.py and smoke test
        "trades_filtered_pct":   round(
            (1 - len(allowed_setups) / len(oos_setups)) * 100, 1
        ) if oos_setups else 0.0,
        "trades_baseline":       len(trades_baseline),
        "trades_allowed":        len(trades_allowed),
        "tp_filtered":           tp_filtered,
        "sl_filtered":           sl_filtered,
        "total_filtered":        total_filtered,
        "filter_precision":      round(precision, 4),
    }

    return RegimeBacktestResult(
        symbol=symbol,
        trades_baseline=trades_baseline,
        trades_allowed=trades_allowed,
        trades_filtered=trades_filtered,
        metrics_baseline=metrics_baseline,
        metrics_allowed=metrics_allowed,
        regime_series=regime_oos,
        filter_stats=filter_stats,
    )








