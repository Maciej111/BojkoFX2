"""
Enhanced backtest engine with EMA, BOS, and HTF location filters.
"""
import pandas as pd
import sys
import os
from tqdm import tqdm

sys.path.append(os.getcwd())

from src.indicators.atr import calculate_atr
from src.indicators.ema import calculate_ema_from_df
from src.indicators.pivots import detect_pivots, check_break_of_structure
from src.indicators.htf_location import build_htf_from_bars, calculate_zone_position_in_htf_range, check_zone_location_filter
from src.indicators.session_filter import is_in_session
from src.zones.detect_zones import detect_zones
from src.backtest.execution import ExecutionEngine
from src.backtest.execution_partial_tp import PartialTPEngine
from src.reporting.report import generate_report
from src.utils.config import load_config


def run_enhanced_backtest(config=None, bars_df=None, output_suffix="", enable_filters=None):
    """
    Run backtest with optional filters (EMA, BOS, HTF location).

    Args:
        config: Configuration dict
        bars_df: DataFrame with bars
        output_suffix: Suffix for output files
        enable_filters: Dict to override filter settings, e.g.:
                       {'use_ema_filter': True, 'use_bos_filter': False}

    Returns:
        DataFrame with trades
    """
    if config is None:
        config = load_config()

    # Override filters if specified
    if enable_filters:
        for key, value in enable_filters.items():
            config['strategy'][key] = value

    if bars_df is None:
        bars_file = os.path.join(config['data']['bars_dir'],
                                 f"{config['data']['symbol']}_m15_bars.csv")

        if not os.path.exists(bars_file):
            print(f"Bars file not found: {bars_file}")
            return None

        print("Loading data...")
        df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)
    else:
        df = bars_df.copy()

    print(f"Loaded {len(df)} M15 bars from {df.index[0]} to {df.index[-1]}")

    # Calculate indicators
    print("Calculating ATR...")
    atr = calculate_atr(df, period=14)

    # EMA filter preparation
    ema = None
    if config['strategy'].get('use_ema_filter', False):
        print(f"Calculating EMA{config['strategy'].get('ema_period', 200)}...")
        ema = calculate_ema_from_df(df, column='close_bid', period=config['strategy'].get('ema_period', 200))

    # Pivot detection for BOS
    pivot_highs = None
    pivot_lows = None
    if config['strategy'].get('use_bos_filter', False):
        print(f"Detecting pivots (lookback={config['strategy'].get('pivot_lookback', 3)})...")
        pivot_highs, pivot_lows = detect_pivots(df, lookback=config['strategy'].get('pivot_lookback', 3))

    # HTF data for location filter
    htf_df = None
    if config['strategy'].get('use_htf_location_filter', False):
        print(f"Building HTF ({config['strategy'].get('htf_period', '1H')}) bars...")
        htf_df = build_htf_from_bars(df, htf_period=config['strategy'].get('htf_period', '1H'))
        print(f"Built {len(htf_df)} HTF bars")

    print("Detecting Zones...")
    zones = detect_zones(df, atr, config['strategy'],
                        pivot_highs=pivot_highs, pivot_lows=pivot_lows,
                        htf_df=htf_df)

    print(f"Detected {len(zones)} zones (after filters)")

    zones.sort(key=lambda z: z.creation_time)

    # Choose execution engine based on config
    use_partial_tp = config['strategy'].get('use_partial_tp', False)

    if use_partial_tp:
        engine = PartialTPEngine(config['execution']['initial_balance'], config['execution'])
        print("Using Partial TP execution engine")
    else:
        engine = ExecutionEngine(config['execution']['initial_balance'], config['execution'])

    active_zones = []
    allow_same_bar_entry = config['execution'].get('allow_same_bar_entry', False)

    # Session filter settings
    use_session_filter = config['strategy'].get('use_session_filter', False)
    session_mode = config['strategy'].get('session_mode', 'both')

    print("Starting Backtest Loop...")

    for time, row in tqdm(df.iterrows(), total=len(df)):
        bar_data = {
            'timestamp': time,
            'open_bid': row['open_bid'],
            'high_bid': row['high_bid'],
            'low_bid': row['low_bid'],
            'close_bid': row['close_bid'],
            'open_ask': row['open_ask'],
            'high_ask': row['high_ask'],
            'low_ask': row['low_ask'],
            'close_ask': row['close_ask']
        }

        engine.process_bar(bar_data)

        # Add newly created zones
        for z in zones:
            if z.creation_time == time:
                active_zones.append(z)

        # Check active zones for touches
        current_atr = atr.loc[time] if time in atr.index else None
        if pd.isna(current_atr):
            continue

        buffer = current_atr * config['strategy']['buffer_atr_mult']

        for z in list(active_zones):
            # Anti-lookahead
            if not allow_same_bar_entry:
                if z.creation_time >= time:
                    continue

            # Session filter check
            if use_session_filter:
                if not is_in_session(time, session_mode):
                    continue

            # Check EMA filter
            if config['strategy'].get('use_ema_filter', False) and ema is not None:
                current_ema = ema.loc[time] if time in ema.index else None
                if pd.isna(current_ema):
                    continue

                close_bid = row['close_bid']

                # LONG only if close > EMA
                if z.type == 'DEMAND' and close_bid <= current_ema:
                    continue

                # SHORT only if close < EMA
                if z.type == 'SUPPLY' and close_bid >= current_ema:
                    continue

            # Check if zone was touched
            touched = False

            if z.type == 'DEMAND':
                if row['low_ask'] <= z.top:
                    touched = True
            elif z.type == 'SUPPLY':
                if row['high_bid'] >= z.bottom:
                    touched = True

            if touched:
                z.touch_count += 1

                # Place order
                if z.type == 'DEMAND':
                    entry_price = z.top
                    sl_price = z.bottom - buffer
                    risk = entry_price - sl_price
                    if risk <= 0:
                        continue

                    tp_price = entry_price + (risk * config['strategy']['risk_reward'])

                    # RR filter for BOS_RR mode
                    strategy_mode = config['strategy'].get('strategy_mode', 'FULL')
                    if strategy_mode == 'BOS_RR':
                        min_rr = config['strategy'].get('min_rr', 1.2)
                        actual_rr = (tp_price - entry_price) / risk if risk > 0 else 0
                        if actual_rr < min_rr:
                            continue  # Skip if RR too low

                    if use_partial_tp:
                        engine.place_limit_order(
                            'LONG', entry_price, sl_price, tp_price, time,
                            comment=f"Demand Touch #{z.touch_count}",
                            touch_no=z.touch_count,
                            zone_created_at=z.creation_time,
                            first_tp_target=config['strategy'].get('partial_tp_first_target', 1.0),
                            final_tp_target=config['strategy'].get('partial_tp_second_target', 1.5)
                        )
                    else:
                        engine.place_limit_order(
                            'LONG', entry_price, sl_price, tp_price, time,
                            comment=f"Demand Touch #{z.touch_count}",
                            touch_no=z.touch_count,
                            zone_created_at=z.creation_time
                        )

                elif z.type == 'SUPPLY':
                    entry_price = z.bottom
                    sl_price = z.top + buffer
                    risk = sl_price - entry_price
                    if risk <= 0:
                        continue

                    tp_price = entry_price - (risk * config['strategy']['risk_reward'])

                    # RR filter for BOS_RR mode
                    strategy_mode = config['strategy'].get('strategy_mode', 'FULL')
                    if strategy_mode == 'BOS_RR':
                        min_rr = config['strategy'].get('min_rr', 1.2)
                        actual_rr = (entry_price - tp_price) / risk if risk > 0 else 0
                        if actual_rr < min_rr:
                            continue  # Skip if RR too low

                    if use_partial_tp:
                        engine.place_limit_order(
                            'SHORT', entry_price, sl_price, tp_price, time,
                            comment=f"Supply Touch #{z.touch_count}",
                            touch_no=z.touch_count,
                            zone_created_at=z.creation_time,
                            first_tp_target=config['strategy'].get('partial_tp_first_target', 1.0),
                            final_tp_target=config['strategy'].get('partial_tp_second_target', 1.5)
                        )
                    else:
                        engine.place_limit_order(
                            'SHORT', entry_price, sl_price, tp_price, time,
                            comment=f"Supply Touch #{z.touch_count}",
                            touch_no=z.touch_count,
                            zone_created_at=z.creation_time
                        )

                # Deactivate zone after max touches
                max_touches = config['strategy'].get('max_touches_per_zone', 3)
                if z.touch_count >= max_touches:
                    z.active = False
                    active_zones.remove(z)

    # Generate Report
    trades = engine.get_results_df()
    print(f"Backtest finished. Total trades: {len(trades)}")

    if len(trades) > 0:
        output_dir = config['reporting']['output_dir']
        generate_report(trades, output_dir, config['execution']['initial_balance'], suffix=output_suffix)

    return trades


if __name__ == "__main__":
    run_enhanced_backtest()


