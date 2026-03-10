# PROOF V2: DETERMINISM CHECK (3 RUNS ALL SYMBOLS)

**Date:** 2026-02-19 16:45:30

---

## Test Setup

- Runs per symbol: 3
- Comparison: SHA256 hash + metrics
- Tolerance: 1e-9

## Results

| Symbol | Hash Match | Trades Match | Exp Match | PF Match | Deterministic |
|--------|------------|--------------|-----------|----------|---------------|
| EURUSD | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | PASS | PASS | PASS | PASS | PASS |
| USDJPY | PASS | PASS | PASS | PASS | PASS |
| XAUUSD | PASS | PASS | PASS | PASS | PASS |

### Run Details

**EURUSD:**

| Run | Trades | Expectancy | PF | MaxDD | Hash |
|-----|--------|------------|-------|-------|------|
| 1 | 234 | 0.211648R | 1.0278 | 17.03% | `1d3fa7217c65` |
| 2 | 234 | 0.211648R | 1.0278 | 17.03% | `1d3fa7217c65` |
| 3 | 234 | 0.211648R | 1.0278 | 17.03% | `1d3fa7217c65` |

**GBPUSD:**

| Run | Trades | Expectancy | PF | MaxDD | Hash |
|-----|--------|------------|-------|-------|------|
| 1 | 200 | 0.571909R | 1.7131 | 26.87% | `e09c2fb0a655` |
| 2 | 200 | 0.571909R | 1.7131 | 26.87% | `e09c2fb0a655` |
| 3 | 200 | 0.571909R | 1.7131 | 26.87% | `e09c2fb0a655` |

**USDJPY:**

| Run | Trades | Expectancy | PF | MaxDD | Hash |
|-----|--------|------------|-------|-------|------|
| 1 | 225 | 0.299678R | 1.1367 | 16.24% | `49eaea1e2e45` |
| 2 | 225 | 0.299678R | 1.1367 | 16.24% | `49eaea1e2e45` |
| 3 | 225 | 0.299678R | 1.1367 | 16.24% | `49eaea1e2e45` |

**XAUUSD:**

| Run | Trades | Expectancy | PF | MaxDD | Hash |
|-----|--------|------------|-------|-------|------|
| 1 | 220 | 0.177787R | 1.2240 | 19.15% | `a66b2a9e46b7` |
| 2 | 220 | 0.177787R | 1.2240 | 19.15% | `a66b2a9e46b7` |
| 3 | 220 | 0.177787R | 1.2240 | 19.15% | `a66b2a9e46b7` |

## Verdict

**Determinism Status:** PASS

All symbols produce identical results across 3 independent runs.

