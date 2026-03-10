import pandas as pd
import sys
import os
from tqdm import tqdm

# Imports assuming script run from root
sys.path.append(os.getcwd())

from src.indicators.atr import calculate_atr
from src.zones.detect_zones import detect_zones
from src.backtest.execution import ExecutionEngine
from src.reporting.report import generate_report
from src.utils.config import load_config

def run_backtest(config=None, bars_df=None, output_suffix=""):
    """
    Run backtest with optional custom config and bars_df.
    output_suffix: add suffix to output files (for batch/sensitivity tests)
    """
    if config is None:
        config = load_config()

    if bars_df is None:
        bars_file = os.path.join(config['data']['bars_dir'],
                                 f"{config['data']['symbol']}_m15_bars.csv")

        if not os.path.exists(bars_file):
            print(f"Bars file not found: {bars_file}. Please run build_bars.py first.")
            return None

        print("Loading data...")
        df = pd.read_csv(bars_file, index_col='timestamp', parse_dates=True)
    else:
        df = bars_df.copy()

    print("Calculating ATR...")
    # ATR on Bid or Mid? Using Bid as per earlier decision
    atr = calculate_atr(df, period=14)

    print("Detecting Zones...")
    # Validating look-ahead: detect_zones only uses past data relative to index i
    zones = detect_zones(df, atr, config['strategy'])
    print(f"Detected {len(zones)} zones.")

    # Sort zones by creation time
    zones.sort(key=lambda z: z.creation_time)

    # Initialize Execution
    engine = ExecutionEngine(config['execution']['initial_balance'], config['execution'])

    # Track active zones (zones that can still be traded)
    active_zones = []

    # Anti-lookahead config
    allow_same_bar_entry = config['execution'].get('allow_same_bar_entry', False)

    print("Starting Backtest Loop...")

    # Iterate through bars
    for time, row in tqdm(df.iterrows(), total=len(df)):
        # 1. Update Engine (Check Fills/SL/TP)
        # Construct bar dict
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

        # 2. Add newly created zones to active zones
        # Check if any zones were created at this bar
        for z in zones:
            if z.creation_time == time:
                active_zones.append(z)

        # 3. Strategy Logic - check active zones for touches
        current_atr = atr.loc[time] if time in atr.index else None
        if pd.isna(current_atr):
            continue

        buffer = current_atr * config['strategy']['buffer_atr_mult']

        for z in list(active_zones):
            # Anti-lookahead check: zone must be created before current bar (not same bar)
            if not allow_same_bar_entry:
                if z.creation_time >= time:
                    # Skip - zone created at current bar or future (shouldn't happen but safety)
                    continue

            # Check if zone was touched
            touched = False

            if z.type == 'DEMAND':
                # Check if price touched zone (low_ask <= zone.top)
                if row['low_ask'] <= z.top:
                    touched = True
            elif z.type == 'SUPPLY':
                # Check if price touched zone (high_bid >= zone.bottom)
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
                        continue # Invalid zone structure

                    tp_price = entry_price + (risk * config['strategy']['risk_reward'])

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

                    engine.place_limit_order(
                        'SHORT', entry_price, sl_price, tp_price, time,
                        comment=f"Supply Touch #{z.touch_count}",
                        touch_no=z.touch_count,
                        zone_created_at=z.creation_time
                    )

                # Deactivate zone after max touches (e.g., 3)
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
    run_backtest()
