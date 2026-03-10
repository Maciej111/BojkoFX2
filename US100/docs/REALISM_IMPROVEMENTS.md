# Backtest Realism Improvements — Suggestions (not yet implemented)

Author: GitHub Copilot critical-review follow-up  
Date: 2025  
Status: **Suggestions only — no code changes**

---

## Context

The current backtest (`run_trend_backtest` in `src/strategies/trend_following_v1.py` and
`ExecutionEngine` in `src/backtest/execution.py`) assumes:

- Entry fills exactly at the limit price with zero slippage.  
- The spread is a fixed bid/ask constant throughout the day.  
- Commission is charged per-order at a flat dollar rate (now fixed to scale with lots,
  but still a single flat number).  
- Intrabar position management uses the bar's high/low to determine SL/TP fills
  without simulating the within-bar path.

These assumptions produce optimistic results that overstate live performance.
The following improvements are ordered by estimated impact.

---

## M1 — Slippage Model (High Impact)

### Problem
Limit entries are assumed to fill at *exactly* the limit price.  
In live trading (especially on indices) limits frequently fill worse because:
- the bid/ask has already moved past the limit when the bar closes, or
- queue position means partial fills at worse levels.

### Suggested fix

Add a `slippage_model` parameter to `run_trend_backtest` and `ExecutionEngine`:

```python
# params_dict additions
slippage_model:   "none" | "fixed" | "atr_fraction"
slippage_fixed:   float   # e.g. 0.5 pip if model == "fixed"
slippage_atr_pct: float   # e.g. 0.05 (5% of ATR) if model == "atr_fraction"
```

For **limit entries** (BOS pullback):
```
fill_price = limit_price + slippage * side_sign
```
where `side_sign = +1` for LONG (pay more on the ask) and `-1` for SHORT.

For **SL exits** (stop orders filled at worst-case):
```
fill_price = sl_price - slippage * side_sign
```

This means LONG SLs fill *below* `sl_price` and SHORT SLs fill *above*, which is
closer to live behaviour for thin markets or fast moves.

### Why not Wilder ATR (M1 from critical review)?
The slippage model is more impactful than the ATR formula choice because it
directly changes realized PnL on every trade.  Wilder vs. rolling-mean ATR
changes position sizing and SL distances by < 2% on average.

---

## M2 — Variable Spread / Time-of-Day Filter (Medium Impact)

### Problem
The backtest uses a single constant spread for all bars.  
In practice the spread on FX and indices widens significantly:
- During overnight/Asian session on EUR pairs (+2–5× normal).  
- Around economic releases (NFP, CPI) — can spike 10–20× for seconds.
- At the London open for crosses.

Because entries and exits use different (bid/ask) sides, using a flat spread
underestimates cost during wide-spread windows.

### Suggested fix

Add a `spread_schedule` dict to the backtest config:

```python
spread_schedule = {
    "default":         0.00010,   # 1 pip
    "asian_session":   0.00020,   # 2× during 22:00–07:00 UTC
    "around_release":  0.00050,   # 5× for a 15-minute window around known events
}
```

At each bar, look up the spread for that timestamp and apply it to `_ask = _bid + spread`.

A simpler starting point: just use the *actual* stored `close_ask - close_bid` from the
Dukascopy tick data (it is already downloaded — `high_ask - high_bid` etc. exist per bar).
The columns are present in the data but currently ignored for spread calculation.

---

## M3 — Intrabar Execution Order (Medium Impact)

### Problem
When both SL and TP are hit within the same bar, the backtest always chooses the SL
(worst-case conflict resolution).  This is conservative but not realistic.

More critically: the order in which price hits SL vs. TP within a bar is unknown
from OHLC data.  Current behaviour assumes `high` is always hit before `low` on a
long trade (wrong ~50% of the time).

### Suggested fix

Add an `intrabar_model` parameter:

```python
intrabar_model: "worst_case" | "random" | "first_touch"
```

- `"worst_case"` (current) — always SL wins on conflict.  
- `"random"` — when both hit, flip a coin (seeded RNG for reproducibility).  
- `"first_touch"` — use tick data (if available) to determine which level was
  reached first.

For the `"random"` model, a 50/50 coin flip on the conflict bars changes the
expectancy of a 2R system from roughly +0R (if all conflicts SL) toward
`0.5 × (+2R) + 0.5 × (−1R) = +0.5R` per conflict — a meaningful difference
if many bars hit both levels.

Flag the conflict trades with `exit_reason = "SL_intrabar_conflict"` (already done)
so they can be analysed separately.

---

## M4 — Commission Model (Low Impact — partially fixed)

### Current state
Bug C5 was fixed: commission now scales as `commission_per_lot × (lot_size / 100_000)`.

### Remaining gap
On **index CFDs** (NAS100, SPX, DAX) the market convention is commission *per unit*
(contract size = 1), not per 100,000-unit FX lot.  Using the FX formula for indices
makes commission effectively zero: `$7 × (1 / 100_000) ≈ $0.000007` per trade.

### Suggested fix

Add a `commission_model` key to the backtest config:

```python
commission_model:  "per_lot_fx" | "per_unit" | "flat"
commission_value:  float   # meaning depends on model
```

- `"per_lot_fx"` (current after fix) — `comm = value × lot_size / 100_000`.  
- `"per_unit"` — `comm = value × units` (e.g. $0.005 per NAS100 unit).  
- `"flat"` — fixed dollar amount per trade, independent of size.

---

## M5 — Overnight / Weekend Gap Risk (Low Impact)

### Problem
The backtest processes each H1 bar independently.  If a position is open over the
weekend (Friday close → Monday open gap), the SL price becomes irrelevant because
the open gap can be far through it.  Currently, the bar loop would fill the SL at
`sl_price` even if Monday's open was 20 pips beyond it.

### Suggested fix

Add a gap-fill check at position update time:

```python
# Check for overnight/weekend gap fill
if current_bar['open_bid'] <= position['sl']  and direction == 'LONG':
    exit_price  = current_bar['open_bid']   # gap fill — worse than stop
    exit_reason = 'SL_gap'
elif current_bar['open_bid'] >= position['sl'] and direction == 'SHORT':
    exit_price  = current_bar['open_bid']
    exit_reason = 'SL_gap'
```

This correctly fills the stop at the open price (worst-case gap fill) rather than the
original SL price, reducing the optimism bias for gap-sensitive strategies.

---

## Priority Order for Implementation

| Priority | Improvement | Reason |
|----------|-------------|--------|
| 1 | **Slippage model** | Directly impacts every PnL calculation; biggest source of live/backtest divergence |
| 2 | **Variable spread** | Already have the data (ask/bid columns in Dukascopy feeds) |
| 3 | **Intrabar order** | Affects P/L on conflict bars; random model is 5 lines of code |
| 4 | **Index commission** | Needed before going live on NAS100/SPX — zero cost now is misleading |
| 5 | **Gap risk** | Low frequency but can blow a trade — important for overnight holds |
