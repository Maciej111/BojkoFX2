"""
US100 Regime Filter — trzy niezależne kandydaty (A, B, C).

Wszystkie no-lookahead: wskaźniki liczone na całej historii HTF, ale przy sprawdzeniu
na barze i używamy wyłącznie HTF barów z timestamp <= ltf_df.index[i].

Kandydat A: ADX(14) na HTF > regime_adx_threshold
    - Progi do testowania: [15, 20, 25, 30]
    - ADX niezależny od kierunku — blokuje rynki boczne

Kandydat B: ATR(14)/ATR(100) na HTF > regime_atr_ratio_threshold
    - Progi do testowania: [0.8, 1.0, 1.2, 1.5]
    - Ratio > 1.0 = krótkoterminowa zmienność wyższa od długoterminowej = rynek "żywy"

Kandydat C: EMA(50) slope na HTF, kierunkowy (BULL → EMA rośnie, BEAR → EMA spada)
    - Lookback barów H4 do testowania: [2, 3, 5]
    - Wymaga podania htf_bias (BULL/BEAR) w wywołaniu is_trending_regime()

Użycie w run_trend_backtest():
    # Przed pętlą:
    if params_dict.get('use_regime_filter', False):
        params_dict['_regime_data'] = precompute_regime(htf_df, params_dict)

    # Wewnątrz pętli, po if htf_bias == 'NEUTRAL': continue:
    if params_dict.get('use_regime_filter', False):
        if not is_trending_regime(ltf_df, htf_df, i, params_dict, htf_bias=htf_bias):
            continue
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Wewnętrzne helpery — liczymy na pełnym df HTF (no-lookahead w pętli przez pos)
# ---------------------------------------------------------------------------

def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (EWM alpha=1/period, identyczny z calculate_atr w shared)."""
    return series.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def _compute_atr_series(htf_df: pd.DataFrame, period: int) -> pd.Series:
    """ATR Wildera na HTF (używa kolumn high_bid/low_bid/close_bid)."""
    hi = htf_df['high_bid']
    lo = htf_df['low_bid']
    cl = htf_df['close_bid']
    prev_cl = cl.shift(1)
    tr = pd.concat([
        hi - lo,
        (hi - prev_cl).abs(),
        (lo - prev_cl).abs(),
    ], axis=1).max(axis=1)
    return _wilder_smooth(tr, period)


def _compute_adx_series(htf_df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ADX Wildera na HTF (Wilder smoothing, tożsamy z compute_adx_series w FX module).
    Używa kolumn high_bid / low_bid / close_bid.
    """
    hi = htf_df['high_bid']
    lo = htf_df['low_bid']

    up_move = hi - hi.shift(1)
    dn_move = lo.shift(1) - lo

    plus_dm_arr = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
    minus_dm_arr = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)

    plus_dm = pd.Series(plus_dm_arr, index=htf_df.index)
    minus_dm = pd.Series(minus_dm_arr, index=htf_df.index)

    atr = _compute_atr_series(htf_df, period)

    plus_di = 100.0 * _wilder_smooth(plus_dm, period) / atr
    minus_di = 100.0 * _wilder_smooth(minus_dm, period) / atr

    dx = (
        100.0
        * (plus_di - minus_di).abs()
        / (plus_di + minus_di).replace(0, np.nan)
    ).fillna(0.0)

    return _wilder_smooth(dx, period)


def _compute_ema_series(series: pd.Series, period: int) -> pd.Series:
    """EMA standardowa (span=period, adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Precompute — wywołać RAZ przed pętlą backtestu
# ---------------------------------------------------------------------------

def precompute_regime(htf_df: pd.DataFrame, config: dict) -> dict:
    """
    Przelicza wszystkie wskaźniki reżimu na pełnym HTF df.
    Wynik przechowywać w config['_regime_data'] przed wejściem w pętlę.

    config keys używane tutaj:
        regime_adx_period         (int, default 14)
        regime_atr_short_period   (int, default 14)
        regime_atr_long_period    (int, default 100)
        regime_ema_period         (int, default 50)
    """
    adx_period = config.get('regime_adx_period', 14)
    atr_short_p = config.get('regime_atr_short_period', 14)
    atr_long_p = config.get('regime_atr_long_period', 100)
    ema_period = config.get('regime_ema_period', 50)

    adx = _compute_adx_series(htf_df, adx_period)
    atr_short = _compute_atr_series(htf_df, atr_short_p)
    atr_long = _compute_atr_series(htf_df, atr_long_p)
    atr_ratio = atr_short / atr_long.replace(0, np.nan)
    ema = _compute_ema_series(htf_df['close_bid'], ema_period)

    return {
        'htf_index': htf_df.index,
        'adx': adx,
        'atr_ratio': atr_ratio,
        'ema': ema,
    }


# ---------------------------------------------------------------------------
# Funkcja główna — wywoływana per-bar w pętli backtestu
# ---------------------------------------------------------------------------

def is_trending_regime(
    ltf_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    bar_idx: int,
    config: dict,
    htf_bias: str = None,
) -> bool:
    """
    No-lookahead sprawdzenie czy US100 jest w reżimie trendującym.

    Parametry:
        ltf_df    — LTF DataFrame (index = DatetimeIndex UTC)
        htf_df    — HTF DataFrame (używany tylko gdy _regime_data nie w config)
        bar_idx   — indeks bieżącego baru LTF
        config    — params_dict strategii (musi zawierać '_regime_data')
        htf_bias  — 'BULL' / 'BEAR' / None (wymagany dla metody C)

    config keys:
        regime_method              'A' | 'B' | 'C'  (default 'A')
        regime_adx_threshold       float (default 20.0) — dla metody A
        regime_atr_ratio_threshold float (default 1.0)  — dla metody B
        regime_ema_lookback        int   (default 3)    — dla metody C (bary H4)
        _regime_data               dict  z precompute_regime() — WYMAGANE przed pętlą

    Zwraca True jeśli rynek jest w stanie trendującym (sygnał może przejść).
    Zwraca False jeśli rynek jest boczny/niesprecyzowany (blokuj sygnał).
    """
    regime_data = config.get('_regime_data')
    if regime_data is None:
        # Lazy init (wolne — tylko dla celów debugowania unit-testów)
        regime_data = precompute_regime(htf_df, config)
        config['_regime_data'] = regime_data

    # Znajdź ostatni HTF bar z timestamp <= bieżący LTF bar (no-lookahead)
    ltf_ts = ltf_df.index[bar_idx]
    htf_index = regime_data['htf_index']
    pos = htf_index.searchsorted(ltf_ts, side='right') - 1

    if pos < 1:
        # Za mało historii HTF — blokuj ostrożnie
        return False

    method = config.get('regime_method', 'A')

    # ------------------------------------------------------------------
    # Kandydat A: ADX > próg (direction-agnostic)
    # ------------------------------------------------------------------
    if method == 'A':
        adx_val = regime_data['adx'].iloc[pos]
        threshold = config.get('regime_adx_threshold', 20.0)
        if pd.isna(adx_val):
            return False
        return bool(adx_val >= threshold)

    # ------------------------------------------------------------------
    # Kandydat B: ATR(14)/ATR(100) > próg (direction-agnostic)
    # ------------------------------------------------------------------
    elif method == 'B':
        ratio_val = regime_data['atr_ratio'].iloc[pos]
        threshold = config.get('regime_atr_ratio_threshold', 1.0)
        if pd.isna(ratio_val):
            return False
        return bool(ratio_val >= threshold)

    # ------------------------------------------------------------------
    # Kandydat C: EMA(50) slope aligned z kierunkiem bias (direction-aware)
    # ------------------------------------------------------------------
    elif method == 'C':
        ema_lookback = config.get('regime_ema_lookback', 3)
        if pos < ema_lookback:
            return False
        ema_now = regime_data['ema'].iloc[pos]
        ema_prev = regime_data['ema'].iloc[pos - ema_lookback]
        if pd.isna(ema_now) or pd.isna(ema_prev):
            return False
        if htf_bias == 'BULL':
            return bool(ema_now > ema_prev)
        elif htf_bias == 'BEAR':
            return bool(ema_now < ema_prev)
        else:
            # Bez bias → sprawdź czy slope istnieje w dowolnym kierunku
            return bool(ema_now != ema_prev)

    # Nieznana metoda → nie blokuj (backward-compatible)
    return True
