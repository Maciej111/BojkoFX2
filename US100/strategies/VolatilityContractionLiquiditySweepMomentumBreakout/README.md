# VolatilityContractionLiquiditySweepMomentumBreakout (VCLSMB)

## Strategy Description

Three-phase market structure strategy:

1. **Volatility Contraction** — ATR contracts relative to its rolling max; defines a compression range
2. **Liquidity Sweep** — price wicks beyond the compression range (clearing stop orders), closes back inside
3. **Momentum Breakout** — strong directional bar breaks out of the range in the sweep direction

### State Machine

```
IDLE → COMPRESSION → SWEEP_DETECTED → MOMENTUM_CONFIRMED → IN_POSITION → IDLE
```

---

## What Was Reused

| Component | Source |
|-----------|--------|
| ATR calculation (Wilder) | `shared/bojkofx_shared/indicators/atr.py` |
| EMA calculation | `shared/bojkofx_shared/indicators/ema.py` |
| `load_ltf()` / `build_htf_from_ltf()` / `filter_by_date()` | `scripts/run_backtest_idx.py` |
| `compute_metrics()` | `src/backtest/metrics.py` |
| Trade dict schema (R, direction, entry/exit, SL/TP) | Same as `trend_following_v1.py` |
| Synthetic test bar factory pattern | `tests/test_strategy_end_to_end.py` |
| Session filter logic | Inline (mirrors `shared/bojkofx_shared/indicators/session_filter.py`) |
| Bar data files | `data/bars_idx/usatechidxusd_5m_bars.csv` |

## What Was Added (Strategy-Specific)

| File | Purpose |
|------|---------|
| `config.py` | `VCLSMBConfig` dataclass — all tunable parameters |
| `feature_pipeline.py` | Computes ATR, rolling range, body/range ratio (no-lookahead) |
| `detectors.py` | Pure-function detectors for compression, sweep, momentum |
| `state_machine.py` | `MachineContext` + `advance()` — bar-by-bar state transitions |
| `signals.py` | `Signal` dataclass (output of momentum confirmation) |
| `risk_management.py` | Entry/SL/TP computation with anchor choice |
| `strategy.py` | Full bar-loop backtest: `run_vclsmb_backtest()` |
| `run_backtest.py` | CLI runner — saves trades CSV + markdown report |
| `tests/test_vclsmb.py` | Unit + integration tests (no external data needed) |

---

## How to Run Tests

From the `US100/` directory:

```bash
# All VCLSMB tests
pytest strategies/VolatilityContractionLiquiditySweepMomentumBreakout/tests/ -v

# With coverage
pytest strategies/VolatilityContractionLiquiditySweepMomentumBreakout/tests/ -v --tb=short
```

No external data files required — all tests use synthetic bars.

---

## How to Run Backtest

From the `US100/` directory:

```bash
# Default: 2021-2025, 5min LTF, RR=2.0, improved params, session filter OFF
python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest

# With trend filter enabled
python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest \
  --start 2021-01-01 --end 2025-12-31 \
  --trend-filter

# Overnight session filter (21-02 UTC, crosses midnight)
python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest \
  --session-filter

# Custom params
python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest \
  --start 2022-01-01 --end 2024-12-31 \
  --rr 2.5 \
  --compression-atr-ratio 0.5 \
  --sweep-atr-mult 0.6 \
  --momentum-atr-mult 1.5 \
  --trend-filter \
  --trailing-stop --trailing-atr-mult 3.0

# 15-minute LTF
python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest \
  --ltf 15min --rr 2.0
```

---

## Where Outputs Are Written

All strategy-specific outputs are isolated in this folder:

```
strategies/VolatilityContractionLiquiditySweepMomentumBreakout/
  output/
    USATECHIDXUSD_VCLSMB_5m_YYYY-MM-DD_TRADES.csv   ← trade log
  report/
    USATECHIDXUSD_VCLSMB_5m_YYYY-MM-DD_REPORT.md    ← markdown summary
```

Global `reports/` directory is **not touched** by this strategy.

---

## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_period` | 14 | Wilder ATR period |
| `compression_lookback` | 20 | Bars for rolling ATR max |
| `compression_atr_ratio` | 0.6 | ATR/ATR_max threshold for compression |
| `range_window` | 10 | Bars to define consolidation range |
| `sweep_atr_mult` | **0.5** | Minimum wick extension beyond range (in ATR) |
| `sweep_close_inside` | True | Sweep bar must close back inside range |
| `momentum_atr_mult` | **1.3** | Breakout bar body ≥ N × ATR |
| `momentum_body_ratio` | **0.65** | Breakout bar body/range fraction |
| `risk_reward` | 2.0 | TP = entry + RR × risk |
| `sl_anchor` | `range_extreme` | `range_extreme` or `sweep_wick` |
| `sl_buffer_atr_mult` | 0.3 | Extra SL buffer beyond anchor |
| `enable_trend_filter` | False | EMA trend gate (LONG above EMA, SHORT below) |
| `trend_ema_period` | 50 | EMA period for trend filter |
| `use_trailing_stop` | False | Trail SL from best price |
| `trailing_atr_multiplier` | 2.0 | Trail distance in ATR units |
| `breakeven_atr_mult` | 1.0 | Move SL to BE after N ATR profit |
| `use_session_filter` | **False** | Session time gate (disabled by default) |
| `session_start_hour_utc` | 21 | Overnight session start (if enabled) |
| `session_end_hour_utc` | 2 | Overnight session end, crosses midnight (if enabled) |
| `max_bars_in_state` | 30 | Setup TTL (expiry) |

---

## Architecture Notes

- **No lookahead**: `range_high`/`range_low` in `feature_pipeline.py` use `shift(1)` on rolling windows — bar N only sees bars 0..N-1.
- **Entry on next bar open**: signal fires on momentum confirmation bar; fill is `open_ask` (LONG) or `open_bid` (SHORT) of bar i+1.
- **Same-bar SL/TP conflict**: SL wins (conservative).
- **Metrics**: reuses `src.backtest.metrics.compute_metrics` → identical schema to `trend_following_v1` for comparability.

---

## Historical Backtest Results

**Data:** `usatechidxusd_5m_bars.csv` — 525 312 barów 5m (2021-01-01 do 2026-03-07)  
**Instrument:** US Tech 100 (NQ futures, bid/ask OHLC)  
**Last run:** 2026-03-11 (v2, improved parameters)

### Key findings from v1 (initial run)

During v1 testing it was discovered that:

1. **Default session filter (13-20 UTC) blocks 100% of signals.** The VC→LS→MB pattern forms almost exclusively during the Asian / pre-market overnight session (22:00-01:00 UTC) when NQ futures consolidate in low-liquidity ranges.

2. **State machine bug fixed:** Sweep detection was placed **after** the "compression lost" guard. A sweep bar by definition has elevated ATR, causing an immediate IDLE reset before the sweep could be registered.

---

### v1 Baseline vs v2 Improved

v1: `sweep_atr_mult=0.3, momentum_atr_mult=1.0, momentum_body_ratio=0.5`  
v2: `sweep_atr_mult=0.5, momentum_atr_mult=1.3, momentum_body_ratio=0.65`  
All results: `no session filter`

| Config | Period | n | WR | E(R) | PF | Max DD |
|--------|--------|---|----|------|----|--------|
| v1 Baseline | FULL 2021-2025 | 277 | 30% | -0.112 | 0.84 | 40.0 R |
| v1 Baseline | OOS 2023-2025 | 153 | 31% | -0.059 | 0.91 | 19.0 R |
| **v2 Improved** | FULL 2021-2025 | 171 | 31% | -0.070 | 0.90 | 22.0 R |
| **v2 Improved** | **OOS 2023-2025** | **93** | **35%** | **+0.065** | **1.10** | **9.0 R** |

---

### v2 Improved — yearly breakdown (OOS)

| Year | n | WR | E(R) | PF | Max DD |
|------|---|----|------|----|--------|
| IS 2021-2022 | 78 | 26% | -0.231 | 0.69 | 21.0 R |
| OOS 2023 | 37 | 41% | +0.216 | 1.36 | 6.0 R |
| OOS 2024 | 18 | 22% | -0.333 | 0.57 | 7.0 R |
| OOS 2025 | 38 | 37% | +0.105 | 1.17 | 8.0 R |

---

### v2 + EMA(50) trend filter

| Period | n | WR | E(R) | PF | Max DD |
|--------|---|----|------|----|--------|
| FULL 2021-2025 | 147 | 32% | -0.041 | 0.94 | 19.0 R |
| OOS 2023-2025 | 78 | 37% | **+0.115** | **1.18** | **6.0 R** |
| OOS 2023 | 34 | 44% | +0.324 | 1.58 | 6.0 R |
| OOS 2025 | 29 | 38% | +0.138 | 1.22 | 4.0 R |

---

### Session distribution

All signals form during **22:00-01:00 UTC** (Asian/pre-market overnight NQ session). Default `use_session_filter=False` ensures no signals are blocked.

See full improvement report in [report/IMPROVEMENT_REPORT_2026-03-11.md](report/IMPROVEMENT_REPORT_2026-03-11.md).

---

### Next tuning directions

1. **Session filter**: test strict 21:00-02:00 UTC overnight window
2. **Trailing stop**: 3-4×ATR trail (2×ATR too tight for overnight 5m)
3. **2024 deep-dive**: only 15-18 trades with trend filter — investigate why
4. **15min LTF**: reduce noise in sweep/momentum detection
5. **Sweep mult grid**: test 0.6, 0.7 against 0.5 baseline


### Next tuning directions

1. **Session filter**: change to overnight window (e.g., 21:00-01:00 UTC) to align with where setups form
2. **Momentum body ratio**: increase to 0.65-0.75 to filter fakeouts (raise WR at cost of frequency)
3. **Sweep ATR mult**: increase to 0.4-0.5 (require deeper sweep = more committed liquidity grab)
4. **Combine with trend filter**: only take LONG sweeps when HTF (1h) is above 20-EMA (avoid counter-trend in bear markets)
5. **15min LTF**: test on 15m bars to reduce noise in overnight session

