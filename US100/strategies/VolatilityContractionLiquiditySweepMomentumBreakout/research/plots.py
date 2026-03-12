"""
research/plots.py
=================
Heatmap and visualisation helpers for VCLSMB grid search results.

All figures are saved to disk (headless Agg backend — no display required).

Public API
----------
generate_heatmaps(df, output_dir)
    For every pair of grid parameters, produce a 2D heatmap coloured by
    OOS composite score (average over the other dimensions).

    Saves PNG files to output_dir/plots/.
    Returns a list of Path objects for the generated files.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")          # headless — must be before importing pyplot
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

# ── Parameters shown in heatmaps (must be columns in the grid results df) ────
HEATMAP_PARAMS = [
    "sweep_atr_mult",
    "momentum_atr_mult",
    "momentum_body_ratio",
    "compression_lookback",
    "liquidity_level_atr_mult",          # only present in liq-filter runs
    "volatility_percentile_threshold",   # only present in vol-filter runs
]

_SCORE_COL = "oos_score"
_SCORE_LABEL = "OOS Composite Score"


def _pivot_mean(df: pd.DataFrame, x_param: str, y_param: str) -> pd.DataFrame:
    """
    Average the score over all other dimensions to get a 2D pivot table.

    Rows = y_param values (descending), Columns = x_param values (ascending).
    """
    pivot = (
        df.groupby([y_param, x_param])[_SCORE_COL]
        .mean()
        .unstack(x_param)
    )
    return pivot.sort_index(ascending=False)   # largest y at top → natural heatmap layout


def _heatmap_one(
    pivot: pd.DataFrame,
    x_label: str,
    y_label: str,
    title: str,
    out_path: Path,
) -> None:
    """Render a single heatmap and save to *out_path*."""
    nrows, ncols = pivot.shape

    # Determine colour limits — centre cmap at 0 so negatives are red, positives blue
    vals = pivot.values[~np.isnan(pivot.values)]
    if len(vals) == 0:
        return
    vmin = min(vals.min(), -0.01)
    vmax = max(vals.max(),  0.01)
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(max(5, ncols + 2), max(4, nrows + 1)))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", norm=norm)

    ax.set_xticks(range(ncols))
    ax.set_xticklabels([f"{v:.2f}" for v in pivot.columns], fontsize=9)
    ax.set_yticks(range(nrows))
    ax.set_yticklabels([f"{v:.2f}" for v in pivot.index], fontsize=9)
    ax.set_xlabel(x_label, fontsize=10)
    ax.set_ylabel(y_label, fontsize=10)
    ax.set_title(title, fontsize=11, pad=10)

    # Annotate each cell with its score (or "—" for NaN)
    for r in range(nrows):
        for c in range(ncols):
            val = pivot.values[r, c]
            txt = f"{val:+.2f}" if not np.isnan(val) else "—"
            color = "black"
            ax.text(c, r, txt, ha="center", va="center", fontsize=8.5, color=color)

    cbar = fig.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label(_SCORE_LABEL, fontsize=9)

    plt.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def generate_heatmaps(
    df: pd.DataFrame,
    output_dir: Path,
    score_col: str = _SCORE_COL,
    params: Optional[List[str]] = None,
) -> List[Path]:
    """
    Generate one heatmap PNG per parameter pair.

    Parameters
    ----------
    df         : full grid results DataFrame with *score_col* already computed
    output_dir : strategy research base directory; plots go into output_dir/plots/
    score_col  : column containing the composite score
    params     : list of parameter column names; defaults to HEATMAP_PARAMS

    Returns
    -------
    List of Path objects for the saved PNG files.
    """
    if score_col not in df.columns:
        raise ValueError(
            f"Column '{score_col}' not found in dataframe. "
            "Run ranking.score_dataframe() first."
        )

    if params is None:
        params = [p for p in HEATMAP_PARAMS if p in df.columns]

    if len(params) < 2:
        return []

    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # Only use rows with a valid score
    df_valid = df[df[score_col].notna()].copy()
    df_valid = df_valid.rename(columns={score_col: _SCORE_COL})

    saved: List[Path] = []
    import itertools
    for x_param, y_param in itertools.combinations(params, 2):
        if x_param not in df_valid.columns or y_param not in df_valid.columns:
            continue

        try:
            pivot = _pivot_mean(df_valid, x_param, y_param)
        except Exception:
            continue

        x_label = x_param.replace("_", " ")
        y_label = y_param.replace("_", " ")
        title   = f"Avg OOS Score  |  {x_label} vs {y_label}"
        fname   = f"heatmap_{x_param}_vs_{y_param}.png"
        out_path = plots_dir / fname

        _heatmap_one(pivot, x_label, y_label, title, out_path)
        saved.append(out_path)
        print(f"  Saved heatmap: {out_path.name}")

    return saved


def score_distribution(
    df: pd.DataFrame,
    output_dir: Path,
    score_col: str = _SCORE_COL,
) -> Optional[Path]:
    """
    Bar chart of all OOS composite scores, sorted descending.
    """
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    df_s = df[df[score_col].notna()].copy()
    if df_s.empty:
        return None

    df_s = df_s.sort_values(score_col, ascending=False).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(12, 4))
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in df_s[score_col]]
    ax.bar(df_s.index + 1, df_s[score_col], color=colors, edgecolor="white", linewidth=0.3)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Rank", fontsize=10)
    ax.set_ylabel(_SCORE_LABEL, fontsize=10)
    ax.set_title("OOS Composite Score Distribution (all parameter combinations)", fontsize=11)
    ax.set_xlim(0, len(df_s) + 1)
    plt.tight_layout()

    out_path = plots_dir / "score_distribution.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved distribution chart: {out_path.name}")
    return out_path


def expectancy_scatter(
    df: pd.DataFrame,
    output_dir: Path,
) -> Optional[Path]:
    """
    Scatter: IS E(R) vs OOS E(R) for all parameter combos.
    Points above the y=x diagonal indicate OOS degradation (expected).
    """
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    needed = ["is_expectancy_R", "oos_expectancy_R"]
    if not all(c in df.columns for c in needed):
        return None

    df_s = df.dropna(subset=needed).copy()
    if df_s.empty:
        return None

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(df_s["is_expectancy_R"], df_s["oos_expectancy_R"],
               alpha=0.6, edgecolors="grey", linewidths=0.5, s=50)

    # Diagonal reference (perfect IS=OOS)
    lo = min(df_s["is_expectancy_R"].min(), df_s["oos_expectancy_R"].min()) - 0.05
    hi = max(df_s["is_expectancy_R"].max(), df_s["oos_expectancy_R"].max()) + 0.05
    ax.plot([lo, hi], [lo, hi], "k--", linewidth=0.8, label="IS = OOS")
    ax.axhline(0, color="#d62728", linewidth=0.7, linestyle=":")
    ax.axvline(0, color="#d62728", linewidth=0.7, linestyle=":")

    ax.set_xlabel("IS Expectancy R (2021-2022)", fontsize=10)
    ax.set_ylabel("OOS Expectancy R (2023-2025)", fontsize=10)
    ax.set_title("IS vs OOS Expectancy — all parameter combinations", fontsize=11)
    ax.legend(fontsize=9)
    plt.tight_layout()

    out_path = plots_dir / "is_vs_oos_expectancy.png"
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved IS/OOS scatter: {out_path.name}")
    return out_path
