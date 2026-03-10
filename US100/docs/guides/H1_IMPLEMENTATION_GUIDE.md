# H1 Timeframe Testing - Implementation Guide

**Date:** 2026-02-18  
**Objective:** Test identical strategy on H1 timeframe vs M15

---

## 🎯 OBJECTIVE

Run **IDENTICAL tests** as M15 Phase 1 & 2, but on **H1 timeframe**.

**No changes to:**
- Execution logic
- Bid/ask rules
- Intra-bar worst-case
- BOS logic
- First-touch rule

**Only change:** Timeframe M15 → H1

---

## 📋 IMPLEMENTATION

### New Files Created:

1. ✅ `scripts/build_h1_bars.py` (100 lines)
   - Builds H1 bars directly from ticks
   - Open = first tick in hour
   - High/Low = max/min in hour
   - Close = last tick in hour
   - Forward fills missing bars

2. ✅ `scripts/run_h1_tests.py` (400+ lines)
   - Runs 3 H1 tests (Baseline BOS, HTF, Partial TP)
   - Walk-forward 2021-2024
   - Generates H1_COMPLETE_REPORT

---

## 🔧 USAGE

### Step 1: Build H1 Bars

```powershell
python scripts/build_h1_bars.py
```

**Input:** `data/raw/eurusd-tick-2024-06-01-2024-12-31.csv`  
**Output:** `data/bars/eurusd_h1_bars.csv`

**Time:** ~2-3 minutes

---

### Step 2: Run H1 Tests (2024 H2 only)

```powershell
python scripts/run_h1_tests.py --symbol EURUSD --mode tests
```

**Tests:**
- H1 Baseline BOS
- H1 Test D (BOS + HTF H4)
- H1 Test F (BOS + Partial TP)

**Output:**
- `reports/trades_h1_baseline_bos.csv`
- `reports/trades_h1_testD_bos_htf.csv`
- `reports/trades_h1_testF_bos_partial_tp.csv`
- Equity curves & R histograms

**Time:** ~5-7 minutes

---

### Step 3: Run H1 Walk-Forward (2021-2024)

```powershell
python scripts/run_h1_tests.py --symbol EURUSD --mode walkforward
```

**Tests:** Baseline BOS per year (2021, 2022, 2023, 2024)

**Time:** ~15-20 minutes

---

### Step 4: Run Both

```powershell
python scripts/run_h1_tests.py --symbol EURUSD --mode both
```

**Total Time:** ~20-25 minutes

---

## 📊 EXPECTED RESULTS

### H1 vs M15 Comparison:

**Hypotheses to Test:**

1. **Higher WR on H1?**
   - H1 has cleaner price action
   - Less noise than M15
   - **Expected:** WR should increase

2. **Higher Expectancy on H1?**
   - Stronger S&D zones on higher TF
   - Better risk/reward opportunities
   - **Expected:** Expectancy should improve

3. **Lower DD on H1?**
   - Fewer whipsaws
   - More stable equity curve
   - **Expected:** DD should decrease

4. **Edge grows with TF?**
   - Industry wisdom: "Higher TF = better edge"
   - **To verify:** Does data support this?

---

## 🔍 KEY DIFFERENCES H1 vs M15

### Trade Frequency:
- **M15:** ~121 trades over 7 months
- **H1 Expected:** ~30-40 trades (3-4x less)

### Bar Count:
- **M15:** 20,268 bars
- **H1:** ~5,067 bars (4x less)

### Zone Formation:
- **M15:** More frequent, smaller zones
- **H1:** Less frequent, larger zones

### ATR:
- **M15:** Smaller ATR values
- **H1:** Larger ATR values (wider stops/targets)

---

## 📈 SANITY CHECKS

For each H1 test, verify:

1. **Spread Statistics**
   - Average H1 spread = M15 spread (same underlying data)
   - Should be ~1.3 pips

2. **Same-Bar SL/TP**
   - H1 bars are 4x larger
   - More likely to hit both SL+TP in same bar
   - Worst-case policy more important

3. **Look-Ahead**
   - Same anti-lookahead rules apply
   - Zone created before entry

4. **First-Touch**
   - 100% of trades should be first touch
   - max_touches_per_zone = 1

5. **BOS Logic**
   - Pivot lookback = 3 (same as M15)
   - Should detect pivots correctly on H1

---

## 📁 OUTPUT FILES

### Test Results:
```
reports/
  trades_h1_baseline_bos.csv
  summary_h1_baseline_bos.md
  equity_curve_h1_baseline_bos.png
  r_histogram_h1_baseline_bos.png
  
  trades_h1_testD_bos_htf.csv
  summary_h1_testD_bos_htf.md
  ...
  
  trades_h1_testF_bos_partial_tp.csv
  summary_h1_testF_bos_partial_tp.md
  ...
```

### Walk-Forward:
```
reports/
  trades_h1_baseline_2021.csv
  trades_h1_baseline_2022.csv
  trades_h1_baseline_2023.csv
  trades_h1_baseline_2024.csv
```

### Final Report:
```
data/outputs/H1_COMPLETE_REPORT_EURUSD.md
```

---

## 🎯 REPORT STRUCTURE

### H1_COMPLETE_REPORT.md Contains:

#### 1. H1 Test Results (2024 H2)
- Table with all 3 tests
- Trades, WR, Expectancy, PF, DD, Return

#### 2. M15 vs H1 Comparison
- Side-by-side table
- Baseline BOS on both timeframes
- Differences (absolute & percentage)

#### 3. Walk-Forward Analysis
- Year-by-year results
- 4-year averages
- Std dev
- Best/worst years

#### 4. Conclusions
- ✅/❌ Does H1 have higher WR?
- ✅/❌ Does H1 have higher Expectancy?
- ✅/❌ Does H1 have lower DD?
- ✅/❌ Does edge grow with TF?

#### 5. Final Verdict
- **Does S&D work better on higher TF?**
- Recommendation: Use H1 or stick with M15?

---

## 💡 EXPECTED INSIGHTS

### Scenario A: H1 is Better
```
H1 Baseline BOS:
  Trades: 35
  WR: 50%
  Expectancy: +0.15R
  Return: +5.25%
```

**Interpretation:**
- ✅ Higher TF provides real edge
- ✅ Cleaner zones, less noise
- **Recommendation:** Switch to H1

---

### Scenario B: M15 is Better
```
H1 Baseline BOS:
  Trades: 40
  WR: 38%
  Expectancy: -0.10R
  Return: -4.00%
```

**Interpretation:**
- ❌ Higher TF doesn't help
- ❌ Fewer opportunities, not better quality
- **Recommendation:** Stick with M15

---

### Scenario C: Similar Results
```
H1 Baseline BOS:
  Trades: 38
  WR: 43%
  Expectancy: -0.02R
  Return: -0.76%
```

**Interpretation:**
- ⚠️ No significant difference
- Strategy works similarly on both TFs
- **Recommendation:** Choose based on preference (M15 = more trades, H1 = less monitoring)

---

## 🔧 TECHNICAL NOTES

### H1 Bars Construction:

Uses pandas resample:
```python
bars = df.resample('1h').agg({
    'bid': ['first', 'max', 'min', 'last']
})
```

**Advantages:**
- Direct from ticks (no aggregation from M15)
- Preserves bid/ask properly
- Consistent with M15 methodology

### HTF for H1:

When H1 is base timeframe, HTF must be H4:
```python
config['strategy']['htf_period'] = '4h'
```

**Rationale:**
- M15 → H1 (4x ratio)
- H1 → H4 (4x ratio)
- Maintains same relative scale

### BOS on H1:

Same pivot_lookback = 3:
```python
config['strategy']['pivot_lookback'] = 3
```

**Works because:**
- 3 bars on H1 = 12 bars on M15 (time-wise)
- Equivalent to ~3 hours lookback
- Appropriate for pivot detection

---

## 🚀 QUICK START

**Complete H1 testing in 3 commands:**

```powershell
# 1. Build H1 bars
python scripts/build_h1_bars.py

# 2. Run H1 tests + walk-forward
python scripts/run_h1_tests.py --mode both

# 3. View results
cat data/outputs/H1_COMPLETE_REPORT_EURUSD.md
```

**Total Time:** ~25 minutes

---

## ✅ DONE CRITERIA

- [x] H1 bars builder created
- [x] H1 tests script created
- [ ] H1 bars built (in progress)
- [ ] H1 tests run
- [ ] Walk-forward completed
- [ ] H1_COMPLETE_REPORT generated

---

## 📝 NEXT STEPS (After Running)

### If H1 is better:
1. ✅ Switch primary timeframe to H1
2. ✅ Re-run Phase 2 tests on H1
3. ✅ Forward test on demo (H1)

### If M15 is better:
1. ✅ Confirm M15 as primary TF
2. ✅ Consider testing H4 (even higher TF)
3. ✅ Focus optimization on M15

### If similar:
1. ✅ Choose based on trading style
2. ✅ M15 = more active, H1 = more passive
3. ✅ Consider testing both in parallel

---

**Status:** ✅ **Implementation Complete**  
**Next:** Build H1 bars and run tests

---

*"The right timeframe is the one that gives you the most edge with the least noise."*

**Let's find out if H1 is that timeframe!** 🎯

