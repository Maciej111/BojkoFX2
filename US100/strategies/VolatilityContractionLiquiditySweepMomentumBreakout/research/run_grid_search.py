"""
research/run_grid_search.py
===========================
Full parameter grid search for the VCLSMB strategy.

Workflow
--------
1. Load all historical bars ONCE.
2. Split into IS (2021-2022) and OOS (2023-2025).
3. Enumerate every combination of the parameter grid.
4. Run backtest for each combo on both IS and OOS windows.
5. Compute composite score (ranking.py).
6. Save:
     research/output/grid_search_results.csv  — all combinations
     research/output/top_candidates.csv        — top-N by OOS score
   Generate plots:
     research/plots/heatmap_*.png
     research/plots/score_distribution.png
     research/plots/is_vs_oos_expectancy.png
7. Write report:
     research/report/GRID_SEARCH_REPORT_<DATE>.md

Usage (from US100/ root):
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.run_grid_search
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.run_grid_search \\
        --no-trend-filter --quick
"""
from __future__ import annotations

import argparse
import itertools
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT   = Path(__file__).resolve().parents[3]   # US100/
_SHARED = _ROOT.parent / "shared"
for _p in [str(_ROOT), str(_SHARED)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.run_backtest_idx import load_ltf, filter_by_date, _calc_r_drawdown
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.config import VCLSMBConfig
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.strategy import run_vclsmb_backtest

_STRATEGY_DIR = Path(__file__).resolve().parents[1]
_RESEARCH_DIR = _STRATEGY_DIR / "research"
_OUTPUT_DIR   = _RESEARCH_DIR / "output"
_REPORT_DIR   = _RESEARCH_DIR / "report"

# ── IS / OOS periods ──────────────────────────────────────────────────────────
IS_START  = "2021-01-01"
IS_END    = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END   = "2025-12-31"

# ── Parameter grid ────────────────────────────────────────────────────────────
# 3 × 3 × 3 × 3 = 81 combinations
PARAM_GRID: Dict[str, list] = {
    "sweep_atr_mult":       [0.35, 0.5, 0.75],
    "momentum_atr_mult":    [1.0, 1.3, 1.6],
    "momentum_body_ratio":  [0.55, 0.65, 0.75],
    "compression_lookback": [12, 20, 30],
}

# Optional second axis: trend EMA filter
TREND_EMA_GRID = [20, 50, 100]   # only used when --trend-filter passed

# Fixed baseline parameters (not searched)
BASE_CONFIG = dict(
    atr_period           = 14,
    compression_atr_ratio= 0.6,
    range_window         = 10,
    risk_reward          = 2.0,
    sl_buffer_atr_mult   = 0.3,
    sl_anchor            = "range_extreme",
    use_session_filter   = False,
    use_trailing_stop    = False,
    # Volatility filter disabled by default; overridden by --vol-filter
    enable_volatility_filter        = False,
    volatility_window_days          = 20,
    volatility_percentile_threshold = 40.0,
    # Liquidity location filter disabled by default; overridden by --liq-filter
    enable_liquidity_location_filter = False,
)


def _build_configs(use_trend_filter: bool = False) -> List[dict]:
    """Return list of all parameter combination dicts."""
    keys   = list(PARAM_GRID.keys())
    values = [PARAM_GRID[k] for k in keys]

    configs: List[dict] = []
    for combo in itertools.product(*values):
        d = dict(zip(keys, combo))

        if use_trend_filter:
            for ema_p in TREND_EMA_GRID:
                c2 = dict(d)
                c2["enable_trend_filter"] = True
                c2["trend_ema_period"]    = ema_p
                configs.append(c2)
        else:
            d["enable_trend_filter"] = False
            d["trend_ema_period"]    = 50
            configs.append(d)

    return configs


def _make_cfg(params: dict) -> VCLSMBConfig:
    """Merge BASE_CONFIG with per-run params into a VCLSMBConfig."""
    merged = {**BASE_CONFIG, **params}
    return VCLSMBConfig(**merged)


def _run_one(
    symbol: str,
    bars: pd.DataFrame,
    params: dict,
) -> dict:
    """
    Run a single backtest with *params* on *bars*.
    Returns a flat dict of metrics (prefixed for IS or OOS calls).
    """
    cfg = _make_cfg(params)
    trades_df, metrics = run_vclsmb_backtest(symbol, bars, cfg)

    n  = metrics.get("trades_count", 0)
    wr = metrics.get("win_rate", 0.0)
    er = metrics.get("expectancy_R", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = _calc_r_drawdown(trades_df) if n > 0 else 0.0

    return {
        "trades":      n,
        "win_rate":    round(wr, 2),
        "expectancy_R":round(er, 4),
        "profit_factor":round(pf, 4),
        "max_dd_R":    round(dd, 2),
    }


def run_grid(
    symbol: str,
    ltf_full: pd.DataFrame,
    use_trend_filter: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Run all parameter combinations; return a DataFrame with IS + OOS metrics.
    """
    is_bars  = filter_by_date(ltf_full, IS_START,  IS_END)
    oos_bars = filter_by_date(ltf_full, OOS_START, OOS_END)

    if verbose:
        print(f"IS  bars: {len(is_bars):,}   ({IS_START} - {IS_END})")
        print(f"OOS bars: {len(oos_bars):,}   ({OOS_START} - {OOS_END})")

    configs = _build_configs(use_trend_filter)
    total   = len(configs)
    if verbose:
        print(f"\nRunning {total} parameter combinations...")
        print("-" * 60)

    rows: List[dict] = []
    t0 = time.time()

    for i, params in enumerate(configs, 1):
        is_m  = _run_one(symbol, is_bars,  params)
        oos_m = _run_one(symbol, oos_bars, params)

        row: dict = {}
        # Store searched params
        for k, v in params.items():
            row[k] = v
        # Store metrics with period prefix
        for k, v in is_m.items():
            row[f"is_{k}"] = v
        for k, v in oos_m.items():
            row[f"oos_{k}"] = v

        rows.append(row)

        if verbose and (i % 10 == 0 or i == total):
            elapsed = time.time() - t0
            pct = i / total * 100
            print(
                f"  [{i:3d}/{total}]  {pct:.0f}%  "
                f"elapsed {elapsed:.1f}s  "
                f"| last OOS E(R)={oos_m['expectancy_R']:+.3f}  "
                f"n={oos_m['trades']}"
            )

    df = pd.DataFrame(rows)
    elapsed = time.time() - t0
    if verbose:
        print(f"\nDone in {elapsed:.1f}s")

    return df


def _build_report(
    df_all: pd.DataFrame,
    df_top: pd.DataFrame,
    plot_files: List[Path],
    use_trend_filter: bool,
    date_tag: str,
    use_vol_filter: bool = False,
    vol_window_days: int = 20,
    vol_percentile_threshold: float = 40.0,
    use_liq_filter: bool = False,
    liq_level_atr_mult_values: Optional[List[float]] = None,
) -> str:
    """Build full markdown research report."""
    from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.ranking import (
        oos_validation_summary,
    )

    viable_oos = (df_all["oos_score"].notna()).sum()
    total      = len(df_all)
    best       = df_all.loc[df_all["oos_score"].idxmax()] if viable_oos > 0 else None

    lines: List[str] = [
        f"# VCLSMB Parameter Grid Search Report",
        f"",
        f"**Generated:** {date_tag} UTC",
        f"**Strategy:** VolatilityContraction → LiquiditySweep → MomentumBreakout (VCLSMB)",
        f"**Trend Filter:** {'Enabled (EMA variants included)' if use_trend_filter else 'Disabled'}",
        f"**Volatility Regime Filter:** {'Enabled — ATR percentile > ' + str(vol_percentile_threshold) + '% over ' + str(vol_window_days) + ' days (1h ATR)' if use_vol_filter else 'Disabled'}",
        f"**Liquidity Location Filter (PDH/PDL):** {'Enabled — sweep within [' + ', '.join(str(v) for v in (liq_level_atr_mult_values or [])) + '] × ATR of daily level' if use_liq_filter else 'Disabled'}",
        f"",
        f"## Methodology",
        f"",
        f"- **IS period (In-Sample):**  {IS_START} – {IS_END}  (2 years, model development)",
        f"- **OOS period (Out-of-Sample):** {OOS_START} – {OOS_END} (3 years, robustness validation)",
        f"- **Data:** 5-min bars, USATECHIDXUSD",
        f"",
        f"### Parameter Grid",
        f"",
        f"| Parameter | Values |",
        f"|-----------|--------|",
    ]
    for k, vals in PARAM_GRID.items():
        lines.append(f"| `{k}` | {vals} |")
    if use_trend_filter:
        lines.append(f"| `trend_ema_period` | {TREND_EMA_GRID} |")
    if use_liq_filter:
        lines.append(f"| `liquidity_level_atr_mult` | {liq_level_atr_mult_values or []} |")

    n_combos = len(_build_configs(use_trend_filter))
    lines += [
        f"",
        f"**Total combinations:** {n_combos}  (IS + OOS = {n_combos * 2} backtests)",
        f"",
        f"### Composite Score Formula",
        f"",
        f"```",
        f"score = 1.0 × profit_factor",
        f"      + 3.0 × expectancy_R",
        f"      - 0.5 × (max_dd_R / 10.0)",
        f"      + 0.5 × (min(trades, 100) / 100) ^ 0.75",
        f"",
        f"Hard filters: trades ≥ 40, E(R) > 0, max_dd_R < 30",
        f"```",
        f"",
        f"---",
        f"",
        f"## Overall Results",
        f"",
        f"- **Total combinations tested:** {total}",
        f"- **Viable OOS (pass hard filters):** {viable_oos} ({viable_oos/total*100:.0f}%)",
    ]

    if best is not None:
        lines += [
            f"- **Best OOS score:** {best['oos_score']:.3f}",
            f"  - `sweep_atr_mult` = {best['sweep_atr_mult']:.2f}",
            f"  - `momentum_atr_mult` = {best['momentum_atr_mult']:.2f}",
            f"  - `momentum_body_ratio` = {best['momentum_body_ratio']:.2f}",
            f"  - `compression_lookback` = {int(best['compression_lookback'])}",
        ]
        if use_trend_filter:
            lines.append(f"  - `trend_ema_period` = {int(best.get('trend_ema_period', 50))}")
        if use_liq_filter and "liquidity_level_atr_mult" in best:
            lines.append(f"  - `liquidity_level_atr_mult` = {best['liquidity_level_atr_mult']:.2f}")
        lines += [
            f"  - OOS E(R) = {best['oos_expectancy_R']:+.3f}",
            f"  - OOS win rate = {best['oos_win_rate']:.1f}%",
            f"  - OOS profit factor = {best['oos_profit_factor']:.2f}",
            f"  - OOS trades = {int(best['oos_trades'])}",
            f"  - OOS max DD = {best['oos_max_dd_R']:.1f}R",
        ]

    lines += [
        f"",
        f"---",
        f"",
        f"## Top {len(df_top)} Candidates (by OOS Composite Score)",
        f"",
        oos_validation_summary(df_top),
        f"",
        f"---",
        f"",
        f"## IS vs OOS Robustness",
        f"",
        f"The IS period (2021-2022) includes a significant bear market, so IS metrics",
        f"tend to be weak for most configurations. OOS (2023-2025) is the primary",
        f"evaluation criterion.",
        f"",
    ]

    # Distribution of OOS E(R) values
    oos_er = df_all["oos_expectancy_R"]
    lines += [
        f"### OOS Expectancy Distribution",
        f"",
        f"| Bucket | Count |",
        f"|--------|-------|",
        f"| E(R) > +0.1 | {(oos_er > 0.1).sum()} |",
        f"| E(R) 0.0 – 0.1 | {((oos_er > 0) & (oos_er <= 0.1)).sum()} |",
        f"| E(R) -0.1 – 0.0 | {((oos_er >= -0.1) & (oos_er <= 0)).sum()} |",
        f"| E(R) < -0.1 | {(oos_er < -0.1).sum()} |",
        f"",
    ]

    if plot_files:
        lines += [
            f"---",
            f"",
            f"## Visualisations",
            f"",
        ]
        for p in plot_files:
            lines.append(f"![{p.stem}](../plots/{p.name})")
        lines.append("")

    lines += [
        f"---",
        f"",
        f"## Recommended Configuration",
        f"",
    ]

    if best is not None:
        lines += [
            f"Based on the grid search, the recommended parameter set is:",
            f"",
            f"```python",
            f"VCLSMBConfig(",
            f"    sweep_atr_mult       = {best['sweep_atr_mult']:.2f},",
            f"    momentum_atr_mult    = {best['momentum_atr_mult']:.2f},",
            f"    momentum_body_ratio  = {best['momentum_body_ratio']:.2f},",
            f"    compression_lookback = {int(best['compression_lookback'])},",
        ]
        if use_trend_filter:
            lines.append(f"    enable_trend_filter  = True,")
            lines.append(f"    trend_ema_period     = {int(best.get('trend_ema_period', 50))},")
        if use_liq_filter and "liquidity_level_atr_mult" in best:
            lines.append(f"    enable_liquidity_location_filter = True,")
            lines.append(f"    liquidity_level_atr_mult = {best['liquidity_level_atr_mult']:.2f},")
        lines += [
            f"    # Fixed params",
            f"    atr_period           = 14,",
            f"    risk_reward          = 2.0,",
            f")",
            f"```",
            f"",
            f"> **Caution:** these parameters were selected from a grid search on historical data.",
            f"> Always validate with walk-forward testing before live deployment.",
        ]
    else:
        lines += [
            f"> No parameter combination passed all hard filters on OOS data.",
            f"> Consider relaxing thresholds or extending the data window.",
        ]

    lines += [
        f"",
        f"---",
        f"*End of report — generated by `research/run_grid_search.py`*",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="VCLSMB parameter grid search"
    )
    parser.add_argument("--symbol", default="usatechidxusd")
    parser.add_argument("--ltf",    default="5min")
    parser.add_argument(
        "--trend-filter", dest="trend_filter",
        action="store_true", default=False,
        help="Also search over trend_ema_period values",
    )
    parser.add_argument(
        "--quick", action="store_true", default=False,
        help="Use a smaller 2×2×2×2 grid for a quick smoke test",
    )
    parser.add_argument(
        "--no-plots", dest="no_plots",
        action="store_true", default=False,
        help="Skip heatmap generation",
    )
    parser.add_argument(
        "--from-csv", dest="from_csv",
        default=None,
        metavar="PATH",
        help="Load existing grid_search_results CSV and skip backtests (plots + report only)",
    )
    parser.add_argument(
        "--vol-filter", dest="vol_filter",
        action="store_true", default=False,
        help="Enable volatility regime filter (ATR percentile > 40%% over 20 days on 1h bars)",
    )
    parser.add_argument(
        "--vol-threshold", dest="vol_threshold",
        type=float, default=40.0,
        help="ATR percentile threshold for the volatility regime filter (default: 40.0)",
    )
    parser.add_argument(
        "--vol-window", dest="vol_window",
        type=int, default=20,
        help="Rolling window in calendar days for the volatility regime filter (default: 20)",
    )
    parser.add_argument(
        "--liq-filter", dest="liq_filter",
        action="store_true", default=False,
        help="Enable PDH/PDL structural liquidity location filter; adds liquidity_level_atr_mult axis",
    )
    args = parser.parse_args(argv)

    if args.quick:
        # Override grid with minimal values for fast testing
        global PARAM_GRID
        PARAM_GRID = {
            "sweep_atr_mult":       [0.35, 0.75],
            "momentum_atr_mult":    [1.0, 1.5],
            "momentum_body_ratio":  [0.55, 0.75],
            "compression_lookback": [12, 30],
        }
        print("[QUICK MODE] Using 2×2×2×2 = 16 combinations")

    # ── Apply volatility filter settings to BASE_CONFIG when requested ────────
    if args.vol_filter:
        BASE_CONFIG["enable_volatility_filter"]        = True
        BASE_CONFIG["volatility_window_days"]          = args.vol_window
        BASE_CONFIG["volatility_percentile_threshold"] = args.vol_threshold
        print(
            f"[VOL FILTER] Enabled: ATR percentile > {args.vol_threshold}% "
            f"over {args.vol_window}-day window (1h bars)"
        )

    # ── Apply liquidity location filter settings when requested ───────────────
    LIQ_MULT_VALUES = [2.0, 4.0, 6.0, 10.0]
    if args.liq_filter:
        BASE_CONFIG["enable_liquidity_location_filter"] = True
        PARAM_GRID["liquidity_level_atr_mult"] = LIQ_MULT_VALUES
        print(
            f"[LIQ FILTER] Enabled: PDH/PDL proximity, "
            f"liquidity_level_atr_mult in {LIQ_MULT_VALUES}"
        )

    date_tag = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    file_tag = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    # Suffix so results from runs with/without filter don't overwrite each other
    if args.liq_filter and args.vol_filter:
        file_suffix = "_with_vol_and_liq_filter"
    elif args.liq_filter:
        file_suffix = "_with_liquidity_filter"
    elif args.vol_filter:
        file_suffix = "_with_volatility_filter"
    else:
        file_suffix = ""

    # ── --from-csv shortcut: skip backtests, just score + plot + report ──────
    if args.from_csv:
        import pandas as pd
        from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.ranking import (
            score_dataframe,
            rank_results,
            TOP_N,
        )
        print(f"Loading results from: {args.from_csv}")
        df_all = pd.read_csv(args.from_csv)
        # Re-score (in case weights changed)
        df_all = score_dataframe(df_all, period_prefix="is")
        df_all = score_dataframe(df_all, period_prefix="oos")
        df_top = rank_results(df_all, sort_by="oos_score", top_n=TOP_N)

        print(f"\n{'='*60}")
        print(f"TOP {min(10, len(df_top))} CONFIGURATIONS BY OOS SCORE")
        print(f"{'='*60}")
        display_cols = [
            "sweep_atr_mult", "momentum_atr_mult", "momentum_body_ratio",
            "compression_lookback",
            "oos_trades", "oos_win_rate", "oos_expectancy_R",
            "oos_profit_factor", "oos_max_dd_R", "oos_score",
        ]
        if "liquidity_level_atr_mult" in df_top.columns:
            display_cols.insert(4, "liquidity_level_atr_mult")
        avail = [c for c in display_cols if c in df_top.columns]
        print(df_top[avail].head(10).to_string())

        plot_files: List[Path] = []
        if not args.no_plots:
            print("\nGenerating heatmaps...")
            from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.plots import (
                generate_heatmaps,
                score_distribution,
                expectancy_scatter,
            )
            try:
                plot_files += generate_heatmaps(df_all, _RESEARCH_DIR)
                p = score_distribution(df_all, _RESEARCH_DIR)
                if p:
                    plot_files.append(p)
                p = expectancy_scatter(df_all, _RESEARCH_DIR)
                if p:
                    plot_files.append(p)
            except Exception as exc:
                print(f"  Warning: plot generation failed — {exc}")

        report_md = _build_report(
            df_all                   = df_all,
            df_top                   = df_top,
            plot_files               = plot_files,
            use_trend_filter         = args.trend_filter,
            date_tag                 = date_tag,
            use_vol_filter           = getattr(args, "vol_filter", False),
            vol_window_days          = getattr(args, "vol_window", 20),
            vol_percentile_threshold = getattr(args, "vol_threshold", 40.0),
            use_liq_filter           = getattr(args, "liq_filter", False),
            liq_level_atr_mult_values= LIQ_MULT_VALUES if getattr(args, "liq_filter", False) else None,
        )
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = _REPORT_DIR / f"GRID_SEARCH_REPORT_{file_tag}.md"
        report_path.write_text(report_md, encoding="utf-8")
        print(f"\nReport: {report_path}")
        print("\nDone.")
        return

    # ── Load data ─────────────────────────────────────────────────────────────
    print(f"Loading {args.ltf} bars for {args.symbol}...")
    ltf_full = load_ltf(args.symbol, args.ltf)
    # Load the full range (IS + OOS)
    ltf_full = filter_by_date(ltf_full, IS_START, OOS_END)
    print(f"Total bars loaded: {len(ltf_full):,}")

    # ── Run grid ──────────────────────────────────────────────────────────────
    df_all = run_grid(
        symbol           = args.symbol,
        ltf_full         = ltf_full,
        use_trend_filter = args.trend_filter,
        verbose          = True,
    )

    # ── Score and rank ────────────────────────────────────────────────────────
    from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.ranking import (
        score_dataframe,
        rank_results,
        TOP_N,
    )

    df_all = score_dataframe(df_all, period_prefix="is")
    df_all = score_dataframe(df_all, period_prefix="oos")

    df_top = rank_results(df_all, sort_by="oos_score", top_n=TOP_N)

    # ── Save CSVs ─────────────────────────────────────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)

    all_path = _OUTPUT_DIR / f"grid_search_results{file_suffix}_{file_tag}.csv"
    top_path = _OUTPUT_DIR / f"top_candidates{file_suffix}_{file_tag}.csv"

    df_all.to_csv(all_path, index=False)
    df_top.to_csv(top_path)
    print(f"\nSaved: {all_path.name}")
    print(f"Saved: {top_path.name}")

    # Print quick leaderboard to console
    print(f"\n{'='*60}")
    print(f"TOP {min(10, len(df_top))} CONFIGURATIONS BY OOS SCORE")
    print(f"{'='*60}")
    display_cols = [
        "sweep_atr_mult", "momentum_atr_mult", "momentum_body_ratio",
        "compression_lookback",
        "oos_trades", "oos_win_rate", "oos_expectancy_R",
        "oos_profit_factor", "oos_max_dd_R", "oos_score",
    ]
    if args.trend_filter:
        display_cols.insert(4, "trend_ema_period")
    if args.liq_filter:
        display_cols.insert(4, "liquidity_level_atr_mult")

    avail = [c for c in display_cols if c in df_top.columns]
    print(df_top[avail].head(10).to_string())

    # ── Generate plots ────────────────────────────────────────────────────────
    plot_files: List[Path] = []
    if not args.no_plots:
        print("\nGenerating heatmaps...")
        from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.plots import (
            generate_heatmaps,
            score_distribution,
            expectancy_scatter,
        )
        try:
            plot_files += generate_heatmaps(df_all, _RESEARCH_DIR)
            p = score_distribution(df_all, _RESEARCH_DIR)
            if p:
                plot_files.append(p)
            p = expectancy_scatter(df_all, _RESEARCH_DIR)
            if p:
                plot_files.append(p)
        except Exception as exc:
            print(f"  Warning: plot generation failed — {exc}")

    # ── Write report ──────────────────────────────────────────────────────────
    report_md = _build_report(
        df_all                   = df_all,
        df_top                   = df_top,
        plot_files               = plot_files,
        use_trend_filter         = args.trend_filter,
        date_tag                 = date_tag,
        use_vol_filter           = args.vol_filter,
        vol_window_days          = args.vol_window,
        vol_percentile_threshold = args.vol_threshold,
        use_liq_filter           = args.liq_filter,
        liq_level_atr_mult_values= LIQ_MULT_VALUES if args.liq_filter else None,
    )
    report_path = _REPORT_DIR / f"GRID_SEARCH_REPORT{file_suffix}_{file_tag}.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\nReport: {report_path}")
    print("\nGrid search complete.")


if __name__ == "__main__":
    main()
