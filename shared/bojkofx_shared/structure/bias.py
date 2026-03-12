"""
HTF Bias Detection Module
Określa trend bias na wyższym timeframe (H4)
"""
import pandas as pd
import numpy as np


def determine_htf_bias(pivot_sequence, last_close):
    """
    Określa bias na podstawie sekwencji pivotów HTF.

    BULL Bias:
    - Mamy sekwencję Higher Highs i Higher Lows (min 2 każdego)
    - LUB ostatni swing high został wybity przez cenę

    BEAR Bias:
    - Mamy sekwencję Lower Lows i Lower Highs (min 2 każdego)
    - LUB ostatni swing low został wybity przez cenę

    NEUTRAL:
    - Nie można ustalić trendu

    Args:
        pivot_sequence: dict z 'highs' i 'lows' (output z get_pivot_sequence)
        last_close: obecna cena zamknięcia

    Returns:
        'BULL', 'BEAR', lub 'NEUTRAL'
    """

    highs = pivot_sequence['highs']
    lows = pivot_sequence['lows']

    # Potrzebujemy min 2 pivoty każdego typu
    if len(highs) < 2 or len(lows) < 2:
        return 'NEUTRAL'

    # Check dla BULL bias
    # 1. Higher Highs: każdy kolejny high wyższy od poprzedniego
    highs_ascending = all(highs[i][1] > highs[i+1][1] for i in range(min(2, len(highs)-1)))

    # 2. Higher Lows: każdy kolejny low wyższy od poprzedniego
    lows_ascending = all(lows[i][1] > lows[i+1][1] for i in range(min(2, len(lows)-1)))

    # FIX BUG-05: removed last_high_broken / last_low_broken conditions.
    # Those conditions created a tautology: close > last_pivot_high is exactly the
    # BOS LONG condition, so every LTF BOS automatically granted itself a BULL bias
    # on the same bar. This caused false biases in ranging markets and a live/backtest
    # mismatch (live used an in-progress H4 bar via iloc[-1]).
    # BULL now requires STRICT structural confirmation: HH + HL (ascending sequence).
    if highs_ascending and lows_ascending:
        return 'BULL'

    # Check dla BEAR bias
    # 1. Lower Lows: każdy kolejny low niższy od poprzedniego
    lows_descending = all(lows[i][1] < lows[i+1][1] for i in range(min(2, len(lows)-1)))

    # 2. Lower Highs: każdy kolejny high niższy od poprzedniego
    highs_descending = all(highs[i][1] < highs[i+1][1] for i in range(min(2, len(highs)-1)))

    # BEAR requires strict structural confirmation: LL + LH (descending sequence).
    if lows_descending and highs_descending:
        return 'BEAR'

    # Default
    return 'NEUTRAL'


def get_htf_bias_at_bar(htf_df, current_bar_time, pivot_highs, pivot_lows,
                         pivot_high_levels, pivot_low_levels, pivot_count=4):
    """
    Pobiera HTF bias na danym barze (używając tylko danych do tego momentu).

    Args:
        htf_df: DataFrame HTF (H4)
        current_bar_time: timestamp obecnego bara (H1)
        pivot_highs, pivot_lows, pivot_high_levels, pivot_low_levels: Serie pivotów HTF
        pivot_count: ile ostatnich pivotów używać

    Returns:
        'BULL', 'BEAR', lub 'NEUTRAL'
    """

    # Znajdź odpowiedni HTF bar dla current_bar_time
    # Używamy tylko barow HTF PRZED lub NA current_bar_time (anti-lookahead)
    htf_before = htf_df[htf_df.index <= current_bar_time]

    if len(htf_before) == 0:
        return 'NEUTRAL'

    latest_htf_idx = htf_before.index[-1]
    last_close = htf_before['close_bid'].iloc[-1]

    # Pobierz sekwencję pivotów
    from .pivots import get_pivot_sequence

    pivot_seq = get_pivot_sequence(
        htf_df, pivot_highs, pivot_lows, pivot_high_levels, pivot_low_levels,
        latest_htf_idx, count=pivot_count
    )

    # Określ bias
    bias = determine_htf_bias(pivot_seq, last_close)

    return bias

