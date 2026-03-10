# ENGINE AUDIT REPORT - EVIDENCE-BASED VERIFICATION

**Date:** 2026-02-18
**Data:** trades_full_2_EURUSD_H1_2021_2024.csv (414 trades)
**Config:** #2 (Winner: +0.582R)

---

## 1. METRIC RECOMPUTATION AUDIT

**Objective:** Verify reported metrics by recomputing from raw trades data.

| Metric | Reported | Recomputed | Diff | Match |
|--------|----------|------------|------|-------|
| Expectancy_R | 0.5818 | 0.5818 | 0.000000 | PASS |
| Win_Rate | 46.6184 | 46.6184 | 0.000000 | PASS |
| Profit_Factor | 1.4290 | 1.4290 | 0.000000 | PASS |
| Max_DD_pct | 17.6682 | 17.6682 | 0.000000 | PASS |

**Result:** PASS - All metrics verified

## 2. R-MULTIPLE AUDIT

**Objective:** Verify R-multiples are consistent with exit reasons.

- Total trades checked: 414
- R anomalies found: 353

**Issues Found:**
- TP exits should have R near 1.8 (RR ratio)
- SL exits should have R near -1.0
- 353 trades outside expected ranges

Sample (first 10):

- Trade 0: SHORT TP
  - R: 0.4002 (expected: (1.7, 1.9))
- Trade 1: SHORT SL
  - R: -4.3886 (expected: (-1.1, -0.9))
- Trade 2: SHORT SL
  - R: -7.1100 (expected: (-1.1, -0.9))
- Trade 3: LONG SL
  - R: -0.1166 (expected: (-1.1, -0.9))
- Trade 4: LONG SL
  - R: -1.1955 (expected: (-1.1, -0.9))
- Trade 5: SHORT TP
  - R: 5.7165 (expected: (1.7, 1.9))
- Trade 6: SHORT SL
  - R: -0.2481 (expected: (-1.1, -0.9))
- Trade 7: LONG SL
  - R: -5.6933 (expected: (-1.1, -0.9))
- Trade 8: SHORT SL
  - R: -4.7034 (expected: (-1.1, -0.9))
- Trade 9: LONG TP
  - R: 3.6503 (expected: (1.7, 1.9))

**Result:** FAIL - R anomalies detected

## 3. INTRABAR CONFLICT AUDIT

**Objective:** Verify worst-case execution when SL and TP both hit in same bar.

- Total conflicts (SL & TP in same bar): 2

**FAIL:** 2 trades closed at TP despite SL also being hit.
With worst-case policy, SL should be hit first.

Sample (first 10):

- Trade 38: LONG
  - Exit time: 2021-05-07 12:00:00
  - Entry: 1.20724, Est SL: 1.20624, Est TP: 1.20904
  - Bar range: [1.20581, 1.21462]
  - SL hit: True, TP hit: True
  - Exit reason: TP (should be SL!)

- Trade 170: LONG
  - Exit time: 2022-05-04 18:00:00
  - Entry: 1.05394, Est SL: 1.05294, Est TP: 1.05574
  - Bar range: [1.05105, 1.06265]
  - SL hit: True, TP hit: True
  - Exit reason: TP (should be SL!)

**Result:** FAIL - 2 worst-case violations

## 4. PIVOT LOOK-AHEAD AUDIT

**Objective:** Verify pivots used for SL are confirmed before entry.

**Note:** Pivot timestamps not stored in trades CSV. Simplified check performed.

- Time paradoxes (entry >= exit): 0

**Result:** PASS

*Full pivot audit requires pivot_time column in trades data.*

## 5. BID/ASK FEASIBILITY AUDIT

**Objective:** Verify entry/exit prices are feasible given OHLC bid/ask.

- Sampled trades: 50
- Feasibility issues: 12

**Issues Found:**

- Trade 325: SHORT
  - Exit FAIL: 1.05846 not in [1.05707, 1.05808]
- Trade 261: LONG
  - Exit FAIL: 1.08917 not in [1.08518, 1.08621]
- Trade 387: SHORT
  - Exit FAIL: 1.10288 not in [1.10299, 1.10473]
- Trade 143: LONG
  - Exit FAIL: 1.12886 not in [1.12752, 1.12828]
- Trade 372: SHORT
  - Exit FAIL: 1.08558 not in [1.08609, 1.08682]
- Trade 19: LONG
  - Exit FAIL: 1.19102 not in [1.18987, 1.19061]
- Trade 14: LONG
  - Exit FAIL: 1.21191 not in [1.21204, 1.21310]
- Trade 39: LONG
  - Exit FAIL: 1.21638 not in [1.21674, 1.21769]
- Trade 411: LONG
  - Exit FAIL: 1.04230 not in [1.04072, 1.04187]
- Trade 322: SHORT
  - Exit FAIL: 1.05674 not in [1.05581, 1.05649]

**Result:** FAIL - 12 feasibility issues

---

## OVERALL AUDIT RESULT

1. Metric Recomputation:    PASS
2. R-Multiple Validation:   FAIL
3. Intrabar Conflicts:      FAIL
4. Pivot Look-Ahead:        PASS
5. Bid/Ask Feasibility:     FAIL

**OVERALL: FAIL**

---

*Report generated: 2026-02-18*
