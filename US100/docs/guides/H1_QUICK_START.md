# H1 Testing - Quick Start & Summary

**Date:** 2026-02-18  
**Status:** ✅ **H1 Bars Built, Tests Running**

---

## ✅ COMPLETED

### 1. Implementation
- ✅ `scripts/build_h1_bars.py` - H1 bar builder from ticks
- ✅ `scripts/run_h1_tests.py` - H1 test runner
- ✅ H1 bars generated: **5,067 bars** (vs 20,268 M15 bars)

### 2. H1 Bars Built
```
Input:  data/raw/eurusd-tick-2024-06-01-2024-12-31.csv (12.4M ticks)
Output: data/bars/eurusd_h1_bars.csv (5,067 H1 bars)
Time:   ~30 seconds
```

### 3. Tests In Progress
- H1 Baseline BOS
- H1 Test D (BOS + HTF H4)
- H1 Test F (BOS + Partial TP)

---

## 📊 WHAT TO EXPECT

### M15 Baseline (Reference):
```
Trades:     121
Win Rate:   42.98%
Expectancy: -0.018R
Return:     -2.34%
Max DD:     24.92%
```

### H1 Predictions:

**Scenario 1: H1 Better (Likely)**
```
Trades:     30-40
Win Rate:   48-52%
Expectancy: +0.05 to +0.15R
Return:     +2% to +6%
Max DD:     15-20%
```

**Why:** Cleaner price action, less noise, stronger zones

---

**Scenario 2: H1 Similar**
```
Trades:     35-45
Win Rate:   40-45%
Expectancy: -0.02 to +0.02R
Return:     -1% to +1%
Max DD:     20-25%
```

**Why:** S&D works similarly across timeframes

---

**Scenario 3: H1 Worse (Unlikely)**
```
Trades:     25-35
Win Rate:   35-40%
Expectancy: -0.05 to -0.10R
Return:     -2% to -4%
Max DD:     25-30%
```

**Why:** Too few setups, statistical noise dominates

---

## 🔍 KEY METRICS TO WATCH

### 1. Trade Count
- **M15:** 121 trades
- **H1 Expected:** ~30-40 trades (70-75% reduction)
- **Minimum viable:** 30 trades for statistical significance

### 2. Win Rate
- **M15:** 42.98%
- **Breakeven (RR 1.5):** 40%
- **Target:** 45%+ on H1

### 3. Expectancy
- **M15:** -0.018R (essentially breakeven)
- **Target:** >0.0R (profitable)
- **Good:** >+0.10R

### 4. Max DD
- **M15:** 24.92%
- **Target:** <20%
- **Acceptable:** <25%

---

## 📈 HYPOTHESIS TESTING

### H1: Higher TF = Higher Win Rate
**Reasoning:** Less whipsaws, cleaner zones  
**Test:** Compare WR(H1) vs WR(M15)  
**Expected:** ✅ H1 > M15

### H2: Higher TF = Higher Expectancy
**Reasoning:** Better quality setups  
**Test:** Compare Exp(H1) vs Exp(M15)  
**Expected:** ✅ H1 > M15

### H3: Higher TF = Lower DD
**Reasoning:** Fewer trades, more stable  
**Test:** Compare DD(H1) vs DD(M15)  
**Expected:** ✅ H1 < M15

### H4: Edge Grows with TF
**Overall Test:** All 3 above true  
**Expected:** ✅ YES

---

## 📁 OUTPUT FILES

### After Test Completion:

```
data/bars/
  eurusd_h1_bars.csv ✅

reports/
  trades_h1_baseline_bos.csv
  summary_h1_baseline_bos.md
  equity_curve_h1_baseline_bos.png
  r_histogram_h1_baseline_bos.png
  
  trades_h1_testD_bos_htf.csv
  summary_h1_testD_bos_htf.md
  equity_curve_h1_testD_bos_htf.png
  r_histogram_h1_testD_bos_htf.png
  
  trades_h1_testF_bos_partial_tp.csv
  summary_h1_testF_bos_partial_tp.md
  equity_curve_h1_testF_bos_partial_tp.png
  r_histogram_h1_testF_bos_partial_tp.png

data/outputs/
  H1_COMPLETE_REPORT_EURUSD.md
```

---

## 🚀 NEXT COMMANDS

### View H1 Report:
```powershell
cat data/outputs/H1_COMPLETE_REPORT_EURUSD.md
```

### Run Walk-Forward (if needed):
```powershell
python scripts/run_h1_tests.py --mode walkforward
```

### Compare M15 vs H1:
```powershell
# M15 Baseline
cat data/outputs/comparison_report_EURUSD_M15_20240601-20241231.md

# H1 Report
cat data/outputs/H1_COMPLETE_REPORT_EURUSD.md
```

---

## 💡 DECISION TREE

### If H1 Expectancy > 0:
→ ✅ **Switch to H1 as primary timeframe**
→ ✅ Re-run all Phase 2 tests on H1
→ ✅ Forward test H1 on demo

### If H1 Expectancy ≈ M15 (both near 0):
→ ⚠️ **Choose based on preference**
→ M15: More trades, more monitoring
→ H1: Fewer trades, less monitoring
→ Consider running both in parallel

### If H1 Expectancy < M15:
→ ❌ **Stick with M15**
→ Test H4 next (even higher TF)
→ Focus optimization efforts on M15

---

## 🎯 SUCCESS CRITERIA

### Minimum (Acceptable):
- ✅ H1 tests complete without errors
- ✅ Trade count ≥ 25 (statistical minimum)
- ✅ Expectancy ≥ M15 (-0.018R)

### Good:
- ✅ Trade count ≥ 30
- ✅ Win Rate ≥ 45%
- ✅ Expectancy > 0.0R
- ✅ Max DD < 20%

### Excellent:
- ✅ Trade count ≥ 35
- ✅ Win Rate ≥ 50%
- ✅ Expectancy > +0.10R
- ✅ Max DD < 15%
- ✅ Profit Factor > 1.2

---

## 📊 M15 vs H1 KEY DIFFERENCES

### Time Aggregation:
- **M15:** 15-minute bars
- **H1:** 60-minute bars (4x M15)

### Bar Count (2024 H2):
- **M15:** 20,268 bars
- **H1:** 5,067 bars (4x less)

### Trade Frequency:
- **M15:** ~17 trades/month
- **H1:** ~5 trades/month (expected)

### Zone Size:
- **M15:** Smaller zones (tighter stops)
- **H1:** Larger zones (wider stops)

### ATR:
- **M15:** ~0.0005-0.0010
- **H1:** ~0.0020-0.0040 (4x larger)

### Stop Loss:
- **M15:** ~10-20 pips
- **H1:** ~40-80 pips (4x larger)

### Take Profit:
- **M15:** ~15-30 pips
- **H1:** ~60-120 pips (4x larger)

---

## 🔧 TECHNICAL DETAILS

### H1 Bar Construction:
```python
bars = ticks.resample('1h').agg({
    'bid': ['first', 'max', 'min', 'last'],
    'ask': ['first', 'max', 'min', 'last']
})
```

### HTF for H1:
- **Base TF:** H1
- **HTF:** H4 (4x ratio maintained)
- **HTF Lookback:** 100 H4 bars = 400 hours

### BOS on H1:
- **Pivot Lookback:** 3 bars
- **Equivalent:** 3 hours (vs 45 min on M15)
- **Detection:** Same logic, different scale

---

## ⏱️ ESTIMATED TIMES

### H1 Tests (2024 H2 only):
- **Test Time:** ~5-7 minutes
- **Tests:** 3 configurations
- **Total:** ~15-20 minutes

### H1 Walk-Forward (2021-2024):
- **Test Time:** ~5 min/year
- **Years:** 4
- **Total:** ~20-25 minutes

### Combined:
- **Total Time:** ~40-45 minutes

---

## 📝 CURRENT STATUS

```
[✅] H1 bars built (5,067 bars)
[⏳] H1 tests running (in progress)
[  ] H1 report generated
[  ] Walk-forward completed (optional)
```

**Estimated completion:** ~20 minutes

---

## 🎉 WHAT'S NEXT

### After H1 Tests Complete:

1. **Review H1_COMPLETE_REPORT.md**
   - Check M15 vs H1 comparison
   - Verify hypotheses

2. **Decision Point:**
   - If H1 better → Switch to H1
   - If similar → Choose preference
   - If worse → Stick with M15 or test H4

3. **Optional: Walk-Forward**
   - Validate H1 stability across years
   - Compare to M15 walk-forward

4. **Forward Testing:**
   - Demo account testing
   - Live small size testing

---

**Status:** ✅ **H1 Implementation Complete**  
**Current:** Tests running  
**ETA:** Results in ~20 minutes

---

*"The best timeframe is the one that gives consistent results with the least stress."*

**Let's see if H1 is that timeframe!** 🎯

