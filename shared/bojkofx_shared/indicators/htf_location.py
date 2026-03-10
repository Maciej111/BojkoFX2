"""
Higher Timeframe (HTF) analysis and zone location filtering.
"""
import pandas as pd
import numpy as np


def build_htf_from_bars(bars_df, htf_period='1H'):
    """
    Build higher timeframe bars from M15 bars.

    Args:
        bars_df: DataFrame with M15 OHLC data (indexed by timestamp)
        htf_period: Timeframe string (e.g., '1H', '4H')

    Returns:
        DataFrame with HTF OHLC data
    """
    # Resample bid
    bid_ohlc = bars_df[['open_bid', 'high_bid', 'low_bid', 'close_bid']].resample(htf_period).agg({
        'open_bid': 'first',
        'high_bid': 'max',
        'low_bid': 'min',
        'close_bid': 'last'
    })

    # Resample ask
    ask_ohlc = bars_df[['open_ask', 'high_ask', 'low_ask', 'close_ask']].resample(htf_period).agg({
        'open_ask': 'first',
        'high_ask': 'max',
        'low_ask': 'min',
        'close_ask': 'last'
    })

    # Combine
    htf_df = pd.concat([bid_ohlc, ask_ohlc], axis=1)

    # Forward fill missing data
    htf_df['close_bid'] = htf_df['close_bid'].ffill()
    htf_df['close_ask'] = htf_df['close_ask'].ffill()

    for col in ['open_bid', 'high_bid', 'low_bid']:
        htf_df[col] = htf_df[col].fillna(htf_df['close_bid'])

    for col in ['open_ask', 'high_ask', 'low_ask']:
        htf_df[col] = htf_df[col].fillna(htf_df['close_ask'])

    return htf_df


def calculate_zone_position_in_htf_range(zone_mid, htf_df, zone_time, lookback=100):
    """
    Calculate zone's position within HTF range as percentile.

    Position = (zone_mid - lowest_low) / (highest_high - lowest_low)

    0.0 = at bottom of range
    1.0 = at top of range
    0.5 = middle

    Args:
        zone_mid: Middle price of zone
        htf_df: HTF DataFrame with high/low
        zone_time: Timestamp when zone was created
        lookback: Number of HTF bars to look back

    Returns:
        float: position (0.0 to 1.0), or None if cannot calculate
    """
    # Find HTF bar at or before zone_time
    htf_at_zone = htf_df[htf_df.index <= zone_time]

    if len(htf_at_zone) < lookback:
        # Not enough HTF data
        return None

    # Get last N HTF bars
    recent_htf = htf_at_zone.tail(lookback)

    highest_high = recent_htf['high_bid'].max()
    lowest_low = recent_htf['low_bid'].min()

    range_size = highest_high - lowest_low

    if range_size == 0:
        return 0.5  # No range, assume middle

    position = (zone_mid - lowest_low) / range_size

    # Clamp to [0, 1]
    position = max(0.0, min(1.0, position))

    return position


def check_zone_location_filter(zone_type, zone_position, demand_max_position=0.35, supply_min_position=0.65):
    """
    Check if zone passes HTF location filter.

    DEMAND zones should be near bottom (position <= demand_max_position)
    SUPPLY zones should be near top (position >= supply_min_position)

    Args:
        zone_type: 'DEMAND' or 'SUPPLY'
        zone_position: Position in HTF range (0.0 to 1.0)
        demand_max_position: Max position for demand zones
        supply_min_position: Min position for supply zones

    Returns:
        bool: True if zone passes filter
    """
    if zone_position is None:
        return False

    if zone_type == 'DEMAND':
        return zone_position <= demand_max_position
    elif zone_type == 'SUPPLY':
        return zone_position >= supply_min_position
    else:
        return False

