# Walk-Forward Validation - Implementation Report

**Date:** 2026-02-18  
**Objective:** Out-of-sample validation for H1 + BOS + HTF H4 strategy

---

## 🎯 OBJECTIVE

Execute complete walk-forward validation for years 2021-2024 to confirm:
- **Hypothesis:** H1 + BOS + HTF H4 Location Filter is profitable
- **2024 Result:** +0.298R expectancy, +10.07% return (11 trades)
- **Question:** Is this consistent or lucky outlier?

---

## 📋 VALIDATION PROTOCOL

### Strategy Configuration (LOCKED):
```yaml
Timeframe: H1
Symbol: EURUSD
Risk/Reward: 1.5
Max Touches: 1

Filters:
  - BOS (Break of Structure)
    - pivot_lookback: 3
  
  - HTF H4 Location Filter
    - htf_period: 4h
    - htf_lookback: 100
    - demand_max_position: 0.35
    - supply_min_position: 0.65
```

**NO changes allowed** - pure out-of-sample test.

---

## 🔧 IMPLEMENTATION

### Files Created:

1. ✅ `scripts/run_walkforward_validation.py` (500+ lines)
   - Year-by-year backtest execution
   - Monte Carlo stability analysis (1000 simulations)
   - Comprehensive reporting
   - Sanity checks per year

### Features:

#### Per-Year Analysis:
- Trades count, WR, Expectancy, PF
- Max DD, Return %
- Average Win/Loss (R)
- Long vs Short expectancy
- Spread sanity check
- Look-ahead verification

#### Monte Carlo (per year):
- 1000 random permutations of trade order
- 5th/95th percentile expectancy
- 5th/95th percentile max DD
- Tests robustness to trade sequence

#### Aggregated Analysis:
- Mean/Median/Std Dev expectancy
- Best/Worst year
- Years with positive expectancy
- Years with PF > 1.0
- Long vs Short symmetry

#### Validation Criteria:
1. Expectancy > 0 in >= 3 of 4 years?
2. 4-year average expectancy > 0?
3. PF > 1 in majority of years?
4. Drawdown stable vs explosive?
5. Long and short symmetric?

**Score:** 0-4 criteria met
- **4-3:** ✅ VALIDATED
- **2:** ⚠️ MIXED
- **1-0:** ❌ NOT VALIDATED

---

## 📊 EXPECTED OUTCOMES

### Scenario A: VALIDATED (Best Case)

```
2021: 8 trades,  +0.25R,  +2.0% return
2022: 12 trades, +0.35R,  +4.2% return
2023: 10 trades, +0.20R,  +2.0% return
2024: 11 trades, +0.30R, +10.1% return

Mean: +0.275R
Positive Years: 4/4 ✅
Score: 4/4 ✅

Verdict: STRATEGY VALIDATED
```

**Interpretation:**
- Consistent positive expectancy
- Strategy works across market conditions
- **Ready for demo testing**

---

### Scenario B: PARTIALLY VALIDATED (Mixed)

```
2021: 6 trades,  -0.05R,  -0.3% return
2022: 9 trades,  +0.15R,  +1.4% return
2023: 8 trades,  +0.10R,  +0.8% return
2024: 11 trades, +0.30R, +10.1% return

Mean: +0.125R
Positive Years: 3/4 ⚠️
Score: 2-3/4 ⚠️

Verdict: MIXED RESULTS
```

**Interpretation:**
- Mostly positive but not consistent
- 2024 may be strongest year
- **Proceed with caution**
- Extended testing recommended

---

### Scenario C: NOT VALIDATED (Worst Case)

```
2021: 7 trades,  -0.20R,  -1.4% return
2022: 10 trades, -0.15R,  -1.5% return
2023: 9 trades,  +0.05R,  +0.5% return
2024: 11 trades, +0.30R, +10.1% return

Mean: 0.0R
Positive Years: 2/4 ❌
Score: 1/4 ❌

Verdict: NOT VALIDATED
```

**Interpretation:**
- 2024 is outlier (lucky year)
- Strategy not robust
- **Do NOT deploy**
- Further optimization needed

---

## 🔍 DATA AVAILABILITY

### Current Status:

**Available:**
- ✅ 2024 tick data (full year)
- ✅ 2024 H1 bars (5,067 bars)

**Missing:**
- ❌ 2021 tick data
- ❌ 2022 tick data
- ❌ 2023 tick data

### Implication:

**Walk-forward can ONLY test 2024 with current data.**

To complete full 2021-2024 validation:
1. Download tick data for 2021-2023
2. Build H1 bars for those years
3. Re-run validation script

---

## 📈 MONTE CARLO ANALYSIS

### Purpose:

Test if results are **robust** or **sequence-dependent**.

### Method:

For each year:
1. Take actual trade results (R values)
2. Randomly shuffle order 1000 times
3. Calculate expectancy & max DD for each shuffle
4. Report 5th and 95th percentiles

### Interpretation:

**Tight Range (Good):**
```
Expectancy: [+0.25R, +0.35R] (10pp range)
Max DD:     [4%, 7%] (3pp range)
```
→ ✅ Results are robust

**Wide Range (Bad):**
```
Expectancy: [-0.10R, +0.60R] (70pp range!)
Max DD:     [2%, 20%] (18pp range!)
```
→ ❌ Results are sequence-dependent (luck)

---

## 🧪 SANITY CHECKS

### Per Year Verification:

1. **Average Spread**
   - Should be ~1.3 pips (same as M15)
   - Verifies data quality

2. **Same-Bar Entry %**
   - Should be 0%
   - Verifies anti-lookahead

3. **Same-Bar SL %**
   - Expected: 20-40%
   - Due to worst-case intra-bar policy
   - Normal behavior

4. **First-Touch %**
   - Should be 100%
   - Verifies max_touches_per_zone = 1

---

## 📁 OUTPUT FILES

### Generated Reports:

```
data/outputs/
  walkforward_H1_summary.md  ← Main report

reports/
  trades_h1_wf_2021.csv
  summary_h1_wf_2021.md
  equity_curve_h1_wf_2021.png
  
  trades_h1_wf_2022.csv
  summary_h1_wf_2022.md
  equity_curve_h1_wf_2022.png
  
  trades_h1_wf_2023.csv
  summary_h1_wf_2023.md
  equity_curve_h1_wf_2023.png
  
  trades_h1_wf_2024.csv
  summary_h1_wf_2024.md
  equity_curve_h1_wf_2024.png
```

---

## 🎯 DECISION TREE

### Based on Validation Results:

```
Is Mean Expectancy > 0?
├─ YES
│  └─ Are 3+ years positive?
│     ├─ YES → ✅ DEPLOY (demo → small live → scale)
│     └─ NO  → ⚠️ EXTENDED TESTING (6-12 months demo)
│
└─ NO
   └─ Are 2+ years positive?
      ├─ YES → ⚠️ RE-OPTIMIZE (different params)
      └─ NO  → ❌ ABANDON (try different approach)
```

---

## 💡 CRITICAL INSIGHTS

### 1. Sample Size Per Year

**Expected:** ~10-15 trades/year on H1 + HTF H4

**Concern:** Small sample = high variance

**Mitigation:**
- Monte Carlo tests variance
- 4-year aggregate provides ~40-60 total trades
- Look for consistency, not perfection

### 2. H4 Range Context

**HTF H4** provides ~17 days of price context (100 bars × 4h).

**Hypothesis:** This range captures meaningful structure.

**Validation:** If consistent across years → hypothesis confirmed.

### 3. Market Regimes

Different years = different market conditions:
- **2021:** Post-COVID recovery
- **2022:** Rate hikes begin
- **2023:** Peak rates
- **2024:** Rate cut speculation

**Robust strategy** should work across these regimes.

---

## ⚠️ LIMITATIONS & CAVEATS

### 1. Data Availability

Currently only 2024 available.

**Impact:** Cannot fully validate 2021-2023.

**Action Required:** Download historical data.

### 2. Small Sample Per Year

~10-15 trades/year is statistically marginal.

**Confidence Intervals:** Wide at this sample size.

**Mitigation:** Aggregate across years.

### 3. Curve Fitting Risk

HTF H4 + location thresholds (0.35/0.65) found through testing.

**Risk:** Overfit to 2024.

**Test:** Out-of-sample years (2021-2023) are the proof.

### 4. Future Performance

**Past performance ≠ future results**

Even if validated, no guarantee of future profitability.

**Action:** Start small, monitor closely.

---

## 🚀 POST-VALIDATION ACTIONS

### If VALIDATED (Score 3-4):

1. **Demo Testing (3-6 months)**
   - Live tick feed
   - Real spreads/slippage
   - Paper trading

2. **Small Live (3-6 months)**
   - 0.1% risk per trade
   - $1,000-5,000 account
   - Monitor actual vs expected

3. **Scale Gradually**
   - Increase to 0.5% → 1% risk
   - Scale capital slowly
   - Maintain discipline

---

### If MIXED (Score 2):

1. **Extended Demo (6-12 months)**
   - Need more data
   - Watch for consistency

2. **Parameter Refinement**
   - Test 0.30/0.70 thresholds
   - Test different htf_lookback

3. **Multi-Symbol Testing**
   - Test GBPUSD, XAUUSD
   - Diversification

---

### If NOT VALIDATED (Score 0-1):

1. **Do NOT Deploy**
   - 2024 was outlier
   - Strategy not robust

2. **Alternative Approaches**
   - Test H4 base timeframe
   - Different location thresholds
   - Add volatility filter

3. **Consider Pivot**
   - Different strategy altogether
   - Mean reversion?
   - Breakout instead of S&D?

---

## 📊 STATISTICAL SIGNIFICANCE

### Rule of Thumb:

**Minimum trades for 95% confidence:** ~30 trades

**Per year:** 10-15 trades (insufficient alone)

**4-year aggregate:** 40-60 trades (acceptable)

**Conclusion:** Need multi-year data for confidence.

---

## 🎓 LESSONS FROM THIS PROCESS

### What We've Learned:

1. **Timeframe matters** - H1 > M15 for this strategy
2. **HTF ratio matters** - H4 (not H1) is right HTF for H1
3. **Location filtering powerful** - Range extremes are key
4. **BOS is foundation** - Structural confirmation essential
5. **Quality > Quantity** - 11 good trades > 121 mediocre

### What We're Testing:

**Hypothesis:** These findings generalize across years.

**Method:** Out-of-sample validation (no peeking!)

**Outcome:** Will determine next steps.

---

## 📝 USAGE

### Run Walk-Forward:

```powershell
python scripts/run_walkforward_validation.py
```

### View Report:

```powershell
cat data/outputs/walkforward_H1_summary.md
```

### If More Data Becomes Available:

1. Download tick data for 2021-2023
2. Place in `data/raw/`
3. Build H1 bars: `python scripts/build_h1_bars.py`
4. Re-run validation script

---

## ✅ IMPLEMENTATION STATUS

- [x] Walk-forward script created
- [x] Monte Carlo analysis implemented
- [x] Comprehensive reporting
- [x] Sanity checks included
- [x] Script running on available data
- [ ] Full 2021-2024 data (pending)
- [ ] Complete validation report (in progress)

---

## 🎯 NEXT STEPS

### Immediate:
1. ✅ Review walkforward report (when complete)
2. ✅ Analyze year-by-year consistency
3. ✅ Check Monte Carlo stability

### Short-Term:
- Download 2021-2023 data (if pursuing)
- Complete 4-year validation
- Make deploy/no-deploy decision

### Long-Term:
- Demo testing (if validated)
- Live testing (if demo successful)
- Scale gradually (if live profitable)

---

**Status:** ✅ **Implementation Complete**  
**Running:** Walk-forward validation on available data  
**ETA:** Results in ~15-20 minutes

---

*"Validation is the difference between a hypothesis and a proven strategy."*

**Let's see if H1 + BOS + HTF H4 passes the test!** 🎯

