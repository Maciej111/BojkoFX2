# PROOF V2: FINAL GO/NO-GO DECISION

**Date:** 2026-02-19 16:45:30

---

## A) Determinism Status

| Symbol | Status | Notes |
|--------|--------|-------|
| EURUSD | PASS | 3 runs identical |
| GBPUSD | PASS | 3 runs identical |
| USDJPY | PASS | 3 runs identical |
| XAUUSD | PASS | 3 runs identical |

---

## B) Baseline OOS Results (2023-2024)

| Symbol | Trades | Exp(R) | PF | MaxDD(1%) | Return(1%) |
|--------|--------|--------|----|-----------|-----------|
| EURUSD | 234 | 0.212 | 1.03 | 17.0 | 50.2 |
| GBPUSD | 200 | 0.572 | 1.71 | 26.9 | 147.1 |
| USDJPY | 225 | 0.300 | 1.14 | 16.2 | 83.5 |
| XAUUSD | 220 | 0.178 | 1.22 | 19.1 | 41.4 |

---

## C) Cost Stress Results

| Symbol | Baseline Exp | Mild Exp | Moderate Exp | Severe Exp |
|--------|--------------|----------|--------------|------------|
| EURUSD | 0.212R | 0.132R | 0.012R | -0.188R |
| GBPUSD | 0.572R | 0.505R | 0.405R | 0.239R |
| USDJPY | 0.300R | 0.220R | 0.100R | -0.100R |
| XAUUSD | 0.178R | 0.138R | 0.078R | -0.022R |

---

## D) Outlier Risk

| Symbol | Concentration (%) | Risk Flag |
|--------|-------------------|------------|
| EURUSD | 123.0 | YES |
| GBPUSD | 103.6 | YES |
| USDJPY | 77.2 | YES |
| XAUUSD | 90.3 | YES |

---

## E) Final Verdict

### Criteria Check (FX Pairs: EURUSD, GBPUSD, USDJPY)

- **Determinism PASS:** YES
- **Baseline Exp(R) > 0:** YES
- **Mild Slippage Exp(R) >= 0:** YES
- **MaxDD(1%) <= 35%:** YES

### Decision: GO TO PAPER TRADING

**Status:** All criteria met for FX pairs (EURUSD, GBPUSD, USDJPY)

**Recommended Symbols:** EURUSD, GBPUSD, USDJPY

### XAUUSD Separate Assessment

- Baseline Exp: 0.178R
- Mild Exp: 0.138R
- Decision: GO

---

## F) Risk Management Recommendation

### Initial Risk

- **Start:** 0.5% risk per trade
- **Reasoning:** Conservative entry, validate execution quality
- **Scaling:** After 50 trades, if Exp(R) maintained and MaxDD < 25%, increase to 1.0%

### Position Limits

- Max concurrent positions: 3 (1 per symbol max)
- Daily loss limit: 2% of account
- Monthly DD stop: 15%

### Monitoring

- Track slippage per trade (actual vs expected)
- Compare live Exp(R) to backtest after 20 trades
- Alert if MaxDD exceeds 20%

---

**Report generated:** 2026-02-19 16:45:30
