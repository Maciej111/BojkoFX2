# Quantitative Strategy Audit — BOS + Pullback

**Date:** 2026-03-08  
**Scope:** `src/strategies/trend_following_v1.py`, `src/core/strategy.py`, `src/structure/pivots.py`, `src/structure/bias.py`, `src/backtest/setup_tracker.py`  
**Backtest data:** FX OOS 2023-2024 (4 symbols, H1/H4, 879 trades)  
**Verdict summary:** Edge exists but is fragile, highly concentrated in outliers, regime-dependent, and has several structural biases that inflate backtest results relative to live performance.

---

## 1. BOS Detection Validity

### How it works

BOS fires when `current_close > last_confirmed_pivot_high` (LONG) or `current_close < last_confirmed_pivot_low` (SHORT). The pivot used is the last *confirmed* pivot before current bar.

### The confirmation delay chain

With the default `pivot_lookback_ltf=3` and `confirmation_bars=1` on H1:

```
Pivot forms at bar T
  └─ needs bars T+1, T+2, T+3 to be lower (symmetric window, lookback=3)
  └─ raw pivot detectable at T+3 (earliest bar after the window is complete)
  └─ confirmed pivot fires at T+3+1 = T+4 (confirmation_bars=1)
  └─ BOS detectable from T+5 onward (get_last_confirmed_pivot searches strictly BEFORE current bar)
```

**Result:** a minimum of 5 H1 bars (5 hours) pass between the actual swing high forming and the moment BOS can be detected. In practice, BOS fires on the bar where close exceeds the pivot level, which may be 10–20+ bars after the pivot — the impulse move has already happened.

### Impact on R:R

By the time BOS fires, price has already moved from the pivot level to the BOS bar close. That distance — let's call it the "impulse gap" — is **between 0.5R and 2R of the eventual trade's risk**, meaning the actual remaining reward potential is lower than the theoretical RR. Example:

- Pivot high at 1.0800
- BOS fires at close 1.0850 (50 pips above pivot)
- Entry at 1.0850 + 0.3×ATR — further above pivot
- SL at 1.0720 (last confirmed pivot low) — risk = 1.30 ATR
- TP at 2× risk above entry

The "free move from BOS to entry" of 50+ pips represents wasted structure. This systematically pushes entry further into the move and compresses achievable reward. The backtest captures this correctly (it uses the same impulse), but the psychological and execution implication is that the strategy regularly enters *after* the obvious move.

### Late-entry bias

On the H1 chart with default parameters, the strategy enters no earlier than 5 hours after the structure break, often 10–15 hours. This is structurally a "chasing" system, not a "breakout" system. The distinction matters because:
- In true trends, the late entry still works because the trend continues
- In failed breakouts (80%+ of BOS events in ranging markets), the late entry amplifies losses — entry is far from structure, SL is wide, and the fake-out reversal is already underway

---

## 2. Pivot Logic Quality

### Lookback and density

On H1 with `lookback=3`: a valid swing high at bar T must be the highest bar in a 7-bar window (T±3). On major FX pairs trending 24/5, this produces approximately **5–8 LTF pivots per week**, which is reasonable but may miss micro-structure.

On H4 HTF with `lookback=5`: an 11-bar symmetric window = ±22 hours. This produces approximately **4–6 HTF pivots per month**, giving sparse structure. With `pivot_count=4` in `get_pivot_sequence`, the bias calculation looks only at the last 4 pivots — covering potentially only the past 3–4 weeks on H4.

### Residual lookahead in vectorized backtest

`detect_pivots_confirmed` loops `for i in range(lookback, n - lookback)`, requiring both past AND future bars within `lookback` distance. With `confirmation_bars=1`, confirmed signals fire 1 bar after raw detection — but raw detection required `lookback=3` future bars. The confirmation delay is **2 bars short** of fully eliminating lookahead:

| Parameter combo | Real anti-lookahead requires | Actual delay | Hidden lookahead |
|-----------------|------------------------------|--------------|-----------------|
| lookback=3, confirmation_bars=1 | 3 bars | 1 bar | **2 bars** |
| lookback=3, confirmation_bars=3 | 3 bars | 3 bars | 0 bars |

In the **vectorized backtest**, pivots are pre-computed on the *full* dataset. At bar i, `get_last_confirmed_pivot(ltf_df, ..., current_time)` correctly filters to confirmed pivots before current_time. But those pivots were detected using future bars — specifically, a pivot confirmed at bar i+1 was raw-detected using bars i+1, i+2, i+3 (all future at bar i). This is live-discoverable only through confirmation delay, but in a scenario where bars i+2 or i+3 contain a spike, the pivot assignment could differ from what a true bar-by-bar system would produce.

In the **live bar-by-bar strategy** (`strategy.py` slicing `ltf_window` up to current bar), this issue is self-correcting: the loop only sees the window up to current bar, so future bars are never available. The anti-lookahead is correct in the live implementation.

**Implication:** Backtest and live strategy may assign different pivots in edge cases, leading to occasional BOS/SL level divergence.

### Symmetry assumption

The strategy assumes swing highs and lows have clear separation. With `lookback=3`, adjacent pivot highs can be as close as 3 bars apart if both qualify in their respective windows. In fast-moving markets (post-news), multiple consecutive pivots form rapidly and the "last pivot" changes every few bars, creating noisy BOS signals.

---

## 3. Pullback Entry Logic

### Entry placement

```python
# LONG:
entry_price = bos_level + entry_offset_atr_mult * atr   # above BOS level

# SHORT:
entry_price = bos_level - entry_offset_atr_mult * atr   # below BOS level
```

With default `entry_offset_atr_mult=0.3`: the entry is placed **0.3 ATR beyond (through) the BOS level**, not below it. This is a **retest entry**, not a pullback:

- A LONG limit order above BOS level fills when price returns to slightly above where it broke out. This is directionally correct — you want price to "test" the broken resistance from above.
- However, the fill condition `low_ask <= entry_price <= high_ask` means the entry fills whenever price enters the range. If on the BOS bar itself `high_ask > entry_price` (i.e., the breakout bar extended sufficiently), the entry fills **on the same bar as BOS detection** — there is no pullback. The trade is entered as a momentum entry disguised as a pullback.

### BOS-bar immediate fill risk

This is systematically underestimated. Given the H1 bars are built from 1-minute ticks, the `high_ask` of the BOS bar can easily be 0.3–0.5 ATR above the close (large-range bars on news). The fill condition is satisfied immediately, giving zero pullback. In these cases the entry captures all of the impulse bar's range — which the backtest counts as a "filled pullback" but is actually a chase at the top of the move.

**Realistic fix:** The fill condition should additionally require that the BOS bar has already closed before the entry can be checked. This is approximately the case since BOS fires on close, and the entry is checked from the *next* bar onward. Verifying whether `SetupTracker.check_fill` is skipping the BOS bar itself would be prudent.

Looking at the code: `SetupTracker.create_setup` is called at bar i (BOS bar), and `check_fill` is called from bar i+1 onward (because the setup check comes before BOS detection in the loop). This appears correct — the BOS bar itself cannot fill its own entry. However, bar i+1 can immediately satisfy the fill if the very next bar touches the entry zone.

### `pullback_max_bars` expiry gate

Default is 20–40 bars. This means entries can occur up to 40 hours (on H1) after BOS. By that point, the market may have moved significantly, making the entry at an outdated price zone irrelevant. In ranging markets, old BOS levels get re-tested but in the wrong direction (false breakout retest). The expiry gate does not screen for this scenario.

---

## 4. Stop Loss Placement

### Mechanism

```python
# LONG SL:
sl_level = get_last_confirmed_pivot_low(ltf_df, ..., fill_time)   # last confirmed swing low
sl_price = sl_level - sl_buffer_atr_mult * atr                    # 0.5 ATR below
```

### Variable risk distance

The SL distance is fully dependent on how far the last confirmed pivot low is. There is no cap. In practice:

- In a clean trend: last pivot low is 3–5 H1 bars behind, ~0.5–1.0 ATR below entry → tight stop, good R:R
- In a slow grinding move: last pivot low is 15–25 bars behind, 2–4 ATR below entry → wide stop, trade needs to go far to reach 1.5R TP
- After a volatility spike: ATR inflated, buffer = 0.5 × inflated ATR → stop pushed even further away

The backtest uses ~100–120 trades per symbol per year, and wins ~48% of them. But the distribution of actual risk distances likely has a heavy right tail. A few trades with 3–4 ATR risk (wide SL) and missed TP could disproportionately affect expectancy.

### SL calculation timing divergence: backtest vs live

**This is a structural difference between backtest and live:**

- **Backtest:** SL is computed at `fill_time` (the bar where the pullback entry fills). Between BOS and fill (0–40 bars), new pivot lows may have formed closer to the current price. SL uses the freshest available pivot.
- **Live strategy (`strategy.py`):** SL is calculated at `BOS detection time` when the `OrderIntent` is created. The OrderIntent is submitted to IBKR immediately. If fill happens 10 bars later, the SL in the live trade is anchored to a 10-bar-old pivot low — possibly further away than what the backtest would use.

This creates a **systematic live-vs-backtest SL divergence**. In extreme cases, if a new pivot low forms close to entry level between BOS and fill, the backtest uses the tighter SL (better R:R) but the live system uses the original wider SL. The live strategy would have inferior R:R on every such trade.

---

## 5. ATR Interaction

### ATR formula

The strategy uses `tr.rolling(window=14).mean()` — a simple 14-period rolling average of True Range. This has two known behaviours:

1. **Volatility spikes inflate ATR for 14 bars.** A single high-impact news bar (e.g. NFP, CPI) with a 3× normal range inflates ATR over the next 14 hours. During this window:
   - Entry offset = 0.3 × inflated ATR → entry placed further from BOS
   - SL buffer = 0.5 × inflated ATR → SL pushed further away
   - Net effect: inflated ATR expands both entry and SL, increasing position size uncertainty

2. **ATR shrinks during consolidation.** In tight ranges, ATR shrinks over 14 bars. An eventual breakout occurs with compressed ATR:
   - SL buffer = 0.5 × tiny ATR → SL uncomfortably close to entry
   - Entry inside the consolidation zone
   - First reversal after BOS hits SL before the trend develops

### Entry–SL compounding

Both `entry_offset` and `sl_buffer` scale with the same ATR. This means:
- In high-volatility regimes → both entry and SL move outward proportionally; risk distance partially preserved
- In low-volatility consolidations → entry and SL both compress; SL becomes unrealistically tight
- At volatility-regime transitions: entry computed with fresh (expanded) ATR, SL computed with same ATR. If a news spike caused the BOS itself, the "inflated ATR" makes SL wider than the actual structure requires.

### Practical consequence

Trades entered after news events likely have disproportionately wide stops (inflated ATR). These trades have lower probability of reaching a 1.5R TP simply because the absolute price distance is larger. Wins on these trades would be large in R terms, but frequent small losses accumulate. This is consistent with the observed outlier concentration: the few large winners (likely post-news resumption trades) drive the entire edge.

---

## 6. Risk-Reward Logic

### Fixed RR on variable structure

With `risk_reward=1.5` (frozen config) and a win rate of ~48%, the system needs expectancy ≥ `0.48 × 1.5 - 0.52 × 1.0 = 0.72 - 0.52 = +0.20R` per trade to break even. Observed: +0.178R to +0.572R. This is tight — EURUSD at +0.212R has a PF of 1.03, which means virtually no margin for execution slippage.

### TP achievability by structure

TP is placed at `entry + rr × risk_distance`. In a strong trend after confirmed BOS + pullback, 1.5× the risk distance is typically achievable. However:

- TP does not account for intermediate structure (next HTF or LTF pivot high that might act as resistance)
- In ranging markets: the "bull bias" can be active while the pair is actually stuck in a range. TP of 1.5R above entry may be above a confluence of resistance levels.
- The strategy does not adapt TP. Once set, it stays fixed. If a strong resistance zone is between entry and TP, the trade hits resistance, reverses, and takes SL — even though a trailing stop or partial TP would have banked profit.

### Outlier dependency: the critical finding

From `docs/validation/PROOF_V2_EXECUTIVE_SUMMARY.md`:

| Symbol | Total R (234–220 trades) | Top 5 Trades R | Concentration |
|--------|--------------------------|----------------|---------------|
| EURUSD | 49.5R | 60.9R | **123%** |
| GBPUSD | 114.4R | 118.5R | **103%** |
| USDJPY | 67.4R | 52.1R | **77%** |
| XAUUSD | 39.1R | 35.3R | **90%** |

**EURUSD's top 5 trades EXCEED the total R** — the remaining 229 trades are net zero or negative. **GBPUSD is the same.** This is not a diversified edge; it is a system that loses on most trades and relies on capturing rare outlier trending moves to be profitable overall.

In live trading, those 5 outlier trades may:
- Be missed due to IBKR connectivity issues
- Be exited early by trailing stop (if enabled) when the move is half-complete
- Have different SL/TP due to the live vs backtest timing divergence described above
- Occur during high-spread periods where slippage erodes the R multiple

The viability of the strategy in live trading depends entirely on whether these ~2–3 outlier trades per year per symbol are captured reliably.

---

## 7. Structural Market Assumptions

### Core assumption: breakouts continue

The strategy assumes that when LTF price closes above a confirmed pivot high (with aligned HTF bias), the move will continue far enough (1.5R) for TP to be reached. This is a **momentum continuation** assumption, which requires:

1. The HTF trend is genuinely strong and persistent
2. The LTF BOS is a real trend continuation, not a false breakout
3. No major resistance levels lie between entry and TP

### When it works

- Trending years with clear directional bias (GBPUSD 2024: +1.126R expectancy — a strongly trending year)
- Symbols with persistent momentum (USDJPY 2023-2024: consistent both years)
- Post-consolidation breakouts where ATR is moderate

### When it fails

- **Ranging markets:** HTF pivots form at similar levels, `determine_htf_bias` flips between BULL/BEAR/NEUTRAL rapidly. Each flip generates a new BOS signal in the new direction, immediately after the previous direction's trade SL hits. This creates a whipsaw pattern where the strategy systematically buys highs and sells lows in ranges.
- **Trend exhaustion:** Late in a trend, HTF bias may still be BULL (last HH/HL intact) while LTF is forming a distribution top. BOS signals fire on what appear to be continuation breakouts but are actually late-trend overextension entries.
- **News-driven spikes:** The BOS fires after a news spike but by then the move is complete and a reversion begins. Entry fills on the pullback, but it's a reversal, not a retest.
- **GBPUSD 2023 (+0.029R vs 2024 +1.126R):** A 40× difference between calendar years in the same symbol with zero parameter changes indicates **extreme regime dependence**. 2023 was choppier; 2024 had sustained trends.

### Directional bias concerns

From the audit data, across all symbols:
- GBPUSD 2024: Short Exp = +2.118R, Long Exp = +0.266R — **8× asymmetry**
- USDJPY 2023: Long Exp = +0.715R, Short Exp = −0.200R — **longs profit, shorts lose**
- XAUUSD 2023: Long = −0.195R (losing), Short = +0.414R
- XAUUSD 2024: Long = +0.436R, Short = −0.103R (complete reversal)

The strategy's long/short performance is **not symmetric and reverses by year**. This is consistent with regime-following behaviour, but it means the system will reliably underperform whenever the dominant regime switches mid-year — a predictable failure mode.

---

## 8. Trade Timing Bias

### Entry delay estimation

Minimum delay from structure break to possible entry:
- Pivot forms at bar T
- Apparent at bar T+confirmation_bars = T+1 (visible in confirmed series)
- But truly confirmed when lookback bars have passed after pivot: T+lookback = T+3
- BOS detectable from T+4 (strict `< current_time` in `get_last_confirmed_pivot`)
- BOS fires at bar T+4 or later (when close exceeds pivot high)
- Setup created at T+4; fill on bar T+5 earliest

On H1, this is **minimum 5 hours** after the swing high formed. Expected value (averaging pullback fill time): based on `avg_bars_to_fill` tracked in `SetupTracker`, which is not available in the audit reports. However, `pullback_max_bars=40` means fills up to 40 bars after BOS — up to **45 hours (nearly 2 trading days)** after the structure break.

### The timing paradox

The strategy is designed as "BOS + pullback" — which implies:
1. Structure breaks (BOS) — capture the momentum
2. Price pulls back to retest — enter on retest
3. Continue the trend — profit

However, steps 1 and 2 take up to 45 hours on H1. By that time:
- The initial momentum move is over
- Price has returned to the BOS zone (the pullback has happened)
- The **secondary impulse** is what the strategy hopes to capture

This transforms the strategy from a "fast BOS momentum" approach into a **"delayed structure confirmation followed by pullback fade"** system. The outlier trades may actually be cases where price never properly pulled back — the entry filled immediately on a strong continuation, not a retest — which then ran hard. The strategy might be accidentally better as a momentum entry than as a pullback entry.

---

## 9. Parameter Sensitivity

### Most sensitive parameters

**`pivot_lookback_ltf` (default: 3)**  
This is the most sensitive parameter. It directly controls:
- How many BOS signals are generated (smaller lookback = more pivots = more BOS)
- How far the SL anchor pivot is (smaller lookback = closer pivot = tighter stop)
- Whether the strategy is in "scalp" or "swing" mode

Going from lookback=2 to lookback=5 would halve the number of signals and double the average SL distance. This parameter was likely the primary axis of the grid search optimization.

**`risk_reward` (default: 1.5)**  
Directly determines breakeven win rate (1/(1+RR)). With WR ≈ 48%, RR=1.5 gives expectancy ≈ +0.2R. At RR=2.0 with same WR, expectancy ≈ +0.44R but fewer trades reach TP — absolute number of wins shrinks. The parameter was tuned on H1 FX data; its optimality for other instruments or timeframes is untested.

**`pullback_max_bars` (default: 20–40)**  
Controls what percentage of setups fill vs expire. Longer expiry:
- Higher fill rate (more trades)
- But late-filled trades are stale and may perform worse
- Creates a selection bias problem: you can improve backtest win rate by extending expiry (catching more of the "good" pullbacks) but this also includes stale entries

A `pullback_max_bars=40` means some entries happen 40 bars after BOS. At bar 40, the market has likely formed a new structure that invalidates the original BOS context. This parameter likely has a J-shaped performance curve: too small → miss real pullbacks; too large → include noise trades. The optimum is in-sample-period specific.

**`confirmation_bars` (default: 1)**  
Already discussed above. For lookback=3, a value of 1 is insufficient for true anti-lookahead. Increasing to 3 would be more conservative but delay signals further.

### Overfitting risk

The strategy was developed and validated on 4 FX majors + gold over 2021–2024. This is a relatively short history with a specific macro regime (post-COVID recovery, high inflation cycle, rate-hike cycle). Parameters optimized for this period may not generalize to:
- Low-volatility environments (2017-type markets)
- Sustained bear markets with no clear HTF structure
- Different instruments (indices, commodities) with different tick dynamics

The gap between GBPUSD 2023 (+0.029R) and 2024 (+1.126R) is a warning sign. A parameter set that makes 2023 work better will likely make 2024 worse. The frozen config may represent an in-sample local optimum rather than a robust parameter set.

---

## 10. Hidden Strategy Biases

### 1. Outlier concentration (critical)

Already quantified above. The strategy's entire edge is in ~2–5 trades per year per symbol. This is not a law-of-large-numbers edge — it is a **regime capture** strategy. In a bad regime year, expectancy may be −0.2R to −0.5R (all outlier trades missed or stopped early). This is unacceptable for a mechanical strategy without a regime filter.

### 2. `last_high_broken` bias condition

In `determine_htf_bias`:
```python
last_high_broken = last_close > highs[0][1] if highs else False
if (highs_ascending and lows_ascending) or last_high_broken:
    return 'BULL'
```
The `last_high_broken` condition fires BULL bias whenever the current HTF close is above the most recent confirmed HTF pivot high — **regardless of lower structure.** This condition can fire during a trend reversal:

- Market was trending up: HH/HL structure
- Price starts reversing: forms LL, LH
- But then bounces once above the last HTF pivot high

In this scenario: `highs_ascending` may be False (descending highs), `lows_ascending` may be False (descending lows), but `last_high_broken` fires BULL — the system would generate LONG signals into a reversal. The `last_high_broken` override should require at minimum that the last pivot low also holds (i.e., no lower low was formed below it).

### 3. Stop clustering

All LONG SLs are placed at `last_confirmed_pivot_low - buffer`. When multiple independent BOS strategies (or traders) use similar lookback parameters, SLs cluster at the same price levels — the confirmed pivot lows. This creates stop-hunting zones where brief dips to the pivot low levels sweep stops before the trend continues. The strategy is particularly vulnerable to this in liquid markets where market makers know where retail swing lows are placed.

### 4. Single active setup limitation

`SetupTracker` allows only one active setup at a time. When a new BOS fires before the previous setup fills, the old setup is silently expired. In trending markets with multiple BOS events in sequence (common), the system may skip 2–3 valid setups before entering. The "missed" setups are often the best ones — those where price extended immediately without pulling back. This creates a **selection bias toward late, deep pullbacks** which tend to be against the trend.

### 5. Volatility clustering

High ATR periods generate: (a) wider SL (b) more frequent BOS (pivots are less distinct in choppy volatility). Clusters of volatility generate clusters of BOS signals all with wide stops. If these trades overlap (single active setup prevents this in backtest, but live has no gap between intent creation and position management), position sizing risk accumulates.

### 6. `determine_htf_bias` checks only 2 consecutive pivots

```python
highs_ascending = all(highs[i][1] > highs[i+1][1] for i in range(min(2, len(highs)-1)))
```
This checks only the last 2 pivot highs. Two consecutive HH is sufficient for BULL bias — a minimal structural requirement that can be satisfied after a single rebound from a downtrend. The bias can flip falsely on a 2-bar HTF sequence.

---

## 11. Statistical Red Flags

### 1. EURUSD PF = 1.03

A profit factor of 1.03 over 234 OOS trades means for every $1 lost, $1.03 is won — a 3% margin. After a single pip of additional slippage per trade (realistic), this drops below 1.0. **EURUSD should be considered marginal, not validated.**

### 2. Year-over-year instability

| Symbol | 2023 | 2024 | Ratio |
|--------|------|------|-------|
| GBPUSD | +0.029R | +1.126R | **39×** |
| XAUUSD L | −0.195R | +0.436R | sign flip |
| USDJPY S | −0.200R | +0.069R | sign flip |

Expectancy swings of this magnitude are inconsistent with a "robust statistical edge." A robust edge should hold to within ±50% across years. 39× variation is regime dependency, not edge stability.

### 3. The early multi-symbol bug

`docs/validation/MULTISYMBOL_ROBUSTNESS_REPORT.md` shows all 4 symbols with *identical* results (184 trades, 48.37% WR, 0.1059R for every symbol). This was a data loading bug where all 4 symbols ran on the same dataset. The fact that this report was approved and labeled "ROBUST" before being discovered suggests insufficient validation discipline. It was later caught, but any results generated in the same period should be treated with suspicion.

### 4. Trade count profile

100–120 trades per year per symbol on H1 is sustainable for statistical significance (200+ trades per year for OOS validation is marginal). With 234 OOS trades (2 years) for EURUSD, the confidence interval on +0.212R expectancy is approximately ±0.13R at the 95% level — meaning the true expectancy could be as low as +0.08R. Statistically this edge is not firmly established for EURUSD.

### 5. Returns reported using unrealistic sizing

The "return" percentages in reports use `pnl = (exit_price - entry_price) × 100,000` (FX standard multiplier) with flat balance, not position-size-adjusted 1% risk sizing. The `docs/validation/FULL_SYSTEM_AUDIT_REPORT.md` corrects this for some reports, but earlier reports (MULTISYMBOL, etc.) do not. Comparison across different documents requires care.

---

## 12. Suggested Strategy Improvements

### S1 — Regime filter (highest priority)

Add an explicit regime volatility gate based on ADX or rolling trend strength. Only take BOS trades when the market is in a trending regime (ADX > 20 on HTF, or H4 ATR:range ratio > threshold). Reject all signals in low-ADX environments. This would likely cut trade count by 30–40% but eliminate many of the losing whipsaw trades that currently define 2023-style performance.

### S2 — Fix `last_high_broken` condition in bias

Remove the override condition entirely, or qualify it:
```python
# Current (problematic):
if (highs_ascending and lows_ascending) or last_high_broken:
    return 'BULL'

# Better:
if highs_ascending and lows_ascending:
    return 'BULL'
# last_high_broken alone is insufficient — structure must be intact
```

### S3 — Partial TP to reduce outlier dependency

Split each trade into:
- 50% closes at 1.0R (lock in profit, reduce outlier dependency)
- 50% trails to 2.0R or beyond (preserve the outlier captures)

This changes expectancy distribution from "all or nothing at 1.5R" to "consistent partial wins + occasional large wins." The strategic goal is to reduce the top-5-trades concentration from 90–123% of total down to 50–60%.

### S4 — Synchronize SL calculation to fill time in live strategy

`process_bar` currently computes SL at BOS time. Between BOS and pullback fill (potentially 20–40 bars), new pivot lows may form. The live `IBKRExecutionEngine` should recalculate the SL level at entry fill time using the freshest pivot — matching the backtest behaviour. This requires either: (a) storing the BOS context and recalculating at fill, or (b) accepting the SL drift and considering it a conservative (wider) stop.

### S5 — Scale `confirmation_bars` to match `lookback`

Set `confirmation_bars = lookback = 3` for true anti-lookahead in both backtest and live. The current `confirmation_bars=1` with `lookback=3` leaves 2 bars of implicit lookahead in the vectorized pivot pre-computation. This trades signal speed (1 bar delay vs 3) for reliability — confirmed pivots are truly confirmed.

### S6 — Add intermediate structure check for TP

Before placing a LONG order, check whether any confirmed LTF or HTF pivot high lies within the TP zone. If TP is within 0.5 ATR of a known resistance pivot, reduce TP to just below resistance (partial close) or skip the trade. This would improve TP hit rate in structured markets.

### S7 — BOS quality filter

Not all BOS events are equal. Add a minimum impulse quality filter:
- Only fire BOS if the breaking bar has range > N×ATR (confirming momentum)
- Only fire BOS if volume (or tick count from Dukascopy) is above 20-period average
- Reject BOS events that occur within 2 bars of a session open (spread spike risk)

### S8 — Yearly stability as live monitoring signal

Given the extreme year-over-year instability, implement a drawdown-based regime switch:
- If trailing 60-trade expectancy drops below 0.0R, pause trading for the symbol
- Resume when 20-trade rolling expectancy recovers to +0.1R

This is not curve-fitting — it is a circuit breaker for regime failure, which is clearly a risk given GBPUSD 2023 behaviour.

---

## Summary of Key Risk Areas

| Risk | Severity | Impact on live |
|------|----------|----------------|
| Outlier concentration (top 5 = 90–123% of total R) | **Critical** | Missing 1–2 outlier trades turns profitable year to losing year |
| EURUSD PF = 1.03 — effectively zero margin | **Critical** | Any execution friction makes it a losing strategy |
| 39× year-over-year expectancy swing (GBPUSD) | **High** | Regime switch causes extended drawdowns with no warning |
| `last_high_broken` override fires during reversals | **High** | Generates counter-trend signals at trend exhaustion |
| SL calculated at BOS time in live vs fill time in backtest | **High** | Systematic live underperformance on R:R |
| ATR inflation after news events widens stops post-spike | **Medium** | Reduces trade quality on highest-momentum setups |
| `confirmation_bars=1` with `lookback=3` — 2-bar hidden lookahead in backtest | **Medium** | Backtest slightly optimistic; live may have marginally lower hit rate |
| `pullback_max_bars=40` allows stale entries | **Medium** | Reduces win rate on late-filled trades |
| Single active setup skips secondary BOS signals | **Low** | May miss best entries; likely net neutral |
| Stop clustering near confirmed pivot lows | **Low** | External manipulation risk in liquid markets |
