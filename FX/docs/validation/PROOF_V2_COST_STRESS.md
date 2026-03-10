# PROOF V2: COST MODEL V2 - CONSISTENT SLIPPAGE

**Date:** 2026-02-19 16:45:30

---

## Slippage Configuration (Price Units)

| Symbol | Mild | Moderate | Severe |
|--------|------|----------|--------|
| EURUSD | 0.0002 | 0.0005 | 0.001 |
| GBPUSD | 0.0002 | 0.0005 | 0.001 |
| USDJPY | 0.02 | 0.05 | 0.1 |
| XAUUSD | 0.1 | 0.25 | 0.5 |

**Note:** Slippage applied to both entry and exit (2x per trade)

---

## Baseline Results (No Additional Slippage)

| Symbol | Trades | WR (%) | Exp(R) | PF | MaxDD(1%) | Return(1%) |
|--------|--------|--------|--------|----|-----------|-----------|
| EURUSD | 234 | 46.6 | 0.212 | 1.03 | 17.0 | 50.2 |
| GBPUSD | 200 | 48.5 | 0.572 | 1.71 | 26.9 | 147.1 |
| USDJPY | 225 | 49.8 | 0.300 | 1.14 | 16.2 | 83.5 |
| XAUUSD | 220 | 48.2 | 0.178 | 1.22 | 19.1 | 41.4 |

---

## Stress Test Results

### EURUSD

| Scenario | Slip(R) | Exp(R) | PF | MaxDD(1%) | Return(1%) |
|----------|---------|--------|----|-----------|-----------|
| Baseline | 0.000 | 0.212 | 1.03 | 17.0 | 50.2 |
| Mild | 0.080 | 0.132 | 1.03 | 19.8 | 24.6 |
| Moderate | 0.200 | 0.012 | 1.03 | 23.8 | -5.9 |
| Severe | 0.400 | -0.188 | 1.03 | 41.3 | -41.1 |

### GBPUSD

| Scenario | Slip(R) | Exp(R) | PF | MaxDD(1%) | Return(1%) |
|----------|---------|--------|----|-----------|-----------|
| Baseline | 0.000 | 0.572 | 1.71 | 26.9 | 147.1 |
| Mild | 0.067 | 0.505 | 1.71 | 28.2 | 116.4 |
| Moderate | 0.167 | 0.405 | 1.71 | 30.5 | 77.2 |
| Severe | 0.333 | 0.239 | 1.72 | 40.5 | 27.0 |

### USDJPY

| Scenario | Slip(R) | Exp(R) | PF | MaxDD(1%) | Return(1%) |
|----------|---------|--------|----|-----------|-----------|
| Baseline | 0.000 | 0.300 | 1.14 | 16.2 | 83.5 |
| Mild | 0.080 | 0.220 | 1.13 | 19.2 | 53.3 |
| Moderate | 0.200 | 0.100 | 1.13 | 23.7 | 17.1 |
| Severe | 0.400 | -0.100 | 1.12 | 33.7 | -25.4 |

### XAUUSD

| Scenario | Slip(R) | Exp(R) | PF | MaxDD(1%) | Return(1%) |
|----------|---------|--------|----|-----------|-----------|
| Baseline | 0.000 | 0.178 | 1.22 | 19.1 | 41.4 |
| Mild | 0.040 | 0.138 | 1.21 | 21.8 | 29.5 |
| Moderate | 0.100 | 0.078 | 1.20 | 25.5 | 13.5 |
| Severe | 0.200 | -0.022 | 1.17 | 32.9 | -8.9 |

---

## Edge Survival Summary

| Symbol | Baseline>0 | Mild>0 | Moderate>0 | Severe>0 |
|--------|------------|--------|------------|----------|
| EURUSD | PASS | PASS | PASS | FAIL |
| GBPUSD | PASS | PASS | PASS | PASS |
| USDJPY | PASS | PASS | PASS | FAIL |
| XAUUSD | PASS | PASS | PASS | FAIL |
