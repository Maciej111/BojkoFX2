# ORB Mini Test - Results Report

**Strategy:** Opening Range Breakout  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** 2021-01-01 -> 2025-12-31 (5 years)  
**Timeframe:** 5min  
**Generated:** 2026-03-12  

**Parameters:**
- OR window: 14:30-15:00 UTC (first 30 min of US session)
- Entry: next bar open after breakout bar close
- SL: LONG -> OR_low | SHORT -> OR_high
- TP: RR = 2.0
- EOD close: 21:00 UTC if neither TP nor SL hit
- Max 1 trade per day

---

## Overall Results

| Metric | Value |
|--------|-------|
| Total trades | 1275 |
| Trades/year | 255.0 |
| Win rate | 46.2% |
| Expectancy R | +0.034 R |
| Profit factor | 1.08 |
| Max DD (R) | 20.4 R |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| EOD (21:00 UTC) | 656 | 51.5% |
| SL hit | 470 | 36.9% |
| TP hit | 149 | 11.7% |

## Direction Breakdown

| Direction | Trades | Win Rate | E(R) |
|-----------|--------|----------|------|
| LONG | 672 | 50.3% | +0.072 |
| SHORT | 603 | 41.6% | -0.009 |

## Year-by-Year

| Year | Trades | Win Rate | E(R) |
|------|--------|----------|------|
| 2021 | 255 | 48.6% | +0.041 |
| 2022 | 254 | 46.9% | +0.108 |
| 2023 | 255 | 46.3% | -0.002 |
| 2024 | 256 | 43.0% | -0.017 |
| 2025 | 255 | 46.3% | +0.039 |

---

## Key Observations

### 1. Edge is real but marginal
Overall E(R)=+0.034R and PF=1.08 confirm a small positive edge, but it is not strong enough for live trading in its current form.

### 2. LONG vs SHORT divergence
- **LONG** (WR 50.3%, E(R)=+0.072R): Consistent edge — profitable in all 5 years. Aligns with the structural bullish bias of US100.
- **SHORT** (WR 41.6%, E(R)=-0.009R): Essentially breakeven. No edge worth building on.

### 3. EOD closes dominate
51% of trades are closed at EOD without hitting TP or SL. This suppresses profitability — the market frequently reverses intraday before the 2R target is reached.

### 4. TP rarely reached
Only 149/1275 trades (11.7%) reach TP at 2R. This is the core structural weakness of the setup at RR=2.0.

### 5. Stability is weak
2023 and 2024 were unprofitable years (E(R) -0.002 and -0.017). The strategy does not hold up uniformly across all market regimes.

---

## Verdict

| Question | Answer |
|----------|--------|
| Does ORB have an edge on US100? | Yes, small and unstable |
| Is it tradable as-is? | No |
| Worth deeper research? | Yes — LONG only |
| SHORT ORB worth pursuing? | No |

---

## Recommended Next Steps (if pursuing further)

1. **LONG only** — drop SHORT entirely, eliminate -0.009R drag
2. **Trend filter** — only trade LONG when price > EMA50 (H1 or D1); expected to improve WR and E(R) further
3. **Tighter EOD cut** — test closing at 18:00 UTC instead of 21:00 to avoid late-session reversals
4. **OR range size filter** — skip days where the OR range is unusually narrow (<0.5 ATR) or wide (>3 ATR)
5. **ATR-based TP** — instead of fixed RR=2.0, test TP at OR_high + 1.5x OR_range (mean reversion target)

If LONG-only + trend filter produces E(R) > +0.10R with PF > 1.20, it is a candidate for a full strategy module.

---

## Script

`research/orb_mini_test.py`
