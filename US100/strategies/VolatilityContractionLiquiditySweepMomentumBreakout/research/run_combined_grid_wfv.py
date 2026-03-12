"""
research/run_combined_grid_wfv.py
==================================
Combined volatility-regime + PDH/PDL liquidity-location filter.

Workflow
--------
1. Load all historical bars ONCE.
2. Run IS (2021-2022) / OOS (2023-2025) grid search with BOTH filters active.
3. Score + rank all combinations.
4. Walk-forward validation:
     TRAIN 2021      → TEST 2022
     TRAIN 2021-2022 → TEST 2023
     TRAIN 2021-2023 → TEST 2024
     TRAIN 2021-2024 → TEST 2025
   Per window: run grid on TRAIN, pick best params, evaluate on TEST.
5. Save:
     research/output/grid_search_combined_filters_<DATE>.csv
     research/output/top_candidates_combined_filters_<DATE>.csv
     research/output/walk_forward_results_<DATE>.csv
6. Generate heatmaps under research/plots/ with "combined_" prefix.
7. Write:
     research/report/combined_filter_walk_forward_report_<DATE>.md

Usage (from US100/ root):
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.run_combined_grid_wfv
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.run_combined_grid_wfv --quick
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.run_combined_grid_wfv --no-plots
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
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.ranking import (
    composite_score,
    score_dataframe,
    rank_results,
    oos_validation_summary,
    MIN_TRADES,
    TOP_N,
)

_STRATEGY_DIR = Path(__file__).resolve().parents[1]
_RESEARCH_DIR = _STRATEGY_DIR / "research"
_OUTPUT_DIR   = _RESEARCH_DIR / "output"
_REPORT_DIR   = _RESEARCH_DIR / "report"

# ── IS / OOS periods (global grid search) ────────────────────────────────────
IS_START  = "2021-01-01"
IS_END    = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END   = "2025-12-31"

# ── Walk-forward windows (expanding TRAIN, annual TEST) ───────────────────────
WFV_WINDOWS: List[Tuple[str, str, str, str]] = [
    # (train_start, train_end, test_start, test_end)
    ("2021-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2021-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
]

# ── Parameter grid — combined filter search ───────────────────────────────────
# 3 × 3 × 3 × 3 = 81 base combos
# × 4 liq_mult × 3 vol_pct = 81 × 12 = 972 total
# To keep runtime acceptable, we fix vol_window_days=20 and search the
# percentile threshold only; liq_mult is kept at 4 representative values.
PARAM_GRID: Dict[str, list] = {
    "sweep_atr_mult":               [0.5, 0.75, 1.0],
    "momentum_atr_mult":            [1.0, 1.2, 1.4],
    "momentum_body_ratio":          [0.55, 0.65, 0.75],
    "compression_lookback":         [8, 12, 20],
    "liquidity_level_atr_mult":     [4.0, 6.0, 8.0, 10.0],
    "volatility_percentile_threshold": [30.0, 40.0, 50.0],
}

# ── Fixed parameters (same across all combinations) ───────────────────────────
BASE_CONFIG = dict(
    atr_period                      = 14,
    compression_atr_ratio           = 0.6,
    range_window                    = 10,
    risk_reward                     = 2.0,
    sl_buffer_atr_mult              = 0.3,
    sl_anchor                       = "range_extreme",
    use_session_filter              = False,
    use_trailing_stop               = False,
    enable_trend_filter             = False,
    trend_ema_period                = 50,
    # Both filters ON for this research module
    enable_volatility_filter        = True,
    volatility_htf                  = "1h",
    volatility_atr_period           = 14,
    volatility_window_days          = 20,
    enable_liquidity_location_filter = True,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_configs() -> List[dict]:
    """Return list of all parameter combination dicts."""
    keys   = list(PARAM_GRID.keys())
    values = [PARAM_GRID[k] for k in keys]
    configs: List[dict] = []
    for combo in itertools.product(*values):
        d = dict(zip(keys, combo))
        configs.append(d)
    return configs


def _make_cfg(params: dict) -> VCLSMBConfig:
    """Merge BASE_CONFIG with per-run params into a VCLSMBConfig."""
    merged = {**BASE_CONFIG, **params}
    return VCLSMBConfig(**merged)


def _run_one(symbol: str, bars: pd.DataFrame, params: dict) -> dict:
    """Run a single backtest; return flat metrics dict."""
    cfg = _make_cfg(params)
    trades_df, metrics = run_vclsmb_backtest(symbol, bars, cfg)
    n  = metrics.get("trades_count", 0)
    wr = metrics.get("win_rate", 0.0)
    er = metrics.get("expectancy_R", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = _calc_r_drawdown(trades_df) if n > 0 else 0.0
    total_r = float(trades_df["R"].sum()) if n > 0 else 0.0
    return {
        "trades":       n,
        "win_rate":     round(wr, 2),
        "expectancy_R": round(er, 4),
        "profit_factor":round(pf, 4),
        "max_dd_R":     round(dd, 2),
        "total_R":      round(total_r, 2),
    }


def run_grid(
    symbol: str,
    ltf_full: pd.DataFrame,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    configs: Optional[List[dict]] = None,
    verbose: bool = True,
    period_label: str = "",
) -> pd.DataFrame:
    """
    Run train + test backtests for all configs; return scored DataFrame.

    The train period plays the IS role; test period plays the OOS role.
    """
    train_bars = filter_by_date(ltf_full, train_start, train_end)
    test_bars  = filter_by_date(ltf_full, test_start,  test_end)

    if configs is None:
        configs = _build_configs()
    total = len(configs)

    tag = f" [{period_label}]" if period_label else ""
    if verbose:
        print(f"TRAIN bars: {len(train_bars):,}   ({train_start} - {train_end})")
        print(f"TEST  bars: {len(test_bars):,}   ({test_start} - {test_end})")
        print(f"\nRunning {total} combinations{tag}...")
        print("-" * 60)

    rows: List[dict] = []
    t0 = time.time()

    for i, params in enumerate(configs, 1):
        train_m = _run_one(symbol, train_bars, params)
        test_m  = _run_one(symbol, test_bars,  params)

        row: dict = {}
        for k, v in params.items():
            row[k] = v
        for k, v in train_m.items():
            row[f"is_{k}"] = v
        for k, v in test_m.items():
            row[f"oos_{k}"] = v

        rows.append(row)

        if verbose and (i % 20 == 0 or i == total):
            elapsed = time.time() - t0
            pct = i / total * 100
            print(
                f"  [{i:4d}/{total}]  {pct:.0f}%  "
                f"elapsed {elapsed:.0f}s  "
                f"| last TEST E(R)={test_m['expectancy_R']:+.3f}  "
                f"n={test_m['trades']}"
            )

    df = pd.DataFrame(rows)
    elapsed = time.time() - t0
    if verbose:
        print(f"\nDone in {elapsed:.0f}s")

    # Score
    df = score_dataframe(df, period_prefix="is")
    df = score_dataframe(df, period_prefix="oos")
    return df


# ── Walk-forward validation ───────────────────────────────────────────────────

def run_walk_forward(
    symbol: str,
    ltf_full: pd.DataFrame,
    configs: List[dict],
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Expanding-window walk-forward validation.

    For each window:
      1. Run grid on TRAIN period.
      2. Select best config (by train score).
      3. Evaluate best config on TEST period.

    Returns a DataFrame with one row per WFV window.
    """
    wfv_rows: List[dict] = []

    for idx, (tr_s, tr_e, te_s, te_e) in enumerate(WFV_WINDOWS, 1):
        window_label = f"TRAIN {tr_s[:4]}–{tr_e[:4]} | TEST {te_s[:4]}"
        print(f"\n{'='*65}")
        print(f"  Walk-Forward Window {idx}/{len(WFV_WINDOWS)}:  {window_label}")
        print(f"{'='*65}")

        df_window = run_grid(
            symbol      = symbol,
            ltf_full    = ltf_full,
            train_start = tr_s,
            train_end   = tr_e,
            test_start  = te_s,
            test_end    = te_e,
            configs     = configs,
            verbose     = verbose,
            period_label = window_label,
        )

        # Pick best by TRAIN composite score
        viable = df_window[df_window["is_score"].notna()]
        if viable.empty:
            print("  ⚠ No viable config on TRAIN window — skipping.")
            wfv_rows.append({
                "window":       window_label,
                "train_start":  tr_s,
                "train_end":    tr_e,
                "test_start":   te_s,
                "test_end":     te_e,
                "best_sweep":   None,
                "best_mom_atr": None,
                "best_body":    None,
                "best_lb":      None,
                "best_liq":     None,
                "best_vol_pct": None,
                "train_trades": 0, "train_wr": 0, "train_er": 0,
                "train_pf":     0, "train_dd": 0, "train_score": float("nan"),
                "test_trades":  0, "test_wr":  0, "test_er":  0,
                "test_pf":      0, "test_dd":  0, "test_total_R": 0,
            })
            continue

        best = viable.loc[viable["is_score"].idxmax()]

        test_oos_er = best.get("oos_expectancy_R", float("nan"))
        test_oos_n  = int(best.get("oos_trades", 0))
        test_oos_pf = best.get("oos_profit_factor", float("nan"))
        test_oos_dd = best.get("oos_max_dd_R", float("nan"))
        test_oos_tr = best.get("oos_total_R", float("nan"))
        test_oos_wr = best.get("oos_win_rate", float("nan"))

        row = {
            "window":       window_label,
            "train_start":  tr_s,
            "train_end":    tr_e,
            "test_start":   te_s,
            "test_end":     te_e,
            "best_sweep":   best.get("sweep_atr_mult"),
            "best_mom_atr": best.get("momentum_atr_mult"),
            "best_body":    best.get("momentum_body_ratio"),
            "best_lb":      best.get("compression_lookback"),
            "best_liq":     best.get("liquidity_level_atr_mult"),
            "best_vol_pct": best.get("volatility_percentile_threshold"),
            "train_trades": int(best.get("is_trades", 0)),
            "train_wr":     best.get("is_win_rate", float("nan")),
            "train_er":     best.get("is_expectancy_R", float("nan")),
            "train_pf":     best.get("is_profit_factor", float("nan")),
            "train_dd":     best.get("is_max_dd_R", float("nan")),
            "train_score":  best.get("is_score", float("nan")),
            "test_trades":  test_oos_n,
            "test_wr":      test_oos_wr,
            "test_er":      test_oos_er,
            "test_pf":      test_oos_pf,
            "test_dd":      test_oos_dd,
            "test_total_R": test_oos_tr,
        }
        wfv_rows.append(row)

        print(
            f"\n  ✓ Best config:  sweep={best.get('sweep_atr_mult'):.2f}  "
            f"mom={best.get('momentum_atr_mult'):.2f}  "
            f"body={best.get('momentum_body_ratio'):.2f}  "
            f"lb={int(best.get('compression_lookback', 0))}  "
            f"liq={best.get('liquidity_level_atr_mult'):.0f}  "
            f"vol_pct={best.get('volatility_percentile_threshold'):.0f}"
        )
        print(
            f"  TRAIN: n={int(best.get('is_trades',0))}  "
            f"E(R)={best.get('is_expectancy_R',0):+.3f}  "
            f"PF={best.get('is_profit_factor',0):.2f}  "
            f"DD={best.get('is_max_dd_R',0):.1f}R"
        )
        print(
            f"  TEST : n={test_oos_n}  "
            f"E(R)={test_oos_er:+.3f}  "
            f"PF={test_oos_pf:.2f}  "
            f"DD={test_oos_dd:.1f}R  "
            f"total={test_oos_tr:+.1f}R"
        )

    return pd.DataFrame(wfv_rows)


# ── Heatmaps ──────────────────────────────────────────────────────────────────

def _generate_combined_heatmaps(
    df_all: pd.DataFrame,
    research_dir: Path,
    no_plots: bool,
) -> List[Path]:
    """Generate heatmaps using the shared plots utility with combined_ filename prefix."""
    if no_plots:
        return []

    from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.research.plots import (
        generate_heatmaps,
        score_distribution,
        expectancy_scatter,
    )

    # Override output filename prefix by saving to a subdir, then rename
    # (plots.py uses param names as filenames — add prefix via a wrapper)
    plots_dir = research_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plot_files: List[Path] = []
    try:
        # generate_heatmaps writes to research_dir/plots/heatmap_*.png
        pfiles = generate_heatmaps(df_all, research_dir)
        # Rename to add "combined_" prefix so they don't overwrite previous runs
        for p in pfiles:
            new_name = p.parent / f"combined_{p.name}"
            p.rename(new_name)
            plot_files.append(new_name)

        p = score_distribution(df_all, research_dir)
        if p:
            new_name = p.parent / f"combined_{p.name}"
            p.rename(new_name)
            plot_files.append(new_name)

        p = expectancy_scatter(df_all, research_dir)
        if p:
            new_name = p.parent / f"combined_{p.name}"
            p.rename(new_name)
            plot_files.append(new_name)

    except Exception as exc:
        print(f"  Warning: plot generation failed — {exc}")

    return plot_files


def _generate_wfv_chart(
    wfv_df: pd.DataFrame,
    research_dir: Path,
    no_plots: bool,
) -> Optional[Path]:
    """Bar chart of test E(R) per WFV window."""
    if no_plots or wfv_df.empty:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plots_dir = research_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)

        windows = [
            f"TEST {r['test_start'][:4]}" for _, r in wfv_df.iterrows()
        ]
        ers = [
            r["test_er"] if r["test_er"] is not None else 0
            for _, r in wfv_df.iterrows()
        ]

        colors = ["#2ca02c" if e > 0 else "#d62728" for e in ers]

        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.bar(windows, ers, color=colors, edgecolor="white", linewidth=0.5)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")

        for bar, er in zip(bars, ers):
            if er is not None:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    er + (0.005 if er >= 0 else -0.012),
                    f"{er:+.3f}",
                    ha="center", va="bottom" if er >= 0 else "top",
                    fontsize=9,
                )

        ax.set_ylabel("Test E(R)", fontsize=10)
        ax.set_title(
            "Walk-Forward Validation — Test E(R) per Window\n"
            "(Best TRAIN config evaluated on unseen TEST year)",
            fontsize=11,
        )
        plt.tight_layout()

        out_path = plots_dir / "combined_wfv_test_expectancy.png"
        fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved WFV chart: {out_path.name}")
        return out_path
    except Exception as exc:
        print(f"  Warning: WFV chart failed — {exc}")
        return None


# ── Report builder ────────────────────────────────────────────────────────────

def _build_report(
    df_all: pd.DataFrame,
    df_top: pd.DataFrame,
    wfv_df: pd.DataFrame,
    plot_files: List[Path],
    wfv_chart: Optional[Path],
    date_tag: str,
    file_tag: str,
) -> str:
    viable = df_all["oos_score"].notna().sum()
    total  = len(df_all)
    best   = df_all.loc[df_all["oos_score"].idxmax()] if viable > 0 else None

    combos_per_dim = "  ×  ".join(
        f"{len(v)} {k}" for k, v in PARAM_GRID.items()
    )
    n_combos = total

    lines: List[str] = [
        "# VCLSMB Combined Filter Grid Search + Walk-Forward Validation",
        "",
        f"**Generated:** {date_tag} UTC",
        "**Strategy:** VolatilityContraction → LiquiditySweep → MomentumBreakout (VCLSMB v2)",
        "**Active filters:** Volatility Regime Filter + PDH/PDL Liquidity Location Filter",
        "",
        "---",
        "",
        "## 1. Research Objective",
        "",
        "Evaluate VCLSMB with **both** structural filters simultaneously active:",
        "",
        "1. **Volatility Regime Filter** — prevents entries during low-ATR regimes by",
        "   requiring the current 1-hour ATR to exceed its rolling N-th percentile.",
        "2. **Structural Liquidity Location Filter (PDH/PDL)** — requires the compression",
        "   range boundary to be within a configurable ATR-multiple of the previous day's",
        "   high (bearish setups) or previous day's low (bullish setups).",
        "",
        "**Combined pipeline:**",
        "",
        "```",
        "Market Data",
        "↓ Feature Calculation (ATR, range, PDH/PDL, vol-regime flag)",
        "↓ Volatility Regime Gate   ← filter 1: skip bar if low-vol regime",
        "↓ Compression Detection",
        "↓ Liquidity Sweep Detection",
        "↓ PDH/PDL Proximity Gate   ← filter 2: skip entry if range not near daily extreme",
        "↓ Momentum Confirmation",
        "↓ Trade Execution",
        "```",
        "",
        "---",
        "",
        "## 2. Experimental Setup",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        "| Symbol | USATECHIDXUSD (US100 CFD) |",
        "| LTF | 5-minute bars |",
        "| IS window | 2021-01-01 – 2022-12-31 |",
        "| OOS window | 2023-01-01 – 2025-12-31 |",
        "| Vol filter HTF | 1h |",
        "| Vol filter window | 20 calendar days |",
        "| Risk-reward | 2:1 |",
        f"| Min trades (hard filter) | {MIN_TRADES} |",
        "",
        "---",
        "",
        "## 3. Parameter Grid",
        "",
        "| Parameter | Values | Notes |",
        "|-----------|--------|-------|",
    ]

    notes = {
        "sweep_atr_mult":               "wick extension threshold (ATR multiples)",
        "momentum_atr_mult":            "breakout bar body size (ATR multiples)",
        "momentum_body_ratio":          "body/range quality filter",
        "compression_lookback":         "bars to establish compression range",
        "liquidity_level_atr_mult":     "PDH/PDL proximity width (ATR multiples)",
        "volatility_percentile_threshold": "minimum ATR percentile to allow entries (%)",
    }
    for k, vals in PARAM_GRID.items():
        lines.append(f"| `{k}` | {vals} | {notes.get(k, '')} |")

    lines += [
        "",
        f"**Total combinations:** {n_combos}",
        f"**Dimensions:** {combos_per_dim}",
        "",
        "---",
        "",
        "## 4. IS / OOS Grid Search Results",
        "",
        f"- **Total combinations:** {total}",
        f"- **Viable OOS** (pass hard filters): **{viable}** ({viable/total*100:.0f}%)",
    ]

    if best is not None:
        lines += [
            f"- **Best OOS composite score:** {best['oos_score']:.3f}",
            "",
            "### Best Configuration",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
            f"| `sweep_atr_mult` | {best['sweep_atr_mult']:.2f} |",
            f"| `momentum_atr_mult` | {best['momentum_atr_mult']:.2f} |",
            f"| `momentum_body_ratio` | {best['momentum_body_ratio']:.2f} |",
            f"| `compression_lookback` | {int(best['compression_lookback'])} |",
            f"| `liquidity_level_atr_mult` | {best['liquidity_level_atr_mult']:.1f} |",
            f"| `volatility_percentile_threshold` | {best['volatility_percentile_threshold']:.0f}% |",
            "",
            "| Period | E(R) | Trades | Win Rate | PF | Max DD |",
            "|--------|------|--------|----------|----|--------|",
            f"| IS (2021-2022) | {best['is_expectancy_R']:+.3f} | {int(best['is_trades'])} | {best['is_win_rate']:.1f}% | {best['is_profit_factor']:.2f} | {best['is_max_dd_R']:.1f}R |",
            f"| OOS (2023-2025) | **{best['oos_expectancy_R']:+.3f}** | **{int(best['oos_trades'])}** | **{best['oos_win_rate']:.1f}%** | **{best['oos_profit_factor']:.2f}** | **{best['oos_max_dd_R']:.1f}R** |",
        ]

    lines += [
        "",
        "### Top Candidates (OOS)",
        "",
        oos_validation_summary(df_top),
        "",
        "---",
        "",
        "## 5. OOS E(R) Distribution",
        "",
    ]

    oos_er = df_all["oos_expectancy_R"]
    lines += [
        "| Bucket | Count |",
        "|--------|-------|",
        f"| E(R) > +0.3 | {(oos_er > 0.3).sum()} |",
        f"| E(R) +0.2 – +0.3 | {((oos_er >= 0.2) & (oos_er < 0.3)).sum()} |",
        f"| E(R) +0.1 – +0.2 | {((oos_er >= 0.1) & (oos_er < 0.2)).sum()} |",
        f"| E(R) 0.0 – +0.1 | {((oos_er >= 0) & (oos_er < 0.1)).sum()} |",
        f"| E(R) < 0 | {(oos_er < 0).sum()} |",
        "",
        "---",
        "",
        "## 6. Walk-Forward Validation",
        "",
        "**Procedure:** Expanding training window, one-year forward test per fold.",
        "Each fold selects the best-scoring parameter set on the TRAIN window,",
        "then evaluates it — unseen — on the TEST year.",
        "",
    ]

    if wfv_df.empty:
        lines.append("*Walk-forward results not available.*")
    else:
        lines += [
            "| Window | Best Config | Test n | Test WR | Test E(R) | Test PF | Test DD | Test ΣR |",
            "|--------|-------------|--------|---------|-----------|---------|---------|---------|",
        ]
        for _, r in wfv_df.iterrows():
            if r["test_trades"] is None or r["test_trades"] == 0:
                er_s = "—"
                pf_s = "—"
                dd_s = "—"
                tr_s = "—"
                wr_s = "—"
                n_s  = "0"
            else:
                er_s = f"{r['test_er']:+.3f}"
                pf_s = f"{r['test_pf']:.2f}"
                dd_s = f"{r['test_dd']:.1f}R"
                tr_s = f"{r['test_total_R']:+.1f}R"
                wr_s = f"{r['test_wr']:.1f}%"
                n_s  = str(int(r["test_trades"]))

            liq = r["best_liq"]
            vol = r["best_vol_pct"]
            cfg_s = (
                f"sw={r['best_sweep']:.2f} mom={r['best_mom_atr']:.2f} "
                f"body={r['best_body']:.2f} lb={int(r['best_lb']) if r['best_lb'] else '?'} "
                f"liq={int(liq) if liq else '?'} vol={int(vol) if vol else '?'}%"
            )
            lines.append(
                f"| {r['window']} | `{cfg_s}` | {n_s} | {wr_s} | {er_s} | {pf_s} | {dd_s} | {tr_s} |"
            )

        # Aggregate summary
        valid_rows = wfv_df[wfv_df["test_trades"].notna() & (wfv_df["test_trades"] > 0)]
        if not valid_rows.empty:
            avg_er = valid_rows["test_er"].mean()
            pos    = (valid_rows["test_er"] > 0).sum()
            lines += [
                "",
                f"**Walk-forward summary:**",
                f"- Profitable test windows: {pos}/{len(valid_rows)}",
                f"- Average test E(R): {avg_er:+.3f}",
            ]

    if wfv_chart:
        lines += [
            "",
            f"![WFV Test Expectancy](../plots/{wfv_chart.name})",
        ]

    lines += [
        "",
        "---",
        "",
        "## 7. Heatmaps",
        "",
        "Parameter sensitivity heatmaps (all axes averaged over other dimensions).",
        "",
    ]

    for p in plot_files:
        if "combined_heatmap" in p.name:
            lines.append(f"![{p.stem}](../plots/{p.name})")
    lines += [
        "",
        "---",
        "",
        "## 8. Parameter Stability Analysis",
        "",
    ]

    if best is not None and viable > 0:
        viable_df = df_all[df_all["oos_score"].notna()].copy()

        # Frequency of best values in top-15
        top15 = rank_results(df_all, sort_by="oos_score", top_n=15)

        def _mode(col: str) -> str:
            if col not in top15.columns:
                return "?"
            return str(top15[col].mode().iloc[0])

        lines += [
            "Most frequent values among the top-15 configurations (OOS):",
            "",
            "| Parameter | Most Common Value | Top-15 Frequency |",
            "|-----------|-------------------|-----------------|",
        ]
        for k in PARAM_GRID:
            if k not in top15.columns:
                continue
            mode_val = top15[k].mode().iloc[0]
            freq     = (top15[k] == mode_val).sum()
            lines.append(f"| `{k}` | {mode_val} | {freq}/15 |")

        lines += [
            "",
            "A high frequency (≥ 10/15) for a given parameter value indicates a",
            "**stable plateau** — the strategy is insensitive to other parameters",
            "when that value is held fixed.  Low frequency indicates sensitivity.",
        ]

    lines += [
        "",
        "---",
        "",
        "## 9. Comparison with Previous Experiments",
        "",
        "| Variant | OOS E(R) | PF | Trades | Max DD | Notes |",
        "|---------|----------|----|--------|--------|-------|",
        "| No filter (baseline) | +0.183 | 1.30 | 71 | 7.0R | sweep=0.75, mom=1.3, body=0.55, lb=12 |",
        "| Volatility filter only | +0.286 | 1.50 | 63 | 6.0R | sweep=0.35, mom=1.3, body=0.55, lb=12 |",
        "| PDH/PDL filter only | +0.364 | 1.67 | 22 | 4.0R | sweep=0.75, mom=1.3, body=0.75, lb=20 |",
    ]

    if best is not None:
        lines.append(
            f"| **Both filters (this run)** | **{best['oos_expectancy_R']:+.3f}** "
            f"| **{best['oos_profit_factor']:.2f}** "
            f"| {int(best['oos_trades'])} "
            f"| {best['oos_max_dd_R']:.1f}R "
            f"| sweep={best['sweep_atr_mult']:.2f}, mom={best['momentum_atr_mult']:.2f}, "
            f"body={best['momentum_body_ratio']:.2f}, "
            f"lb={int(best['compression_lookback'])}, "
            f"liq={best['liquidity_level_atr_mult']:.0f}, "
            f"vol_pct={best['volatility_percentile_threshold']:.0f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 10. Recommended Configuration",
        "",
    ]

    if best is not None:
        lines += [
            "Based on the combined filter grid search (IS 2021-2022, OOS 2023-2025):",
            "",
            "```python",
            "VCLSMBConfig(",
            f"    sweep_atr_mult                    = {best['sweep_atr_mult']:.2f},",
            f"    momentum_atr_mult                 = {best['momentum_atr_mult']:.2f},",
            f"    momentum_body_ratio               = {best['momentum_body_ratio']:.2f},",
            f"    compression_lookback              = {int(best['compression_lookback'])},",
            "    enable_volatility_filter          = True,",
            f"    volatility_percentile_threshold   = {best['volatility_percentile_threshold']:.0f},",
            "    volatility_window_days            = 20,",
            "    enable_liquidity_location_filter  = True,",
            f"    liquidity_level_atr_mult          = {best['liquidity_level_atr_mult']:.1f},",
            "    # Fixed",
            "    atr_period                        = 14,",
            "    risk_reward                       = 2.0,",
            ")",
            "```",
            "",
            "> **Statistical note:** Always validate with a larger dataset or",
            "> live trading before deploying.  Walk-forward results provide stronger",
            "> evidence of generalization than a single IS/OOS split.",
        ]
    else:
        lines += [
            "> No configuration passed all hard filters on the OOS window.",
            "> Consider relaxing `MIN_TRADES` or extending the data range.",
        ]

    lines += [
        "",
        "---",
        "",
        "## 11. Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        f"| `research/output/grid_search_combined_filters_{file_tag}.csv` | All {total} combos |",
        f"| `research/output/top_candidates_combined_filters_{file_tag}.csv` | Top 15 by OOS score |",
        f"| `research/output/walk_forward_results_{file_tag}.csv` | WFV window results |",
        "| `research/plots/combined_heatmap_*.png` | Parameter sensitivity heatmaps |",
        "| `research/plots/combined_wfv_test_expectancy.png` | WFV test E(R) chart |",
        "",
        "---",
        "",
        "*End of report — generated by `research/run_combined_grid_wfv.py`*",
    ]

    return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="VCLSMB combined filter grid search + walk-forward validation"
    )
    parser.add_argument("--symbol", default="usatechidxusd")
    parser.add_argument("--ltf",    default="5min")
    parser.add_argument(
        "--quick", action="store_true", default=False,
        help="Use a minimal 2×2×2×2×2×2 grid for a quick smoke test",
    )
    parser.add_argument(
        "--no-plots", dest="no_plots",
        action="store_true", default=False,
        help="Skip heatmap and chart generation",
    )
    parser.add_argument(
        "--skip-wfv", dest="skip_wfv",
        action="store_true", default=False,
        help="Skip walk-forward validation (run global IS/OOS grid only)",
    )
    args = parser.parse_args(argv)

    if args.quick:
        global PARAM_GRID
        PARAM_GRID = {
            "sweep_atr_mult":               [0.5, 1.0],
            "momentum_atr_mult":            [1.0, 1.4],
            "momentum_body_ratio":          [0.55, 0.75],
            "compression_lookback":         [8, 20],
            "liquidity_level_atr_mult":     [4.0, 10.0],
            "volatility_percentile_threshold": [30.0, 50.0],
        }
        print("[QUICK MODE] 2×2×2×2×2×2 = 64 combinations")

    date_tag = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    file_tag = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    print(f"Loading {args.ltf} bars for {args.symbol}...")
    ltf_full = load_ltf(args.symbol, args.ltf)
    ltf_full = filter_by_date(ltf_full, "2021-01-01", "2025-12-31")
    print(f"Total bars: {len(ltf_full):,}")

    configs = _build_configs()
    print(f"\nTotal grid combinations: {len(configs)}")

    # ── IS / OOS grid search ─────────────────────────────────────────────────
    print("\n" + "="*65)
    print("  GLOBAL IS / OOS GRID SEARCH")
    print("="*65)

    df_all = run_grid(
        symbol      = args.symbol,
        ltf_full    = ltf_full,
        train_start = IS_START,
        train_end   = IS_END,
        test_start  = OOS_START,
        test_end    = OOS_END,
        configs     = configs,
        verbose     = True,
        period_label = "IS 2021-2022 | OOS 2023-2025",
    )

    df_top = rank_results(df_all, sort_by="oos_score", top_n=TOP_N)

    all_path = _OUTPUT_DIR / f"grid_search_combined_filters_{file_tag}.csv"
    top_path = _OUTPUT_DIR / f"top_candidates_combined_filters_{file_tag}.csv"
    df_all.to_csv(all_path, index=False)
    df_top.to_csv(top_path)
    print(f"\nSaved: {all_path.name}")
    print(f"Saved: {top_path.name}")

    # Console leaderboard
    print(f"\n{'='*65}")
    print("TOP 10 CONFIGURATIONS BY OOS SCORE")
    print("="*65)
    display_cols = [
        "sweep_atr_mult", "momentum_atr_mult", "momentum_body_ratio",
        "compression_lookback", "liquidity_level_atr_mult",
        "volatility_percentile_threshold",
        "oos_trades", "oos_win_rate", "oos_expectancy_R",
        "oos_profit_factor", "oos_max_dd_R", "oos_score",
    ]
    avail = [c for c in display_cols if c in df_top.columns]
    print(df_top[avail].head(10).to_string())

    # ── Walk-forward validation ───────────────────────────────────────────────
    wfv_df = pd.DataFrame()
    if not args.skip_wfv:
        print("\n" + "="*65)
        print("  WALK-FORWARD VALIDATION  (4 expanding windows)")
        print("="*65)

        wfv_df = run_walk_forward(
            symbol   = args.symbol,
            ltf_full = ltf_full,
            configs  = configs,
            verbose  = True,
        )

        wfv_path = _OUTPUT_DIR / f"walk_forward_results_{file_tag}.csv"
        wfv_df.to_csv(wfv_path, index=False)
        print(f"\nSaved: {wfv_path.name}")

    # ── Plots ─────────────────────────────────────────────────────────────────
    print("\nGenerating plots...")
    plot_files = _generate_combined_heatmaps(df_all, _RESEARCH_DIR, args.no_plots)
    wfv_chart  = _generate_wfv_chart(wfv_df, _RESEARCH_DIR, args.no_plots)

    # ── Report ────────────────────────────────────────────────────────────────
    print("\nWriting report...")
    report_md = _build_report(
        df_all     = df_all,
        df_top     = df_top,
        wfv_df     = wfv_df,
        plot_files = plot_files,
        wfv_chart  = wfv_chart,
        date_tag   = date_tag,
        file_tag   = file_tag,
    )
    report_path = _REPORT_DIR / f"combined_filter_walk_forward_report_{file_tag}.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Report: {report_path}")
    print("\nCombined filter research complete.")


if __name__ == "__main__":
    main()
