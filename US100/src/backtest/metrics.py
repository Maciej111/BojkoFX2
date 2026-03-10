"""
Metrics calculation module for backtest analysis.
Handles segmentation by touch_no and computation of various performance metrics.
"""
import pandas as pd
import numpy as np


def compute_yearly_metrics(trades_df, equity_start=10000):
    """
    Compute per-year metrics and overall maxDD.

    Args:
        trades_df: DataFrame with trades (must have 'entry_time', 'pnl', 'R')
        equity_start: Starting equity

    Returns:
        dict with:
            - yearly_metrics: {year: {trades, expectancy_R, win_rate}}
            - overall_maxDD_pct: float
            - overall_maxDD_usd: float
    """

    if len(trades_df) == 0:
        return {
            'yearly_metrics': {},
            'overall_maxDD_pct': 0.0,
            'overall_maxDD_usd': 0.0
        }

    # Ensure datetime index
    if 'entry_time' not in trades_df.columns:
        return {
            'yearly_metrics': {},
            'overall_maxDD_pct': 0.0,
            'overall_maxDD_usd': 0.0
        }

    # Add year column
    trades_df = trades_df.copy()
    trades_df['year'] = pd.to_datetime(trades_df['entry_time']).dt.year

    # Compute per-year metrics
    yearly_metrics = {}

    for year in sorted(trades_df['year'].unique()):
        year_trades = trades_df[trades_df['year'] == year]

        wins = len(year_trades[year_trades['pnl'] > 0])
        total = len(year_trades)
        win_rate = (wins / total * 100) if total > 0 else 0.0

        expectancy_R = year_trades['R'].mean() if 'R' in year_trades.columns else 0.0

        yearly_metrics[int(year)] = {
            'trades': int(total),
            'expectancy_R': float(expectancy_R),
            'win_rate': float(win_rate)
        }

    # Compute overall maxDD
    # Sort by exit_time for equity curve
    if 'exit_time' in trades_df.columns:
        trades_sorted = trades_df.sort_values('exit_time').copy()
    else:
        trades_sorted = trades_df.copy()

    # Build equity curve
    equity = equity_start
    equity_curve = [equity]

    for pnl in trades_sorted['pnl']:
        equity += pnl
        equity_curve.append(equity)

    # Calculate maxDD
    peak = equity_curve[0]
    max_dd_usd = 0
    max_dd_pct = 0

    for equity_val in equity_curve:
        if equity_val > peak:
            peak = equity_val

        dd_usd = peak - equity_val
        dd_pct = (dd_usd / peak * 100) if peak > 0 else 0

        if dd_usd > max_dd_usd:
            max_dd_usd = dd_usd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    return {
        'yearly_metrics': yearly_metrics,
        'overall_maxDD_pct': float(max_dd_pct),
        'overall_maxDD_usd': float(max_dd_usd)
    }


def compute_expectancy_R(trades_df):
    """Compute expectancy in R (average R per trade)."""
    if len(trades_df) == 0:
        return 0.0
    if 'R' not in trades_df.columns:
        return 0.0
    return trades_df['R'].mean()


def compute_profit_factor(trades_df):
    """Compute profit factor (gross wins / gross losses)."""
    if len(trades_df) == 0:
        return 0.0

    if 'pnl' not in trades_df.columns:
        return 0.0

    wins = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    losses = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())

    if losses == 0:
        return float('inf') if wins > 0 else 0.0

    return wins / losses


def compute_max_losing_streak(trades_df):
    """Compute maximum consecutive losing streak."""
    if len(trades_df) == 0:
        return 0

    if 'pnl' not in trades_df.columns:
        return 0

    max_streak = 0
    current_streak = 0

    for pnl in trades_df['pnl']:
        if pnl < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return max_streak


def compute_max_drawdown(trades_df, initial_balance):
    """
    Compute maximum drawdown from equity curve.
    Returns: (maxDD_dollars, maxDD_percent)
    """
    if len(trades_df) == 0:
        return 0.0, 0.0

    if 'pnl' not in trades_df.columns:
        return 0.0, 0.0

    # Build equity curve
    equity = initial_balance + trades_df['pnl'].cumsum()
    equity = pd.concat([pd.Series([initial_balance]), equity]).reset_index(drop=True)

    # Calculate running maximum
    running_max = equity.expanding().max()
    drawdown = equity - running_max

    max_dd_dollars = drawdown.min()

    # Max DD percent
    max_dd_idx = drawdown.idxmin()
    peak_equity = running_max.iloc[max_dd_idx]

    if peak_equity > 0:
        max_dd_percent = (max_dd_dollars / peak_equity) * 100
    else:
        max_dd_percent = 0.0

    return abs(max_dd_dollars), abs(max_dd_percent)


def compute_segment_metrics(trades_df, initial_balance, segment_col='touch_no'):
    """
    Compute metrics segmented by column (e.g., touch_no).
    Returns dict: {segment_value: metrics_dict}
    """
    if segment_col not in trades_df.columns:
        # Return metrics for ALL as single segment
        return {'ALL': compute_metrics(trades_df, initial_balance)}

    segments = {}

    # Compute for ALL
    segments['ALL'] = compute_metrics(trades_df, initial_balance)

    # Compute per segment value
    for segment_val in sorted(trades_df[segment_col].unique()):
        segment_df = trades_df[trades_df[segment_col] == segment_val]
        # Always use TOUCH_ prefix for numeric values
        if isinstance(segment_val, (int, float)):
            segment_name = f"TOUCH_{int(segment_val)}"
        else:
            segment_name = str(segment_val)
        segments[segment_name] = compute_metrics(segment_df, initial_balance)

    return segments


def compute_metrics(trades_df, initial_balance):
    """
    Compute all metrics for a trades DataFrame.
    Returns dict with all performance metrics.
    """
    if len(trades_df) == 0:
        return {
            'trades_count': 0,
            'win_rate': 0.0,
            'expectancy_R': 0.0,
            'avg_R': 0.0,
            'median_R': 0.0,
            'profit_factor': 0.0,
            'total_pnl': 0.0,
            'max_dd_dollars': 0.0,
            'max_dd_percent': 0.0,
            'max_losing_streak': 0
        }

    # Basic counts
    trades_count = len(trades_df)

    # Win rate
    if 'pnl' in trades_df.columns:
        wins = (trades_df['pnl'] > 0).sum()
        win_rate = (wins / trades_count) * 100 if trades_count > 0 else 0.0
    else:
        win_rate = 0.0

    # R metrics
    expectancy_R = compute_expectancy_R(trades_df)
    avg_R = trades_df['R'].mean() if 'R' in trades_df.columns and len(trades_df) > 0 else 0.0
    median_R = trades_df['R'].median() if 'R' in trades_df.columns and len(trades_df) > 0 else 0.0

    # Profit factor
    profit_factor = compute_profit_factor(trades_df)

    # Total PnL
    total_pnl = trades_df['pnl'].sum() if 'pnl' in trades_df.columns else 0.0

    # Drawdown
    max_dd_dollars, max_dd_percent = compute_max_drawdown(trades_df, initial_balance)

    # Losing streak
    max_losing_streak = compute_max_losing_streak(trades_df)

    return {
        'trades_count': trades_count,
        'win_rate': win_rate,
        'expectancy_R': expectancy_R,
        'avg_R': avg_R,
        'median_R': median_R,
        'profit_factor': profit_factor,
        'total_pnl': total_pnl,
        'max_dd_dollars': max_dd_dollars,
        'max_dd_percent': max_dd_percent,
        'max_losing_streak': max_losing_streak
    }


def add_R_column(trades_df):
    """
    Add R column (pnl / risk) to trades DataFrame.
    Requires: entry_price, sl, pnl columns
    """
    if 'R' in trades_df.columns:
        return trades_df

    if 'entry_price' not in trades_df.columns or 'sl' not in trades_df.columns:
        # Cannot compute R without entry and sl
        trades_df['R'] = 0.0
        return trades_df

    # Calculate risk amount per trade
    # For LONG: risk = entry_price - sl
    # For SHORT: risk = sl - entry_price

    def calc_R(row):
        if row['direction'] == 'LONG':
            risk = row['entry_price'] - row['sl']
        else:  # SHORT
            risk = row['sl'] - row['entry_price']

        if risk <= 0:
            return 0.0

        # R = pnl / (risk * lot_size)
        # Since pnl already accounts for lot_size, we need risk in price terms
        # Actually pnl is in dollars, risk is in price points
        # We need to convert: risk_dollars = risk * lot_size
        # But we don't have lot_size here...
        # Let's assume pnl already normalized or we compute R as pnl/risk_points

        # Better approach: R = (exit_price - entry_price) / risk for LONG
        # But we only have pnl here. Let's use pnl / risk_dollars
        # We need lot_size - let's assume it's passed or use default

        # Simplification: assume lot_size is standard 100k
        # For EURUSD: 1 pip = $10 per lot
        # risk_dollars = risk * 100000

        lot_size = 100000  # TODO: get from config
        risk_dollars = risk * lot_size

        if risk_dollars == 0:
            return 0.0

        return row['pnl'] / risk_dollars

    trades_df['R'] = trades_df.apply(calc_R, axis=1)
    return trades_df


