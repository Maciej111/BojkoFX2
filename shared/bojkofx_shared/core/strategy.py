"""
Core strategy logic - generates OrderIntent from bars
Pure function - no I/O, no state, deterministic
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Tuple
from datetime import datetime
import uuid

from .models import Bar, OrderIntent, Side, OrderType
from .config import StrategyConfig

# State store — optional, injected at runtime
try:
    from .state_store import (
        SQLiteStateStore, StrategyState, BosInfo, PivotInfo,
        DBOrderRecord, OrderStatus, make_intent_id,
    )
    _STORE_AVAILABLE = True
except ImportError:
    _STORE_AVAILABLE = False


class TrendFollowingStrategy:
    """
    BOS + Pullback strategy (frozen from PROOF V2)
    Generates OrderIntent from bar series
    """

    def __init__(self, config: StrategyConfig, store=None):
        self.config = config
        self.active_setups = {}  # signal_id -> setup data
        self._store = store      # Optional[SQLiteStateStore]

    def process_bar(
        self,
        ltf_bars: pd.DataFrame,  # H1 bars with DatetimeIndex
        htf_bars: pd.DataFrame,  # H4 bars with DatetimeIndex
        current_bar_idx: int
    ) -> List[OrderIntent]:
        """
        Process new bar and generate order intents

        Args:
            ltf_bars: H1 bars (columns: open/high/low/close bid/ask)
            htf_bars: H4 bars (same structure)
            current_bar_idx: index of current bar in ltf_bars

        Returns:
            List of OrderIntent objects
        """
        intents = []

        if current_bar_idx < 200:  # Need history for indicators
            return intents

        # Extract bar window for analysis
        lookback = 200
        start_idx = max(0, current_bar_idx - lookback)
        ltf_window = ltf_bars.iloc[start_idx:current_bar_idx+1].copy()

        # Calculate ATR (on close_bid for simplicity)
        ltf_window['tr'] = self._calculate_tr(ltf_window)
        ltf_window['atr'] = ltf_window['tr'].rolling(14).mean()

        current_bar = ltf_window.iloc[-1]
        current_time = ltf_window.index[-1]

        if pd.isna(current_bar['atr']) or current_bar['atr'] <= 0:
            return intents

        # Detect pivots
        pivots = self._detect_pivots(ltf_window, self.config.pivot_lookback_ltf)

        # Check for BOS (Break of Structure)
        bos_signal = self._check_bos(ltf_window, pivots, current_bar_idx - start_idx)

        if bos_signal:
            side, bos_level = bos_signal

            # Bar timestamp used as idempotency key component
            bos_bar_ts = current_time.isoformat() if hasattr(current_time, "isoformat") \
                         else str(current_time)

            # ── Idempotency: skip if identical intent already in DB ────────────
            if self._store and _STORE_AVAILABLE:
                _intent_id = make_intent_id(
                    "UNKNOWN",   # symbol filled by runner
                    side.value, bos_level, bos_bar_ts
                )
                existing = self._store.get_order_by_intent_id(_intent_id)
                if existing is not None:
                    # Already created / sent — do not re-generate
                    return intents

            # Create setup for pullback entry
            signal_id = f"{current_time.isoformat()}_{side.value}_{uuid.uuid4().hex[:8]}"

            # Calculate entry level (pullback to BOS level + offset)
            atr = current_bar['atr']

            if side == Side.LONG:
                entry_price = bos_level + (self.config.entry_offset_atr_mult * atr)
                sl_price = self._calculate_sl(ltf_window, pivots, side, entry_price, atr)
                tp_price = entry_price + (self.config.risk_reward * abs(entry_price - sl_price))
            else:
                entry_price = bos_level - (self.config.entry_offset_atr_mult * atr)
                sl_price = self._calculate_sl(ltf_window, pivots, side, entry_price, atr)
                tp_price = entry_price - (self.config.risk_reward * abs(entry_price - sl_price))

            # Create OrderIntent
            intent = OrderIntent(
                signal_id=signal_id,
                timestamp=current_time,
                symbol="UNKNOWN",  # Will be set by runner
                side=side,
                entry_type=OrderType.LIMIT,
                entry_price=entry_price,
                sl_price=sl_price,
                tp_price=tp_price,
                ttl_bars=self.config.pullback_max_bars,
                risk_R=1.0,
                metadata={
                    'bos_level': bos_level,
                    'bos_bar_ts': bos_bar_ts,
                    'atr': atr,
                    'reason': 'BOS_PULLBACK'
                }
            )

            intents.append(intent)
            self.active_setups[signal_id] = {
                'created_at': current_bar_idx,
                'expires_at': current_bar_idx + self.config.pullback_max_bars
            }

            # ── Persist strategy state + CREATED order record ─────────────────
            if self._store and _STORE_AVAILABLE:
                # Update strategy state with latest pivot/BOS info
                ph = pivots['highs'][-1] if pivots['highs'] else None
                pl = pivots['lows'][-1]  if pivots['lows']  else None
                state = StrategyState(
                    symbol=intent.symbol,   # will be "UNKNOWN" until runner patches it
                    last_processed_bar_ts=bos_bar_ts,
                    last_pivot_high=PivotInfo(
                        price=float(ph[1]),
                        bar_ts=str(ltf_window.index[ph[0]].isoformat()),
                        idx=int(ph[0]),
                    ) if ph else None,
                    last_pivot_low=PivotInfo(
                        price=float(pl[1]),
                        bar_ts=str(ltf_window.index[pl[0]].isoformat()),
                        idx=int(pl[0]),
                    ) if pl else None,
                    last_bos=BosInfo(
                        direction=side.value,
                        level=float(bos_level),
                        bar_ts=bos_bar_ts,
                    ),
                )
                self._store.save_strategy_state(state)
                self._store.append_event("INTENT_CREATED", {
                    "signal_id": signal_id,
                    "side": side.value,
                    "bos_level": float(bos_level),
                    "bos_bar_ts": bos_bar_ts,
                    "entry_price": float(entry_price),
                    "sl_price": float(sl_price),
                    "tp_price": float(tp_price),
                })

        # Clean expired setups
        self._clean_expired_setups(current_bar_idx)

        return intents

    def _calculate_tr(self, df: pd.DataFrame) -> pd.Series:
        """Calculate True Range"""
        high = df['high_bid']
        low = df['low_bid']
        close_prev = df['close_bid'].shift(1)

        tr1 = high - low
        tr2 = abs(high - close_prev)
        tr3 = abs(low - close_prev)

        return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    def _detect_pivots(
        self,
        df: pd.DataFrame,
        lookback: int
    ) -> dict:
        """
        Detect swing highs and lows
        Returns dict with 'highs' and 'lows' as lists of (idx, price)
        """
        highs = []
        lows = []

        high_col = df['high_bid'].values
        low_col = df['low_bid'].values

        for i in range(lookback, len(df) - lookback):
            # Pivot high
            if all(high_col[i] >= high_col[i-lookback:i]) and \
               all(high_col[i] >= high_col[i+1:i+lookback+1]):
                highs.append((i, high_col[i]))

            # Pivot low
            if all(low_col[i] <= low_col[i-lookback:i]) and \
               all(low_col[i] <= low_col[i+1:i+lookback+1]):
                lows.append((i, low_col[i]))

        return {'highs': highs, 'lows': lows}

    def _check_bos(
        self,
        df: pd.DataFrame,
        pivots: dict,
        current_idx: int
    ) -> Optional[Tuple[Side, float]]:
        """
        Check for Break of Structure
        Returns (Side, bos_level) or None
        """
        if current_idx < 10:
            return None

        current_close = df.iloc[current_idx]['close_bid']

        # Bull BOS: close above last pivot high
        if pivots['highs']:
            last_high_idx, last_high_price = pivots['highs'][-1]
            if last_high_idx < current_idx - 2:  # Must be confirmed
                if current_close > last_high_price:
                    return (Side.LONG, last_high_price)

        # Bear BOS: close below last pivot low
        if pivots['lows']:
            last_low_idx, last_low_price = pivots['lows'][-1]
            if last_low_idx < current_idx - 2:
                if current_close < last_low_price:
                    return (Side.SHORT, last_low_price)

        return None

    def _calculate_sl(
        self,
        df: pd.DataFrame,
        pivots: dict,
        side: Side,
        entry_price: float,
        atr: float
    ) -> float:
        """Calculate stop loss based on pivot and buffer"""
        buffer = self.config.sl_buffer_atr_mult * atr

        if side == Side.LONG:
            # SL below last pivot low
            if pivots['lows']:
                last_low_price = pivots['lows'][-1][1]
                sl = last_low_price - buffer
            else:
                sl = entry_price - (2 * atr)
        else:
            # SL above last pivot high
            if pivots['highs']:
                last_high_price = pivots['highs'][-1][1]
                sl = last_high_price + buffer
            else:
                sl = entry_price + (2 * atr)

        return sl

    def _clean_expired_setups(self, current_bar_idx: int):
        """Remove expired setups"""
        expired = [
            sid for sid, setup in self.active_setups.items()
            if current_bar_idx > setup['expires_at']
        ]

        for sid in expired:
            del self.active_setups[sid]

