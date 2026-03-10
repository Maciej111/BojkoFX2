# QUANTITATIVE STRATEGY AUDIT — BojkoFX BOS+Pullback

> **Date:** 2026-03-10  
> **Scope:** FX/src/strategies/trend_following_v1.py, FX/backtests/signals_bos_pullback.py, FX/backtests/engine.py, FX/backtests/indicators.py  
> **Data period:** Train 2021–2022, OOS 2023–2024  
> **Symbols audited:** EURUSD, USDJPY, USDCHF, AUDJPY, CADJPY

---

## 1. Strategy Logic

**Exact mechanism:**

1. **HTF Market Structure Bias** — HTF (D1 or H4) pivots are analyzed to determine directional bias (BULL / BEAR / NEUTRAL). The bias function counts the last N confirmed pivot highs and lows and assesses whether structure is making HH/HL or LL/LH. NEUTRAL bias → skip all signals.

2. **LTF BOS Detection** — On H1 (or 30m), the system checks if close breaks above the last confirmed pivot high (LONG BOS) or below the last confirmed pivot low (SHORT BOS). The pivot must be _confirmed_ — i.e., `lookback` right-side bars must have formed after the pivot candidate. With `lookback=3`, confirmation lag is **3 bars** before the pivot is even visible, plus the additional bars until the BOS fires.

3. **Pending Setup Registration** — On BOS detection, a limit order is set at `bos_level + offset_atr * ATR(14)` (LONG) or `bos_level - offset_atr * ATR(14)` (SHORT). This waits for price to _return_ to the BOS level (the pullback). TTL = 50 bars.

4. **SL Placement** — Anchored at the last confirmed pivot on the opposite side, minus `sl_buffer * ATR`. For LONG: last confirmed pivot _low_ minus buffer. For SHORT: last confirmed pivot _high_ plus buffer.

5. **TP Placement** — Fixed R:R from entry: `TP = entry + RR * (entry - SL)`. Default `RR = 3.0`.

**Classification:** Breakout-continuation with pullback entry — a micro-trend-following setup within a confirmed higher-timeframe directional context. Not mean reversion. Not pure momentum. The pullback requirement makes it partially contra-momentum at the entry bar.

**Internal consistency:** Largely consistent. HTF bias, LTF BOS, and pullback-to-break all align thematically. However there is a structural contradiction: the entry places a limit order _at the BOS level_, meaning entry fills only when price retraces all the way back to the breakout point. If the limit fill zone happens to be below the prior pivot high for a LONG, the entry is technically inside the old range, not above it.

---

## 2. Entry Timing

**BOS detection lag is material.** A pivot at bar `p` is confirmed only at bar `p + lookback`. With `lookback=3`, every BOS is visible **3 bars late** on the LTF. On H1, that is 3 hours of lag. On 30m, 90 minutes. The BOS event itself (close breaking the pivot level) adds one more bar. Total minimum lag from pivot formation to BOS signal: **4–6 bars**.

**The pullback wait adds further displacement.** After BOS detection at bar `i`, entries only fill when price returns to `bos_level ± offset`. The system waits up to TTL=50 bars (50 hours on H1). This means the entry executes _after_ the initial move has exhausted itself and price pulls back — which can be many bars after the underlying structural shift.

**Effect on R:R:** The entry at the BOS level (re-test) means entry is at a structurally meaningful level, but the distance from entry to SL is determined by the last pivot _below_ entry (for LONG). If the market moved significantly between pivot formation and BOS, the SL is far away — compressing the effective R:R dramatically.

**Estimation:** Given TTL=50 and the design logic, expect 5–20 bars between BOS and fill in typical setups. For trades that fill early (1–3 bars) the entry is on the strongest part of the pullback (good). For late fills (20+ bars), the structural context may have already changed.

**Entry quality risk:** The entry does not distinguish between a clean, fast pullback and a grinding, multi-day consolidation that eventually touches the level. Both get filled identically.

---

## 3. Risk Management

### Stop Loss

The SL anchors to the **last confirmed opposite pivot**. This creates three serious problems:

**Problem A — SL size variance.** The last pivot low on H1 might be 30 pips away (small ATR environment) or 200 pips away (post-news). The ATR buffer (`sl_buffer * ATR`) partially mitigates this, but the anchor pivot itself can be anywhere. Looking at the avg_max_R data: median trade reach is only **0.87–1.07R**, but avg_max_R is **3.0–4.2R** with p90 = 4.7–7.1R. This fat tail proves the distribution is heavily right-skewed — and that the SL distance is not consistent.

**Problem B — Pivot age.** The "last confirmed pivot low" might be 30 bars old by the time of entry. A pivot from 2 days ago is not a structurally relevant SL for today's trade. Price has already passed through that level multiple times.

**Problem C — Conservative resolution.** When both SL and TP are hit within the same bar, the engine resolves as SL ("conservative mode"). This is correct for real-world uncertainty but means the backtest penalizes any bar where price briefly touched TP before reversing. In fast-moving markets (overnight gaps on JPY pairs) this is non-trivial.

**Structural meaningfulness:** Partially. Pivot-based SL is conceptually sound — it is a prior swing low/high. But the automatic nature (no discretion on pivot relevance, no context check) means SL placement quality is inconsistent.

### Take Profit

Fixed RR (default 3.0) is appropriate for this strategy type given the fat-tailed distribution of maximum favorable excursion (avg_max_R ≈ 3.0–4.2R). However, the data reveals a fundamental problem:

**Median max excursion is only ~1R.** Over 60% of trades never reach 1.5R before reversing. The strategy is explicitly betting on the right tail (18–25% of setups reach 3R). This is mathematically viable — but fragile. A minor regime shift that reduces tail moves by 20% can turn the strategy from breakeven to chronically losing.

The actual OOS data confirms this: average expectancy across all 5 FX pairs at RR=3.0 is **-0.002R** (essentially zero). Individual pairs oscillate: EURUSD = -0.190R, USDJPY = +0.049R, AUDJPY = +0.104R. The strategy survives only because a few pairs partially offset the losers.

**Trailing stop addition:** The engine supports trailing SL (`ts_r`, `lock_r`). This improves risk management conceptually — protecting gains on large moves. However, at `ts_r=1.5` with `lock_r=0.5`, the trail activates after a 1.5R move. Given median max excursion is ~1R, the trailing stop may frequently activate on the tail of a normal move and then stop out before the trade runs to TP.

---

## 4. Market Regime Dependence

**This strategy needs clean trending conditions at both timeframes simultaneously.**

**Works well in:**
- Strong directional trends on D1/H4 (HTF bias clearly BULL or BEAR)
- Markets with regular alternating swing highs and swing lows (clear pivot structure)
- Moderate volatility — enough to create BOS events, not so much that stops are hit immediately
- Post-consolidation breakouts with clear re-tests (classical flag-and-pole patterns)

**Fails in:**
- Range/chop — HTF bias is frequently NEUTRAL, filtering most signals. When not NEUTRAL, BOS events occur in both directions repeatedly, generating false signals at the range edge
- Low volatility — BOS events are small, SL distances are tight relative to spread and commission, kills edge
- High volatility (gap-prone) — gaps through entry/SL levels create execution slippage not modeled; same-bar SL/TP conflicts increase
- Trend reversal transitions — the HTF bias lags the actual market turn (pivot confirmation takes N bars), generating BOS signals aligned with the dying trend just as it reverses

**Temporal regime dependence is visible in the data.** Training (2021–2022) was a period of strong trending moves post-COVID. OOS (2023–2024) had more chop and mean-reverting behavior on most majors. EURUSD shows a consistent -0.072R to -0.190R expectancy across most RR settings — EURUSD 2023–2024 was largely range-bound.

---

## 5. Hidden Backtest Bias

### Pivot Confirmation Bias (Medium-High severity)
Pivots are confirmed by requiring `lookback` bars after the pivot candidate. The `_precompute_pivots` function correctly stores the pivot visible at bar `i` as `ph_prices[i]` — technically correct. However, the symmetric window `[p - lookback, p + lookback]` uses future bars to classify the pivot. The pivot was "real" only in hindsight.

### BOS Level Entry Artifact (High severity for intrabar analysis)
BOS is confirmed on close. Entry is placed as a limit order expecting a pullback. The BOS bar itself is never entered — only a subsequent candle fills the entry. This is correctly modeled.

### Intrabar SL/TP Resolution (Medium severity)
Conservative same-bar mode (SL wins) underestimates performance. Optimistic mode would overstate it. Conservative is the right choice for robustness. The real answer lies between them.

### Spread Modeling (Low-Medium severity)
Spread is modeled via separate bid/ask columns from Dukascopy data. LONG entries use ASK prices (correct), exits use BID (correct). This is better than most backtests. However, Dukascopy spread data is a time-weighted average, not instantaneous. During London open, actual spreads can be 2–5× the average. Not modeled.

### Slippage (Medium severity for live trading)
Zero slippage modeled. For limit orders this is partially justified but in fast-moving markets (post-NFP, central bank meetings), limit orders at the BOS level may gap through or fill at significantly worse prices. Not modeled.

### Selection Bias in Grid Search (High severity)
144 parameter combinations were tested. The "best OOS" configuration was selected _after seeing OOS results_. Even with temporal train/test split, testing 144 combinations on the same OOS period inflates apparent OOS performance. The probability of finding a configuration with +0.35R expectancy by chance across 144 configurations with marginal true edge is non-trivial. Walk-forward with truly held-out data or Monte Carlo permutation testing is needed.

---

## 6. Statistical Stability

**Trade counts are borderline inadequate for reliable conclusions.**

For EURUSD OOS (2023–2024), the best configuration has **n=119 trades** over 2 years. The 95% confidence interval on expectancy is approximately:

$$\sigma_E \approx \frac{\text{std}(R)}{\sqrt{n}} \approx \frac{1.2}{\sqrt{119}} \approx \pm 0.11R$$

The "best" +0.3549R result has a confidence interval of +0.25R to +0.46R — consistent with borderline-passing performance. True edge could be significantly lower.

**Win rates are at the mathematical edge.** At RR=3.0, breakeven WR = 25% (1/[1+RR]). Actual live WR = 25–28%. A single bad month dropping WR to 22% produces a losing strategy.

**Key OOS numbers (RR=3.0, 2023–2024):**

| Symbol | Trades | WR | ExpR | PF | MaxDD% |
|--------|--------|----|------|----|--------|
| EURUSD | ~120 | 20% | -0.190R | <1.0 | 20.8% |
| USDJPY | ~200 | 26% | +0.049R | ~1.15 | 9.7% |
| USDCHF | ~200 | 25% | -0.010R | ~1.0 | 7.8% |
| AUDJPY | ~200 | 28% | +0.104R | ~1.3 | 11.9% |
| CADJPY | ~150 | 26% | +0.037R | ~1.1 | 12.2% |
| **Portfolio AVG** | — | — | **-0.002R** | ~1.0 | — |

**No walk-forward validation beyond a single train/test split.** Rolling quarters exist but each quarter has only 30–50 trades — insufficient for statistical inference.

---

## 7. Outlier Dependence

**The strategy explicitly depends on outliers.** This is by design — high RR (3.0) with low WR (25–28%) means the system profits only from the top fraction of trades.

**Max favorable excursion distribution (H1 BOS setups):**

| Symbol | Filled | avg_max_R | p50 | p75 | p90 | ≥3.0R |
|--------|--------|-----------|-----|-----|-----|-------|
| EURUSD | 3,719 | +3.12R | 0.92R | 2.20R | 4.74R | 18% |
| USDJPY | 3,870 | +3.63R | 1.04R | 2.58R | 5.93R | 21% |
| USDCHF | 3,821 | +2.99R | 0.98R | 2.46R | 4.80R | 20% |
| AUDJPY | 3,850 | +3.51R | 1.07R | 2.57R | 4.93R | 21% |
| CADJPY | 2,596 | +4.19R | 0.87R | 2.92R | 7.06R | 25% |

```
Rozkład ruchów (konceptualny):
 ┌────────────────────────────────────────────────────────────┐
 │ ████████████████████ 63%  ruchy kończą < 1.5R             │
 │ ███████████          19%  ruchy 1.5R – 3.0R               │
 │ ████                  7%  ruchy 3.0R – 4.0R               │
 │ ████████████         12%  (→ ∞ ogon)                      │
 └────────────────────────────────────────────────────────────┘
      ↑ p50 ≈ 1R          ↑ p75 ≈ 2.5R         ↑ avg ≈ 3.3R
```

**Removing the top 5 trades from any symbol's OOS period likely eliminates most or all of the profit.**

A 10-trade losing streak (probability: 0.75^10 ≈ 5.6%) is expected once every ~180 trades — approximately every 9 months at typical trade frequency. This is by far the most significant live-trading challenge.

---

## 8. Parameter Sensitivity

**Sensitivity analysis from the 144-configuration grid:**

| Parameter | Range tested | Impact on ExpR |
|-----------|-------------|----------------|
| RR | 1.5–2.5 | ±0.06R — **highly sensitive** |
| HTF timeframe | H4 vs D1 | +0.06R for D1 — **highly sensitive** |
| pivot_lookback | 3 only | **not tested — critical omission** |
| entry_offset | 0.0–0.3 | ±0.02R — moderate |
| sl_buffer | 0.1–0.5 | ±0.01R — low sensitivity |
| pullback_max_bars | 20–40 | ±0.02R — low sensitivity |
| TTL bars | 50 only | **not tested — critical omission** |

**HTF timeframe is the single biggest driver:** D1 HTF consistently outperforms H4 by ~0.06R. Both are tested; the choice is stable.

**Lookback parameter is not grid-searched.** Lookback=3 is the only value tested. This is a critical gap — lookback=2 or 4 could produce substantially different results.

**Overfitting risk:** The best EURUSD OOS configuration (+0.3549R) is likely partially overfitted to 2023–2024. The filter_decomposition report confirms the HTF filter alone is responsible for the entire +0.288R edge improvement. One binary parameter drives the whole strategy's validity.

---

## 9. Market Suitability

| Market | Suitability | Notes |
|--------|-------------|-------|
| FX (JPY crosses) | ✅ Best fit | USDJPY, AUDJPY, CADJPY trending well 2021–2024 |
| FX (majors) | ⚠️ Marginal | EURUSD shows negative ExpR in OOS period |
| Index (US100) | ⚠️ Low | Faster moves, gap risk, macro-driven, CFD access issues |
| Crypto | ⚠️ Recalibrate | avg_max_R ~1.5–2.5R → needs RR=1.5, not 3.0 |

---

## 10. Architecture Strengths and Weaknesses

### Strengths
- Clean separation: signal generation → simulation → metrics
- "Generate all → filter_and_adjust" for fast grid searches
- Correct no-lookahead pivot implementation in `_precompute_pivots`
- Bid/ask spread modeling (Dukascopy data) — better than most retail research
- Conservative SL resolution for same-bar conflicts

### Weaknesses
- **Two-codebase divergence:** `trend_following_v1.py` (live) and `signals_bos_pullback.py` (backtest) are different implementations of the same strategy. ADX gates and ATR filters in the backtest are **absent from live code**. Live bot is not running the backtested strategy.
- No forward test / paper trading validation period before live deployment
- Walk-forward validation uses only one train/test split
- Missing: Monte Carlo permutation test on trade sequence to establish baseline random performance

---

## 11. Critical Weaknesses (Top 5)

### #1 — Edge is at or near zero for most symbols (OOS 2023–2024)

Portfolio-average expectancy at RR=3.0 = **-0.002R**. EURUSD (the world's most liquid pair) = -0.072R to -0.190R across all RR settings. Positive results on USDJPY/AUDJPY/CADJPY may reflect yen-trend regime luck, not structural edge.

### #2 — Extreme tail dependence with no regime-detection mechanism

Median max_favorable_excursion ≈ 1R. Entire P&L comes from a handful of outlier moves to 3–7R. No adaptive mechanism detects regime shift and reduces position size or pauses trading. One choppy quarter eliminates months of accumulated edge.

### #3 — Live strategy ≠ backtested strategy (two-codebase divergence)

`trend_following_v1.py` (live) lacks ADX gates and ATR percentile filters present in `signals_bos_pullback.py` (research). If those filters generate the edge (filter decomposition: +0.288R improvement), the live bot may have near-zero expected value independent of the strategy's theoretical merit.

### #4 — Zero slippage model for limit orders at high-impact price levels

BOS levels are price magnets — they attract volume and can produce fast through-and-through moves where limit orders are either skipped or filled then immediately stopped out. Not modeled. At ExpR near 0, realistic execution costs (1–2 additional pips average per entry) may eliminate the edge entirely on tighter pairs.

### #5 — Insufficient walk-forward evidence; possible period-specific overfitting

Only one temporal split tested (2021–2022 train / 2023–2024 OOS). Training coincided with the strongest USD trend environment in 20 years. The strategy may be a disguised "strong-trend-following filter" that works only in 2021–2024 style macro regimes. No evidence of edge on 2018–2020 data.

---

## 12. Suggested Improvements (Priority Order)

### Priority 1 — Unify live and research code into shared implementation
Move all signal generation into `bojkofx_shared`. Live runner and backtest engine should call identical code for pivot detection, HTF bias, entry price calculation, and SL placement. Remove `trend_following_v1.py` and replace with `BOSPullbackSignalGenerator` backed by real-time bar data.

### Priority 2 — Implement ADX and ATR filters in live code
ADX gates on H4 (≥ 16–20) and ATR percentile filter (10–80) show consistent improvement of 0.1–0.2R in backtests. These must be implemented in live immediately. Additionally, suppress signals when ATR percentile < 20th percentile (volatility-contraction flag pattern).

### Priority 3 — Monte Carlo + extended walk-forward analysis
- Generate 10,000 permuted trade sequences to establish the null distribution of ExpR
- Run at minimum 4 non-overlapping annual OOS periods (2021, 2022, 2023, 2024) independently
- If measured ExpR doesn't clearly exceed the 90th percentile of the random distribution → acknowledge the strategy has no statistically proven edge

### Priority 4 — Replace fixed-RR with partial TP + trailing stop structure
The fat-tailed distribution argues for a two-phase exit:
1. Take 50% off at 1.0–1.5R (near the median reachable level)
2. Trail remaining position with a trailing stop activated at 1.5R

This converts the strategy from all-or-nothing (25% WR at 3R) to frequent partial wins with occasional home runs. The engine already supports `trail_cfg` — needs explicit validation.

### Priority 5 — Paper trading validation period before scaling capital
A 3-month paper trading period with live fills logged against backtest predictions would provide the first true validation of whether backtested edge survives execution in real market conditions. Currently no such data exists for either the FX or US100 bot.

---

## Final Verdict

**The strategy is conceptually sound but statistically fragile.**

The BOS + pullback + HTF filter structure is a legitimate edge concept. The code quality is above retail average — bid/ask spread modeling, conservative SL resolution, no-lookahead pivots, and separate signal/simulation layers are all implemented correctly.

However, the **measured edge is marginal**: portfolio ExpR ≈ 0 at the production RR=3.0. Performance depends critically on a small number of large outlier trades, a favorable macro regime, and specific pairs (USDJPY, AUDJPY, CADJPY) that happened to trend strongly in the test period.

The most dangerous risk is invisible: **the live strategy and the backtested strategy are not the same implementation.** The ADX gates and ATR filters that generate the edge in backtests are absent from live code. The live bot may be running a strategy with near-zero expected value right now.

The strategy is **not ready to scale capital** without completing Priority 1 (code unification) and Priority 3 (extended walk-forward). At current confidence levels, trade only with capital that can be lost entirely without material harm.

---

*Audit generated: 2026-03-10*
