"""
Complete Walk-Forward Validation with Monte Carlo
For H1 + BOS + HTF H4 strategy - Years 2021-2024
"""
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import copy

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.backtest.engine_enhanced import run_enhanced_backtest
from src.backtest.metrics import compute_metrics, add_R_column
from scripts.run_experiments import filter_bars_by_date, calculate_sanity_metrics


def monte_carlo_analysis(trades_df, n_simulations=1000, initial_balance=10000):
    """
    Monte Carlo simulation by randomly permuting trade order.

    Returns:
        dict with percentiles of expectancy and max DD
    """
    if trades_df is None or len(trades_df) == 0:
        return {
            'exp_5th': 0, 'exp_95th': 0,
            'dd_5th': 0, 'dd_95th': 0,
            'mean_exp': 0
        }

    trades_df = add_R_column(trades_df)

    original_r = trades_df['R'].values

    expectancies = []
    max_dds = []

    for _ in range(n_simulations):
        # Randomly permute trade order
        shuffled_r = np.random.permutation(original_r)

        # Calculate expectancy
        exp = np.mean(shuffled_r)
        expectancies.append(exp)

        # Calculate max DD
        equity = initial_balance
        equity_curve = [equity]

        for r_value in shuffled_r:
            # Assume R = 1% of current equity
            risk_amount = equity * 0.01
            pnl = r_value * risk_amount
            equity += pnl
            equity_curve.append(equity)

        # Calculate drawdown
        peak = equity_curve[0]
        max_dd = 0

        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

        max_dds.append(max_dd)

    return {
        'exp_5th': np.percentile(expectancies, 5),
        'exp_95th': np.percentile(expectancies, 95),
        'dd_5th': np.percentile(max_dds, 5),
        'dd_95th': np.percentile(max_dds, 95),
        'mean_exp': np.mean(expectancies)
    }


def run_year_backtest(year, symbol, bars_df, config, initial_balance):
    """
    Run backtest for a single year.

    Returns:
        dict with results
    """
    print(f"\n{'='*60}")
    print(f"YEAR {year}")
    print(f"{'='*60}")

    # Filter bars for this year
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    year_bars = filter_bars_by_date(bars_df, start_dt, end_dt)

    if len(year_bars) == 0:
        print(f"⚠ No data for year {year}")
        return None

    print(f"✓ Loaded {len(year_bars)} H1 bars for {year}")

    # Run backtest
    trades_df = run_enhanced_backtest(
        config=config,
        bars_df=year_bars,
        output_suffix=f"_h1_wf_{year}",
        enable_filters={
            'use_bos_filter': True,
            'use_htf_location_filter': True,
            'use_session_filter': False,
            'use_partial_tp': False
        }
    )

    if trades_df is None or len(trades_df) == 0:
        print(f"  ⚠ No trades in {year}")
        return {
            'year': year,
            'trades_count': 0,
            'win_rate': 0.0,
            'expectancy_R': 0.0,
            'profit_factor': 0.0,
            'max_dd_percent': 0.0,
            'return_pct': 0.0,
            'avg_win_R': 0.0,
            'avg_loss_R': 0.0,
            'long_exp': 0.0,
            'short_exp': 0.0,
            'sanity': {},
            'monte_carlo': {}
        }

    # Add R column
    trades_df = add_R_column(trades_df)

    # Calculate metrics
    metrics = compute_metrics(trades_df, initial_balance)

    # Calculate additional metrics
    wins = trades_df[trades_df['R'] > 0]
    losses = trades_df[trades_df['R'] <= 0]

    avg_win_R = wins['R'].mean() if len(wins) > 0 else 0.0
    avg_loss_R = losses['R'].mean() if len(losses) > 0 else 0.0

    # Long/Short analysis
    longs = trades_df[trades_df['direction'] == 'LONG']
    shorts = trades_df[trades_df['direction'] == 'SHORT']

    long_exp = longs['R'].mean() if len(longs) > 0 else 0.0
    short_exp = shorts['R'].mean() if len(shorts) > 0 else 0.0

    # Sanity checks
    sanity = calculate_sanity_metrics(trades_df, year_bars)

    # Monte Carlo
    print(f"  Running Monte Carlo simulation...")
    mc_results = monte_carlo_analysis(trades_df, n_simulations=1000, initial_balance=initial_balance)

    # Final balance
    final_balance = initial_balance + metrics['total_pnl']
    return_pct = ((final_balance - initial_balance) / initial_balance) * 100

    result = {
        'year': year,
        'trades_count': metrics['trades_count'],
        'win_rate': metrics['win_rate'],
        'expectancy_R': metrics['expectancy_R'],
        'profit_factor': metrics['profit_factor'],
        'max_dd_percent': metrics['max_dd_percent'],
        'return_pct': return_pct,
        'avg_win_R': avg_win_R,
        'avg_loss_R': avg_loss_R,
        'long_exp': long_exp,
        'short_exp': short_exp,
        'long_count': len(longs),
        'short_count': len(shorts),
        'sanity': sanity,
        'monte_carlo': mc_results
    }

    print(f"\n✓ Year {year} Complete:")
    print(f"  Trades: {metrics['trades_count']}")
    print(f"  Win Rate: {metrics['win_rate']:.2f}%")
    print(f"  Expectancy: {metrics['expectancy_R']:.3f}R")
    print(f"  Return: {return_pct:.2f}%")
    print(f"  Monte Carlo Exp 5th-95th: [{mc_results['exp_5th']:.3f}R, {mc_results['exp_95th']:.3f}R]")

    return result


def generate_walkforward_report(results, output_path):
    """Generate comprehensive walk-forward report."""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Filter out None results
    results = [r for r in results if r is not None]

    if len(results) == 0:
        print("⚠ No results to generate report")
        return

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Walk-Forward Validation Report\n")
        f.write("# H1 + BOS + HTF H4 Location Filter Strategy\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("---\n\n")

        f.write("## Strategy Configuration\n\n")
        f.write("```yaml\n")
        f.write("Timeframe: H1\n")
        f.write("Symbol: EURUSD\n")
        f.write("Filters:\n")
        f.write("  - BOS (Break of Structure)\n")
        f.write("  - HTF H4 Location Filter\n")
        f.write("Parameters:\n")
        f.write("  risk_reward: 1.5\n")
        f.write("  max_touches_per_zone: 1\n")
        f.write("  demand_max_position: 0.35\n")
        f.write("  supply_min_position: 0.65\n")
        f.write("  pivot_lookback: 3\n")
        f.write("  htf_period: 4h\n")
        f.write("  htf_lookback: 100\n")
        f.write("```\n\n")

        f.write("---\n\n")

        # Yearly Results Table
        f.write("## Yearly Results\n\n")

        f.write("| Year | Trades | Win Rate (%) | Expectancy (R) | Profit Factor | Max DD (%) | Return (%) |\n")
        f.write("|------|--------|--------------|----------------|---------------|------------|------------|\n")

        for r in results:
            f.write(f"| {r['year']} | {r['trades_count']} | {r['win_rate']:.2f} | {r['expectancy_R']:.3f} | {r['profit_factor']:.2f} | {r['max_dd_percent']:.2f} | {r['return_pct']:.2f} |\n")

        f.write("\n")

        # Aggregated Statistics
        f.write("## Aggregated Statistics (All Years)\n\n")

        expectancies = [r['expectancy_R'] for r in results]
        pfs = [r['profit_factor'] for r in results]
        dds = [r['max_dd_percent'] for r in results]
        returns = [r['return_pct'] for r in results]

        mean_exp = np.mean(expectancies)
        median_exp = np.median(expectancies)
        std_exp = np.std(expectancies)

        positive_years = len([e for e in expectancies if e > 0])
        pf_above_1 = len([p for p in pfs if p > 1.0])

        best_year = max(results, key=lambda x: x['expectancy_R'])
        worst_year = min(results, key=lambda x: x['expectancy_R'])

        f.write(f"- **Mean Expectancy:** {mean_exp:.3f}R\n")
        f.write(f"- **Median Expectancy:** {median_exp:.3f}R\n")
        f.write(f"- **Std Dev Expectancy:** {std_exp:.3f}R\n")
        f.write(f"- **Years with Expectancy > 0:** {positive_years}/{len(results)}\n")
        f.write(f"- **Years with PF > 1.0:** {pf_above_1}/{len(results)}\n")
        f.write(f"- **Best Year:** {best_year['year']} ({best_year['expectancy_R']:.3f}R)\n")
        f.write(f"- **Worst Year:** {worst_year['year']} ({worst_year['expectancy_R']:.3f}R)\n")
        f.write(f"- **Mean Return:** {np.mean(returns):.2f}%\n")
        f.write(f"- **Mean Max DD:** {np.mean(dds):.2f}%\n\n")

        # Long vs Short Analysis
        f.write("## Long vs Short Analysis\n\n")

        f.write("| Year | Long Trades | Long Exp (R) | Short Trades | Short Exp (R) |\n")
        f.write("|------|-------------|--------------|--------------|---------------|\n")

        for r in results:
            f.write(f"| {r['year']} | {r['long_count']} | {r['long_exp']:.3f} | {r['short_count']} | {r['short_exp']:.3f} |\n")

        f.write("\n")

        # Monte Carlo Results
        f.write("## Monte Carlo Stability Analysis (1000 simulations per year)\n\n")

        f.write("| Year | Expectancy 5th %ile | Expectancy 95th %ile | Max DD 5th %ile | Max DD 95th %ile |\n")
        f.write("|------|--------------------|--------------------|-----------------|------------------|\n")

        for r in results:
            mc = r['monte_carlo']
            f.write(f"| {r['year']} | {mc['exp_5th']:.3f}R | {mc['exp_95th']:.3f}R | {mc['dd_5th']:.2f}% | {mc['dd_95th']:.2f}% |\n")

        f.write("\n")

        # Sanity Checks
        f.write("## Sanity Checks\n\n")

        for r in results:
            f.write(f"### Year {r['year']}\n\n")

            sanity = r.get('sanity', {})

            f.write(f"- **Average Spread:** {sanity.get('spread_pips', 0):.2f} pips\n")
            f.write(f"- **Same-bar SL:** {sanity.get('same_bar_sl_pct', 0):.2f}%\n")
            f.write(f"- **Same-bar Entry:** {sanity.get('same_bar_entry_pct', 0):.2f}% (should be 0%)\n")

            if sanity.get('same_bar_entry_pct', 0) == 0:
                f.write(f"- **Look-ahead Check:** ✅ PASS\n\n")
            else:
                f.write(f"- **Look-ahead Check:** ⚠️ WARNING\n\n")

        # Interpretation Section
        f.write("---\n\n")
        f.write("## Interpretation & Conclusions\n\n")

        f.write("### 1. Does strategy have positive expectancy in >= 3 of 4 years?\n\n")
        if positive_years >= 3:
            f.write(f"✅ **YES** - {positive_years}/{len(results)} years have positive expectancy\n\n")
        else:
            f.write(f"❌ **NO** - Only {positive_years}/{len(results)} years have positive expectancy\n\n")

        f.write("### 2. Is 4-year average expectancy > 0?\n\n")
        if mean_exp > 0:
            f.write(f"✅ **YES** - Mean expectancy: {mean_exp:.3f}R\n\n")
        else:
            f.write(f"❌ **NO** - Mean expectancy: {mean_exp:.3f}R\n\n")

        f.write("### 3. Is PF > 1 in majority of years?\n\n")
        if pf_above_1 >= len(results) / 2:
            f.write(f"✅ **YES** - {pf_above_1}/{len(results)} years have PF > 1.0\n\n")
        else:
            f.write(f"❌ **NO** - Only {pf_above_1}/{len(results)} years have PF > 1.0\n\n")

        f.write("### 4. Is drawdown stable or explosive?\n\n")
        dd_std = np.std(dds)
        if dd_std < 10:
            f.write(f"✅ **STABLE** - DD std dev: {dd_std:.2f}% (consistent across years)\n\n")
        else:
            f.write(f"⚠️ **VARIABLE** - DD std dev: {dd_std:.2f}% (inconsistent across years)\n\n")

        f.write("### 5. Do long and short behave symmetrically?\n\n")

        avg_long_exp = np.mean([r['long_exp'] for r in results])
        avg_short_exp = np.mean([r['short_exp'] for r in results])

        diff = abs(avg_long_exp - avg_short_exp)

        f.write(f"- Average Long Expectancy: {avg_long_exp:.3f}R\n")
        f.write(f"- Average Short Expectancy: {avg_short_exp:.3f}R\n")
        f.write(f"- Difference: {diff:.3f}R\n\n")

        if diff < 0.1:
            f.write("✅ **SYMMETRIC** - Long and short perform similarly\n\n")
        else:
            f.write("⚠️ **ASYMMETRIC** - Long and short show different characteristics\n\n")

        # Final Verdict
        f.write("---\n\n")
        f.write("## Final Verdict\n\n")

        score = 0
        if positive_years >= 3:
            score += 1
        if mean_exp > 0:
            score += 1
        if pf_above_1 >= len(results) / 2:
            score += 1
        if dd_std < 10:
            score += 1

        f.write(f"**Validation Score:** {score}/4 criteria met\n\n")

        if score >= 3:
            f.write("### ✅ STRATEGY VALIDATED\n\n")
            f.write("The strategy shows consistent positive performance across multiple years.\n")
            f.write("**Recommendation:** Proceed to demo testing.\n\n")
        elif score == 2:
            f.write("### ⚠️ MIXED RESULTS\n\n")
            f.write("The strategy shows some positive characteristics but lacks consistency.\n")
            f.write("**Recommendation:** Proceed with caution, extended testing recommended.\n\n")
        else:
            f.write("### ❌ STRATEGY NOT VALIDATED\n\n")
            f.write("The strategy does not show consistent positive performance.\n")
            f.write("**Recommendation:** Further optimization or different approach needed.\n\n")

        f.write("---\n\n")
        f.write(f"*Report generated: {datetime.now()}*\n")


def main():
    print(f"\n{'='*60}")
    print("WALK-FORWARD VALIDATION")
    print("H1 + BOS + HTF H4 Strategy")
    print("Years: 2021-2024")
    print(f"{'='*60}\n")

    # Load configuration
    config = load_config()
    initial_balance = config['execution']['initial_balance']

    # Set strategy parameters
    config['strategy']['use_bos_filter'] = True
    config['strategy']['use_htf_location_filter'] = True
    config['strategy']['htf_period'] = '4h'
    config['strategy']['risk_reward'] = 1.5
    config['strategy']['max_touches_per_zone'] = 1

    # Load H1 bars
    symbol = config['data']['symbol']
    bars_file = os.path.join(config['data']['bars_dir'], f"{symbol.lower()}_h1_bars.csv")

    if not os.path.exists(bars_file):
        print(f"✗ H1 bars not found: {bars_file}")
        print(f"  Run: python scripts/build_h1_bars.py")
        return

    print(f"Loading H1 bars...")
    bars_df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)
    print(f"✓ Loaded {len(bars_df)} H1 bars")
    print(f"  Date range: {bars_df.index[0]} to {bars_df.index[-1]}")

    # Determine available years
    start_year = bars_df.index[0].year
    end_year = bars_df.index[-1].year

    available_years = list(range(start_year, end_year + 1))
    print(f"\n✓ Available years: {available_years}")

    # Run backtests for each year
    results = []

    for year in [2021, 2022, 2023, 2024]:
        if year in available_years:
            result = run_year_backtest(year, symbol, bars_df, config, initial_balance)
            if result:
                results.append(result)
        else:
            print(f"\n⚠ Year {year}: No data available")

    # Generate report
    if len(results) > 0:
        print(f"\n{'='*60}")
        print("Generating Walk-Forward Report...")
        print(f"{'='*60}\n")

        report_path = "data/outputs/walkforward_H1_summary.md"
        generate_walkforward_report(results, report_path)

        print(f"✓ Report saved to: {report_path}")

        # Quick summary
        print(f"\n{'='*60}")
        print("WALK-FORWARD COMPLETE")
        print(f"{'='*60}\n")

        print("Summary:")
        for r in results:
            print(f"  {r['year']}: {r['trades_count']:3d} trades | {r['expectancy_R']:+.3f}R | {r['return_pct']:+6.2f}%")

        if len(results) > 0:
            mean_exp = np.mean([r['expectancy_R'] for r in results])
            positive_years = len([r for r in results if r['expectancy_R'] > 0])
            print(f"\n  Mean Expectancy: {mean_exp:+.3f}R")
            print(f"  Positive Years: {positive_years}/{len(results)}")
    else:
        print("\n✗ No results generated - insufficient data")
        print("\nData Availability:")
        print("  Required: Years 2021, 2022, 2023, 2024")
        print(f"  Available: Years {available_years}")
        print("\nTo complete walk-forward validation:")
        print("  1. Download tick data for missing years")
        print("  2. Build H1 bars: python scripts/build_h1_bars.py")
        print("  3. Re-run this script")


if __name__ == "__main__":
    main()

