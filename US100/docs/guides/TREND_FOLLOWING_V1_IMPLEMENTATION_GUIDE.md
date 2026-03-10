# TREND FOLLOWING V1 - IMPLEMENTATION GUIDE

**Date:** 2026-02-18  
**Branch:** trend_following_v1  
**Strategy:** Trend-Following with BOS + Pullback Entry

---

## 🎯 OBJECTIVE

Implementacja nowej strategii trend-following na osobnym branchu:
- HTF Bias (H4) - określa kierunek trendu
- BOS Detection (H1) - wykrywa break of structure
- Pullback Entry - czeka na cofnięcie po BOS
- Proper bid/ask execution
- Anti-lookahead compliance

**Stara strategia reversal pozostaje nietknięta!**

---

## 📁 FILES ALREADY CREATED

### ✅ 1. `src/structure/pivots.py`
```python
# Pivot detection z potwierdzeniem (anti-lookahead)
detect_pivots_confirmed(df, lookback=3, confirmation_bars=1)
get_last_confirmed_pivot(df, pivot_series, pivot_level_series, current_idx)
get_pivot_sequence(df, ..., count=4)
```

### ✅ 2. `src/structure/bias.py`
```python
# HTF Bias determination
determine_htf_bias(pivot_sequence, last_close)
get_htf_bias_at_bar(htf_df, current_bar_time, ...)
```

### ⏳ 3. `src/backtest/setup_tracker.py` (NEEDS TO BE CREATED)

```python
"""Setup Tracker - BOS to Pullback Entry"""
import pandas as pd
from dataclasses import dataclass
from typing import Optional

@dataclass
class PullbackSetup:
    direction: str  # 'LONG' or 'SHORT'
    bos_level: float
    bos_time: pd.Timestamp
    entry_price: float
    expiry_time: pd.Timestamp
    expiry_bar_count: int
    htf_bias: str
    ltf_pivot_type: str
    is_filled: bool = False
    is_expired: bool = False
    fill_time: Optional[pd.Timestamp] = None
    bars_to_fill: Optional[int] = None

class SetupTracker:
    def __init__(self):
        self.active_setup = None
        self.missed_setups = []
        self.filled_setups = []
    
    def has_active_setup(self):
        return self.active_setup is not None and not self.active_setup.is_filled and not self.active_setup.is_expired
    
    def create_setup(self, direction, bos_level, bos_time, entry_price, 
                     expiry_time, expiry_bar_count, htf_bias, ltf_pivot_type):
        if self.active_setup and not self.active_setup.is_filled:
            self.active_setup.is_expired = True
            self.missed_setups.append(self.active_setup)
        self.active_setup = PullbackSetup(
            direction, bos_level, bos_time, entry_price, 
            expiry_time, expiry_bar_count, htf_bias, ltf_pivot_type
        )
    
    def check_fill(self, current_bar, current_time):
        if not self.has_active_setup():
            return False
        setup = self.active_setup
        if current_time >= setup.expiry_time:
            setup.is_expired = True
            self.missed_setups.append(setup)
            self.active_setup = None
            return False
        filled = False
        if setup.direction == 'LONG':
            if current_bar['low_ask'] <= setup.entry_price <= current_bar['high_ask']:
                filled = True
        elif setup.direction == 'SHORT':
            if current_bar['low_bid'] <= setup.entry_price <= current_bar['high_bid']:
                filled = True
        if filled:
            setup.is_filled = True
            setup.fill_time = current_time
            self.filled_setups.append(setup)
            return True
        return False
    
    def get_active_setup(self):
        return self.active_setup if self.has_active_setup() else None
    
    def clear_active_setup(self):
        self.active_setup = None
    
    def get_stats(self):
        total = len(self.filled_setups) + len(self.missed_setups)
        if total == 0:
            return {
                'total_setups': 0, 'filled_setups': 0, 'missed_setups': 0, 
                'missed_rate': 0.0, 'avg_bars_to_fill': 0.0
            }
        bars_list = [s.bars_to_fill for s in self.filled_setups if s.bars_to_fill is not None]
        avg_bars = sum(bars_list) / len(bars_list) if bars_list else 0.0
        return {
            'total_setups': total,
            'filled_setups': len(self.filled_setups),
            'missed_setups': len(self.missed_setups),
            'missed_rate': len(self.missed_setups) / total if total > 0 else 0.0,
            'avg_bars_to_fill': avg_bars
        }
```

---

## 📋 REMAINING FILES TO CREATE

### 4. `src/strategies/trend_following_v1.py`

**Main strategy logic:**

```python
"""
Trend Following Strategy v1
BOS + Pullback Entry with HTF Bias
"""
import pandas as pd
import numpy as np
from src.structure.pivots import detect_pivots_confirmed, get_last_confirmed_pivot, get_pivot_sequence
from src.structure.bias import get_htf_bias_at_bar
from src.backtest.setup_tracker import SetupTracker
from src.backtest.execution import ExecutionEngine

def run_trend_following_backtest(ltf_df, htf_df, config, initial_balance=10000):
    """
    Main backtest loop for trend following strategy.
    
    Args:
        ltf_df: H1 bars DataFrame
        htf_df: H4 bars DataFrame  
        config: Config dict
        initial_balance: Starting capital
        
    Returns:
        trades_df: DataFrame with all trades
    """
    
    # Extract config
    ltf_lookback = config['trend_strategy']['pivot_lookback_ltf']
    htf_lookback = config['trend_strategy']['pivot_lookback_htf']
    confirmation_bars = config['trend_strategy']['confirmation_bars']
    require_close_break = config['trend_strategy']['require_close_break']
    entry_offset_atr = config['trend_strategy']['entry_offset_atr_mult']
    pullback_max_bars = config['trend_strategy']['pullback_max_bars']
    sl_anchor = config['trend_strategy']['sl_anchor']
    sl_buffer_atr = config['trend_strategy']['sl_buffer_atr_mult']
    rr = config['trend_strategy']['risk_reward']
    
    # Calculate ATR
    ltf_df['atr'] = calculate_atr(ltf_df, period=14)
    
    # Detect pivots on LTF (H1)
    ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels = detect_pivots_confirmed(
        ltf_df, lookback=ltf_lookback, confirmation_bars=confirmation_bars
    )
    
    # Detect pivots on HTF (H4)
    htf_pivot_highs, htf_pivot_lows, htf_ph_levels, htf_pl_levels = detect_pivots_confirmed(
        htf_df, lookback=htf_lookback, confirmation_bars=confirmation_bars
    )
    
    # Initialize
    engine = ExecutionEngine(initial_balance, config['execution'])
    tracker = SetupTracker()
    
    trades = []
    bar_count = 0
    
    # Main loop through LTF bars
    for i in range(len(ltf_df)):
        current_time = ltf_df.index[i]
        current_bar = ltf_df.iloc[i]
        bar_count += 1
        
        # Update existing positions
        engine.update(current_bar, current_time)
        
        # Check setup fill (if active setup exists)
        if tracker.has_active_setup():
            if tracker.check_fill(current_bar, current_time):
                setup = tracker.get_active_setup()
                
                # Calculate bars to fill
                bos_bar_idx = ltf_df.index.get_loc(setup.bos_time)
                fill_bar_idx = i
                setup.bars_to_fill = fill_bar_idx - bos_bar_idx
                
                # Enter trade
                enter_trade_from_setup(setup, current_bar, current_time, ltf_df, 
                                      ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels,
                                      config, engine)
                
                tracker.clear_active_setup()
        
        # Skip if position open or setup active
        if engine.has_open_position() or tracker.has_active_setup():
            continue
        
        # Get HTF bias
        htf_bias = get_htf_bias_at_bar(
            htf_df, current_time, 
            htf_pivot_highs, htf_pivot_lows, htf_ph_levels, htf_pl_levels,
            pivot_count=4
        )
        
        if htf_bias == 'NEUTRAL':
            continue
        
        # Check for BOS
        bos_detected, bos_direction, bos_level = check_bos(
            ltf_df, i, ltf_pivot_highs, ltf_pivot_lows, ltf_ph_levels, ltf_pl_levels,
            require_close_break
        )
        
        if not bos_detected:
            continue
        
        # BOS must align with HTF bias
        if (bos_direction == 'LONG' and htf_bias != 'BULL') or \
           (bos_direction == 'SHORT' and htf_bias != 'BEAR'):
            continue
        
        # Create pullback setup
        atr = current_bar['atr']
        
        if bos_direction == 'LONG':
            entry_price = bos_level + (entry_offset_atr * atr)
        else:
            entry_price = bos_level - (entry_offset_atr * atr)
        
        expiry_time = ltf_df.index[min(i + pullback_max_bars, len(ltf_df)-1)]
        
        tracker.create_setup(
            direction=bos_direction,
            bos_level=bos_level,
            bos_time=current_time,
            entry_price=entry_price,
            expiry_time=expiry_time,
            expiry_bar_count=pullback_max_bars,
            htf_bias=htf_bias,
            ltf_pivot_type='pivot_high' if bos_direction == 'LONG' else 'pivot_low'
        )
    
    # Collect trades
    trades = engine.get_closed_trades()
    
    # Add setup stats
    setup_stats = tracker.get_stats()
    
    return pd.DataFrame(trades), setup_stats


def check_bos(df, current_idx, pivot_highs, pivot_lows, ph_levels, pl_levels, require_close_break):
    """
    Check if BOS occurred at current bar.
    
    Returns:
        (detected: bool, direction: str, level: float)
    """
    
    current_close = df['close_bid'].iloc[current_idx]
    
    # Bull BOS: close above last pivot high
    last_ph_time, last_ph_level = get_last_confirmed_pivot(df, pivot_highs, ph_levels, df.index[current_idx])
    
    if last_ph_level is not None:
        if require_close_break:
            if current_close > last_ph_level:
                return True, 'LONG', last_ph_level
        else:
            if df['high_bid'].iloc[current_idx] > last_ph_level:
                return True, 'LONG', last_ph_level
    
    # Bear BOS: close below last pivot low
    last_pl_time, last_pl_level = get_last_confirmed_pivot(df, pivot_lows, pl_levels, df.index[current_idx])
    
    if last_pl_level is not None:
        if require_close_break:
            if current_close < last_pl_level:
                return True, 'SHORT', last_pl_level
        else:
            if df['low_bid'].iloc[current_idx] < last_pl_level:
                return True, 'SHORT', last_pl_level
    
    return False, None, None


def enter_trade_from_setup(setup, current_bar, current_time, df, pivot_highs, pivot_lows, ph_levels, pl_levels, config, engine):
    """Enter trade based on filled setup."""
    
    sl_anchor = config['trend_strategy']['sl_anchor']
    sl_buffer_atr = config['trend_strategy']['sl_buffer_atr_mult']
    rr = config['trend_strategy']['risk_reward']
    
    atr = current_bar['atr']
    entry = setup.entry_price
    
    # Calculate SL
    current_idx = df.index.get_loc(current_time)
    
    if setup.direction == 'LONG':
        if sl_anchor == 'last_pivot':
            sl_time, sl_level = get_last_confirmed_pivot(df, pivot_lows, pl_levels, current_time)
        else:  # pre_bos_pivot
            sl_level = setup.bos_level  # Simplified
        
        sl = sl_level - (sl_buffer_atr * atr) if sl_level else entry - (2 * atr)
        risk = entry - sl
        tp = entry + (risk * rr)
        
        engine.place_market_order('LONG', entry, sl, tp, current_time, comment='Trend Long')
    
    else:  # SHORT
        if sl_anchor == 'last_pivot':
            sl_time, sl_level = get_last_confirmed_pivot(df, pivot_highs, ph_levels, current_time)
        else:
            sl_level = setup.bos_level
        
        sl = sl_level + (sl_buffer_atr * atr) if sl_level else entry + (2 * atr)
        risk = sl - entry
        tp = entry - (risk * rr)
        
        engine.place_market_order('SHORT', entry, sl, tp, current_time, comment='Trend Short')


def calculate_atr(df, period=14):
    """Calculate ATR."""
    high = df['high_bid']
    low = df['low_bid']
    close = df['close_bid']
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr
```

---

### 5. `scripts/run_backtest_trend.py`

```python
"""
Run Trend Following v1 Backtest
"""
import sys
import os
import argparse
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.config import load_config
from src.strategies.trend_following_v1 import run_trend_following_backtest
from src.backtest.metrics import compute_metrics, add_R_column
from src.reporting.report import generate_backtest_report

def main():
    parser = argparse.ArgumentParser(description='Run Trend Following Backtest')
    parser.add_argument('--symbol', type=str, default='EURUSD')
    parser.add_argument('--ltf', type=str, default='H1')
    parser.add_argument('--htf', type=str, default='H4')
    parser.add_argument('--start', type=str, default='2021-01-01')
    parser.add_argument('--end', type=str, default='2024-12-31')
    parser.add_argument('--config', type=str, default='config/config.yaml')
    
    args = parser.parse_args()
    
    print(f"\\n{'='*60}")
    print("TREND FOLLOWING V1 BACKTEST")
    print(f"{'='*60}\\n")
    print(f"Symbol: {args.symbol}")
    print(f"LTF: {args.ltf}, HTF: {args.htf}")
    print(f"Period: {args.start} to {args.end}\\n")
    
    # Load config
    config = load_config(args.config)
    initial_balance = config['execution']['initial_balance']
    
    # Load LTF bars (H1)
    ltf_file = f"data/bars/{args.symbol.lower()}_h1_bars.csv"
    if not os.path.exists(ltf_file):
        print(f"✗ LTF bars not found: {ltf_file}")
        return
    
    ltf_df = pd.read_csv(ltf_file, index_col='timestamp', parse_dates=True)
    ltf_df = ltf_df[(ltf_df.index >= args.start) & (ltf_df.index <= args.end)]
    print(f"✓ Loaded {len(ltf_df)} LTF (H1) bars")
    
    # Build HTF bars (H4) from LTF
    htf_df = ltf_df.resample('4H').agg({
        'open_bid': 'first', 'high_bid': 'max', 'low_bid': 'min', 'close_bid': 'last',
        'open_ask': 'first', 'high_ask': 'max', 'low_ask': 'min', 'close_ask': 'last'
    }).dropna()
    print(f"✓ Built {len(htf_df)} HTF (H4) bars\\n")
    
    # Run backtest
    trades_df, setup_stats = run_trend_following_backtest(ltf_df, htf_df, config, initial_balance)
    
    print(f"\\n✓ Backtest Complete:")
    print(f"  Trades: {len(trades_df)}")
    print(f"  Setups Created: {setup_stats['total_setups']}")
    print(f"  Missed Setups: {setup_stats['missed_setups']} ({setup_stats['missed_rate']*100:.1f}%)")
    print(f"  Avg Bars to Fill: {setup_stats['avg_bars_to_fill']:.1f}")
    
    # Calculate metrics
    if len(trades_df) > 0:
        trades_df = add_R_column(trades_df)
        metrics = compute_metrics(trades_df, initial_balance)
        
        print(f"  Win Rate: {metrics['win_rate']:.2f}%")
        print(f"  Expectancy: {metrics['expectancy_R']:.3f}R")
        print(f"  Return: {((initial_balance + metrics['total_pnl']) / initial_balance - 1) * 100:.2f}%")
        
        # Save outputs
        output_file = f"data/outputs/trades_trend_{args.symbol}_{args.ltf}_{args.start}_{args.end}.csv"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        trades_df.to_csv(output_file, index=False)
        print(f"\\n✓ Saved: {output_file}")
        
        # Generate report
        generate_backtest_report(
            trades_df, metrics, initial_balance,
            f"reports/summary_trend_{args.symbol}_{args.ltf}.md",
            f"reports/equity_trend_{args.symbol}_{args.ltf}.png",
            f"reports/r_hist_trend_{args.symbol}_{args.ltf}.png"
        )
        print(f"✓ Reports generated in reports/")
    else:
        print("\\n⚠ No trades generated")

if __name__ == "__main__":
    main()
```

---

### 6. `config/config.yaml` - ADD SECTION

```yaml
# Trend Following Strategy v1
trend_strategy:
  pivot_lookback_ltf: 3       # LTF (H1) pivot lookback
  pivot_lookback_htf: 5       # HTF (H4) pivot lookback
  confirmation_bars: 1        # Bars to confirm pivot (anti-lookahead)
  require_close_break: true   # Require close break for BOS
  entry_offset_atr_mult: 0.3  # Entry offset from BOS level (in ATR)
  pullback_max_bars: 20       # Max bars to wait for pullback
  sl_anchor: "last_pivot"     # "last_pivot" or "pre_bos_pivot"
  sl_buffer_atr_mult: 0.5     # SL buffer (in ATR)
  risk_reward: 2.0            # RR ratio
```

---

### 7. Tests (3 files)

**`tests/test_pivots_no_lookahead.py`:**
```python
import pytest
import pandas as pd
from src.structure.pivots import detect_pivots_confirmed

def test_pivot_confirmation_delay():
    # Create test data
    dates = pd.date_range('2024-01-01', periods=20, freq='H')
    highs = [1.1, 1.2, 1.3, 1.2, 1.1, 1.0, 1.1, 1.2, 1.1, 1.0] + [1.0]*10
    lows = [1.0, 1.1, 1.2, 1.1, 1.0, 0.9, 1.0, 1.1, 1.0, 0.9] + [0.9]*10
    
    df = pd.DataFrame({
        'high_bid': highs,
        'low_bid': lows
    }, index=dates)
    
    # Detect with confirmation=1
    ph, pl, ph_lvl, pl_lvl = detect_pivots_confirmed(df, lookback=2, confirmation_bars=1)
    
    # Pivot at bar 2 should be confirmed at bar 3
    assert ph.iloc[2] == False  # Not yet confirmed at bar 2
    assert ph.iloc[3] == True   # Confirmed at bar 3
    
    print("✓ Pivot confirmation delay works correctly")

if __name__ == "__main__":
    test_pivot_confirmation_delay()
```

**`tests/test_bos_pullback_setup.py`:**
```python
import pytest
import pandas as pd
from src.backtest.setup_tracker import SetupTracker, PullbackSetup

def test_setup_creation_and_fill():
    tracker = SetupTracker()
    
    # Create setup
    tracker.create_setup(
        direction='LONG',
        bos_level=1.1000,
        bos_time=pd.Timestamp('2024-01-01 10:00'),
        entry_price=1.1030,
        expiry_time=pd.Timestamp('2024-01-01 14:00'),
        expiry_bar_count=4,
        htf_bias='BULL',
        ltf_pivot_type='pivot_high'
    )
    
    assert tracker.has_active_setup()
    
    # Try fill
    bar = pd.Series({
        'low_ask': 1.1025,
        'high_ask': 1.1050,
        'low_bid': 1.1020,
        'high_bid': 1.1045
    })
    
    filled = tracker.check_fill(bar, pd.Timestamp('2024-01-01 11:00'))
    assert filled == True
    assert tracker.get_active_setup() is None  # Should be cleared after fill
    
    print("✓ Setup creation and fill works correctly")

if __name__ == "__main__":
    test_setup_creation_and_fill()
```

**`tests/test_missed_setup_expiry.py`:**
```python
import pytest
import pandas as pd
from src.backtest.setup_tracker import SetupTracker

def test_setup_expiry():
    tracker = SetupTracker()
    
    tracker.create_setup(
        direction='SHORT',
        bos_level=1.2000,
        bos_time=pd.Timestamp('2024-01-01 10:00'),
        entry_price=1.1970,
        expiry_time=pd.Timestamp('2024-01-01 12:00'),
        expiry_bar_count=2,
        htf_bias='BEAR',
        ltf_pivot_type='pivot_low'
    )
    
    # Check fill after expiry
    bar = pd.Series({
        'low_ask': 1.1960,
        'high_ask': 1.1990,
        'low_bid': 1.1955,
        'high_bid': 1.1985
    })
    
    filled = tracker.check_fill(bar, pd.Timestamp('2024-01-01 13:00'))  # After expiry!
    
    assert filled == False
    assert tracker.get_active_setup() is None
    assert len(tracker.missed_setups) == 1
    
    stats = tracker.get_stats()
    assert stats['missed_setups'] == 1
    assert stats['missed_rate'] == 1.0
    
    print("✓ Setup expiry works correctly")

if __name__ == "__main__":
    test_setup_expiry()
```

---

## 🚀 HOW TO IMPLEMENT

### Step 1: Create Git Branch

```bash
git checkout -b trend_following_v1
```

### Step 2: Create Directories

```bash
mkdir -p src/strategies
mkdir -p src/structure
```

### Step 3: Create Files

Copy all code from above into respective files:
1. `src/structure/pivots.py` ✅ (already created)
2. `src/structure/bias.py` ✅ (already created)
3. `src/backtest/setup_tracker.py` (create manually)
4. `src/strategies/trend_following_v1.py` (create manually)
5. `scripts/run_backtest_trend.py` (create manually)
6. Update `config/config.yaml`
7. Create 3 test files

### Step 4: Run Tests

```bash
python tests/test_pivots_no_lookahead.py
python tests/test_bos_pullback_setup.py
python tests/test_missed_setup_expiry.py
```

### Step 5: Run Backtest

```bash
python scripts/run_backtest_trend.py --symbol EURUSD --ltf H1 --htf H4 --start 2021-01-01 --end 2024-12-31
```

### Step 6: Verify Outputs

Check:
- `data/outputs/trades_trend_EURUSD_H1_2021-01-01_2024-12-31.csv`
- `reports/summary_trend_EURUSD_H1.md`
- `reports/equity_trend_EURUSD_H1.png`
- `reports/r_hist_trend_EURUSD_H1.png`

---

## ✅ DONE CRITERIA

- [ ] Branch `trend_following_v1` created
- [x] `src/structure/pivots.py` created (anti-lookahead)
- [x] `src/structure/bias.py` created (HTF bias)
- [ ] `src/backtest/setup_tracker.py` created
- [ ] `src/strategies/trend_following_v1.py` created
- [ ] `scripts/run_backtest_trend.py` created
- [ ] `config/config.yaml` updated with trend_strategy section
- [ ] 3 tests created and passing
- [ ] Backtest runs end-to-end
- [ ] Missed setups tracked and reported
- [ ] Bid/ask execution correct
- [ ] Old reversal strategy untouched

---

## 📝 SUMMARY

**Created:**
- ✅ Pivot detection with confirmation (anti-lookahead)
- ✅ HTF bias determination

**Needs Manual Creation:**
- ⏳ Setup tracker (timeout issue)
- ⏳ Main strategy logic
- ⏳ Run script
- ⏳ Config updates
- ⏳ Tests

**All code provided above - ready to copy-paste!**

---

**Implementation Date:** 2026-02-18  
**Status:** Partially Complete (2/7 files created)  
**Next:** Create remaining 5 files manually using code above

---

*"Trend following requires patience - both in trading and in implementation!"*

**Copy the code above and complete the implementation!** 🚀

