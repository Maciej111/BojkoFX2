import numpy as np

class Zone:
    def __init__(self, ztype, start_idx, end_idx, top, bottom, creation_time):
        self.type = ztype # 'DEMAND' or 'SUPPLY'
        self.start_idx = start_idx
        self.end_idx = end_idx
        self.top = top
        self.bottom = bottom
        self.creation_time = creation_time
        self.tested_count = 0
        self.active = True
        self.touch_count = 0  # Track how many times zone was touched

    def __repr__(self):
        return f"Zone({self.type}, {self.top}-{self.bottom}, {self.creation_time})"

def detect_zones(df, atr_series, strategy_config, pivot_highs=None, pivot_lows=None, htf_df=None):
    """
    Detect Supply/Demand zones based on logic:
    1. Impulse candle (large body)
    2. Preceded by Base (small body candles)
    3. Optional: BOS filter (if pivot_highs/pivot_lows provided)
    4. Optional: HTF location filter (if htf_df provided)

    Args:
        df: M15 bars DataFrame
        atr_series: ATR series
        strategy_config: Strategy config dict (config['strategy'])
        pivot_highs: Series with pivot high prices (for BOS filter)
        pivot_lows: Series with pivot low prices (for BOS filter)
        htf_df: HTF bars DataFrame (for location filter)
    """
    zones = []

    impulse_mult = strategy_config['impulse_atr_mult']
    base_max = strategy_config['base_max_candles']
    base_min = strategy_config['base_min_candles']
    base_body_mult = strategy_config.get('base_body_atr_mult', 0.6)

    # Filter settings
    use_bos = strategy_config.get('use_bos_filter', False) and pivot_highs is not None and pivot_lows is not None
    use_htf_location = strategy_config.get('use_htf_location_filter', False) and htf_df is not None

    # We iterate from skipping enough for ATR
    # Using iterrows is slow but readable. For 10k rows it's okay.
    # But let's use index loop.

    closes = df['close_bid'].values
    opens = df['open_bid'].values
    highs = df['high_bid'].values
    lows = df['low_bid'].values
    times = df.index
    atrs = atr_series.values

    # Pre-calculate body sizes
    bodies = np.abs(closes - opens)

    for i in range(base_max + 1, len(df)):
        current_atr = atrs[i-1] # Use previous ATR to avoid lookahead? Or current? Usually previous.
        if np.isnan(current_atr):
            continue

        is_impulse_up = (closes[i] > opens[i]) and (bodies[i] > impulse_mult * current_atr)
        is_impulse_down = (closes[i] < opens[i]) and (bodies[i] > impulse_mult * current_atr)

        if not (is_impulse_up or is_impulse_down):
            continue

        # Check backward for base
        # Base candidates: i-1, i-2...
        # We need 2 to 8 candles of "base" characteristic.
        # Base characteristic: Small body? Or specifically RBD/DBR structure.
        # DBR: Drop -> Base -> Rally (Impulse Up)
        # Verify "Base" logic:
        # Base candles often have body < 50% of range, or body < ATR * 0.5

        # Let's simplify: Base is 1 to base_max candles before impulse where body is small.
        # Strict DBR: Last candle of base was bearish or small?
        # Actually usually Base is consolidation.

        start_base = i - 1
        base_candles = []

        for k in range(1, base_max + 2):
            idx = i - k
            if idx < 0: break

            # Check if candle is "base-like"
            # Condition: Body < Threshold? Or contained within range?
            # Let's use: Body < base_body_mult * ATR (configurable)
            # User said "mały zakres względem mediany".
            # Let's interpret as Body < base_body_mult * ATR

            if bodies[idx] < base_body_mult * current_atr:
                base_candles.append(idx)
            else:
                break

        if len(base_candles) < base_min:
            continue

        # Use first and last index of base
        # base_candles are in reverse order: [i-1, i-2, ...]
        last_base_idx = base_candles[0] # i-1
        first_base_idx = base_candles[-1]

        # Calculate Zone Boundaries
        # Demand:
        # Top = Max Body of Base? Or Max High?
        # Bottom = Lowest Low of Base
        # Supply:
        # Top = Highest High of Base
        # Bottom = Min Body of Base? Or Min Low?

        # Usually:
        # Demand: Proximal = Highest Body (or Wick top if small), Distal = Lowest Low
        # Supply: Proximal = Lowest Body, Distal = Highest High

        # Let's calculate Proximal/Distal based on standard S&D

        base_highs = highs[first_base_idx : last_base_idx + 1]
        base_lows = lows[first_base_idx : last_base_idx + 1]
        base_opens = opens[first_base_idx : last_base_idx + 1]
        base_closes = closes[first_base_idx : last_base_idx + 1]

        distal = None
        proximal = None
        type_ = None

        if is_impulse_up:
            # DBR -> Demand
            # Check if "Drop" preceded base?
            # The strategy says DBR. So before base there should be a Drop?
            # Or just "Rally from Base". Strict DBR implies trend change or continuation.
            # I'll implement simplified "Base -> Rally" as Demand.

            type_ = 'DEMAND'
            # Distal = Lowest Low in Base
            distal = np.min(base_lows)

            # Proximal = Highest Body Top in Base? Or Highest High?
            # Aggressive: Highest High of Base (wider zone).
            # Refined: Highest Open/Close of Base.
            # Let's use Highest Body Top (Open or Close).
            max_body_top = np.max(np.maximum(base_opens, base_closes))

            proximal = max_body_top

            # Sanity check zone width
            width = proximal - distal
            # User config min/max zone width (in pips)
            # Need to convert price to pips. eurusd 0.0001
            # assuming 0.0001

        elif is_impulse_down:
            # RBD -> Supply
            type_ = 'SUPPLY'
            # Distal = Highest High
            distal = np.max(base_highs)

            # Proximal = Lowest Body Bottom
            min_body_bottom = np.min(np.minimum(base_opens, base_closes))
            proximal = min_body_bottom

        # Add Zone
        if type_:
            # Check width constraints
            width_pips = abs(distal - proximal) * 10000
            if strategy_config['min_zone_width_pips'] <= width_pips <= strategy_config['max_zone_width_pips']:

                # BOS Filter Check
                if use_bos:
                    from src.indicators.pivots import check_break_of_structure
                    demand_bos, supply_bos = check_break_of_structure(
                        df, pivot_highs, pivot_lows, i, first_base_idx
                    )

                    # Skip if BOS not met
                    if type_ == 'DEMAND' and not demand_bos:
                        continue
                    if type_ == 'SUPPLY' and not supply_bos:
                        continue

                # HTF Location Filter Check
                if use_htf_location:
                    from src.indicators.htf_location import calculate_zone_position_in_htf_range, check_zone_location_filter

                    zone_mid = (max(proximal, distal) + min(proximal, distal)) / 2
                    zone_position = calculate_zone_position_in_htf_range(
                        zone_mid, htf_df, times[i],
                        lookback=strategy_config.get('htf_lookback', 100)
                    )

                    if not check_zone_location_filter(
                        type_, zone_position,
                        demand_max_position=strategy_config.get('demand_max_position', 0.35),
                        supply_min_position=strategy_config.get('supply_min_position', 0.65)
                    ):
                        continue

                # All filters passed - add zone
                z = Zone(type_, first_base_idx, last_base_idx,
                         top=max(proximal, distal) if type_=='SUPPLY' else proximal,
                         bottom=min(proximal, distal) if type_=='DEMAND' else distal,
                         creation_time=times[i])
                zones.append(z)

    return zones

