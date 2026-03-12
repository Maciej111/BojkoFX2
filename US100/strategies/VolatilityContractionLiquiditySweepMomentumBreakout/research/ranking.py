"""
research/ranking.py
===================
Composite scoring and ranking logic for VCLSMB grid search results.

Composite score formula (higher is better):
  score = w_pf * profit_factor
        + w_er * expectancy_R
        - w_dd * (max_dd_R / 10.0)
        + w_n  * min(trades_count, 100) / 100.0

Hard filters applied before scoring:
  - trades_count >= MIN_TRADES
  - expectancy_R  > 0
  - max_dd_R      < MAX_DD_R
"""
from __future__ import annotations

import pandas as pd

# ── Scoring weights ───────────────────────────────────────────────────────────
W_PF: float = 1.0    # profit factor contribution
W_ER: float = 3.0    # expectancy R is the primary signal quality measure
W_DD: float = 0.5    # penalise large drawdowns
W_N:  float = 0.5    # reward having enough trades (raised from 0.3 — penalises
                     # low trade counts more strongly to combat overfitting)

# ── Hard filter thresholds ────────────────────────────────────────────────────
MIN_TRADES: int   = 40    # minimum trades for statistical reliability
                          # (PDH/PDL filter significantly reduces trade count —
                          #  statistical caveat noted in LIQUIDITY_FILTER report)
MAX_DD_R:   float = 30.0  # drawdowns above this are unacceptable

# ── Top-N candidates to carry forward to OOS validation ──────────────────────
TOP_N: int = 15


def composite_score(
    profit_factor: float,
    expectancy_R: float,
    max_dd_R: float,
    trades_count: int,
) -> float:
    """
    Compute composite quality score for one backtest result.
    Returns ``float('nan')`` when hard filter constraints are violated.
    """
    if trades_count < MIN_TRADES:
        return float("nan")
    if expectancy_R <= 0:
        return float("nan")
    if max_dd_R >= MAX_DD_R:
        return float("nan")

    pf_safe  = min(profit_factor, 5.0)  # cap extreme PF (avoids tiny-loss artefacts)
    # Non-linear trade count score: penalises the 40-60 range more steeply
    # than a simple linear scaling would.  Still saturates at 100 trades.
    n_score  = (min(trades_count, 100) / 100.0) ** 0.75

    return (
        W_PF * pf_safe
        + W_ER * expectancy_R
        - W_DD * (max_dd_R / 10.0)
        + W_N  * n_score
    )


def score_dataframe(
    df: pd.DataFrame,
    period_prefix: str = "oos",
) -> pd.DataFrame:
    """
    Add a composite score column to *df* using columns from a given period.

    Expected columns (for prefix ``"oos"``):
        oos_trades, oos_win_rate, oos_expectancy_R, oos_profit_factor, oos_max_dd_R

    Adds:
        {prefix}_score   — composite score (nan if filters fail)
        {prefix}_viable  — bool, passed all hard filters
    """
    p = period_prefix
    score_col   = f"{p}_score"
    viable_col  = f"{p}_viable"

    df = df.copy()
    df[score_col] = df.apply(
        lambda r: composite_score(
            profit_factor = r.get(f"{p}_profit_factor", 0.0),
            expectancy_R  = r.get(f"{p}_expectancy_R",  -999),
            max_dd_R      = r.get(f"{p}_max_dd_R",       999),
            trades_count  = int(r.get(f"{p}_trades",       0)),
        ),
        axis=1,
    )
    df[viable_col] = df[score_col].notna()
    return df


def rank_results(
    df: pd.DataFrame,
    sort_by: str = "oos_score",
    top_n: int = TOP_N,
) -> pd.DataFrame:
    """
    Sort *df* by composite score (descending), return top *top_n* rows.

    Parameters
    ----------
    df      : full grid results DataFrame (must have score columns already)
    sort_by : column to sort by
    top_n   : how many rows to return
    """
    if sort_by not in df.columns:
        raise ValueError(f"Column '{sort_by}' not found in dataframe. Run score_dataframe() first.")

    ranked = (
        df[df[sort_by].notna()]
        .sort_values(sort_by, ascending=False)
        .reset_index(drop=True)
    )
    ranked.index += 1   # 1-based rank
    ranked.index.name = "rank"
    return ranked.head(top_n)


def oos_validation_summary(
    candidates: pd.DataFrame,
) -> str:
    """
    Return a markdown table summarising IS→OOS robustness for top candidates.
    """
    lines = [
        "| Rank | sweep | mom_atr | body | comp_lb | IS_E(R) | OOS_E(R) | IS_PF | OOS_PF | IS_n | OOS_n | OOS_DD | OOS_score |",
        "|------|-------|---------|------|---------|---------|----------|-------|--------|------|-------|--------|-----------|",
    ]
    for rank, row in candidates.iterrows():
        lines.append(
            f"| {rank} "
            f"| {row.get('sweep_atr_mult', '?'):.2f} "
            f"| {row.get('momentum_atr_mult', '?'):.2f} "
            f"| {row.get('momentum_body_ratio', '?'):.2f} "
            f"| {int(row.get('compression_lookback', 0))} "
            f"| {row.get('is_expectancy_R', float('nan')):+.3f} "
            f"| {row.get('oos_expectancy_R', float('nan')):+.3f} "
            f"| {row.get('is_profit_factor', float('nan')):.2f} "
            f"| {row.get('oos_profit_factor', float('nan')):.2f} "
            f"| {int(row.get('is_trades', 0))} "
            f"| {int(row.get('oos_trades', 0))} "
            f"| {row.get('oos_max_dd_R', float('nan')):.1f} "
            f"| {row.get('oos_score', float('nan')):.3f} "
            f"|"
        )
    return "\n".join(lines)
