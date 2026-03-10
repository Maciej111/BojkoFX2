# Critical Engineering Review — BojkoIDX

**Scope:** Full codebase audit covering architecture quality, backtest correctness, lookahead bias, strategy consistency, execution model realism, data pipeline safety, testing quality, trading risk, hidden technical risks, and a prioritised refactoring plan.

**Convention used:**
- 🔴 **Critical** — incorrect results or live-trading money risk
- 🟡 **Medium** — degraded accuracy or maintenance risk
- 🟢 **Low / informational** — best-practice gap, no immediate harm

---

## 1. Architecture Quality Review

### What works well
- Layered separation: `data` → `structure` → `strategies` → `backtest` → `execution` → `runners`.
- Typed dataclasses in `src/core/config.py` (`StrategyConfig`, `SymbolConfig`, `RiskConfig`, `IBKRConfig`) provide IDE-visible types and defaults.
- `SQLiteStateStore` implements idempotent order recording (`make_intent_id` SHA-1 hash).
- `IBKRExecutionEngine` has a three-gate safety circuit (`readonly` + `allow_live_orders` + `kill_switch_active`).

### Structural problems

**🔴 Two parallel strategy implementations never merged**

| File | HTF bias filter | Pivot anti-lookahead | Used in |
|------|----------------|----------------------|---------|
| `src/strategies/trend_following_v1.py` | ✅ `get_htf_bias_at_bar()` | ✅ `detect_pivots_confirmed()` | Backtests |
| `src/core/strategy.py` | ❌ absent | ❌ internal `_detect_pivots()` has lookahead | Live trading |

The system that runs real money uses a different, weaker strategy than the one whose performance reports are shown to users. See §4 for full details.

**🔴 Two parallel pivot implementations**

| File | Lookahead safe? | Used by |
|------|----------------|---------|
| `src/structure/pivots.py` (`detect_pivots_confirmed`) | ✅ | `trend_following_v1.py` |
| `src/indicators/pivots.py` (`detect_swing_pivots`) | ❌ | `engine.py`, `engine_enhanced.py`, `detect_zones.py` |

Backtests that pass through the zone engine report inflated edge. See §3 for full analysis.

**🟡 Two parallel config systems**
`src/utils/config.py` (legacy plain-dict `BACKTEST_CONFIG`) coexists with `src/core/config.py` (typed dataclasses). Several older backtest scripts still pull from the legacy dict. Keeping both invites parameter-value drift that is invisible to static analysis.

**🟡 Two ATR implementations with different warmup behaviour**

| Location | Formula |
|----------|---------|
| `trend_following_v1.py` | `rolling(14).mean()` — simple arithmetic mean |
| `src/indicators/atr.py` | `ewm(alpha=1/14)` — Wilder exponential moving average |

The simple MA requires exactly 14 bars of warmup and then gives uniform weight to all 14 bars. Wilder EWM never fully "forgets" early bars and is the canonical ATR formula. They diverge most during volatile regimes, which are precisely the bars that most affect entry sizing.

---

## 2. Backtest Engine Correctness (`src/backtest/execution.py`)

### Correct behaviours
- **Intrabar SL/TP conflict → always SL** (worst-case). Documented and defensible.
- **Fill side**: LONG fills on ASK (`low_ask ≤ entry ≤ high_ask`), SHORT fills on BID — correct.
- **Exit side**: LONG exits on BID, SHORT exits on ASK — correct.
- **Fill feasibility assertion**: raises `ValueError` if the entry/exit price falls outside the bar OHLC range, catching data errors early.

### Bugs

**🔴 Symbol hardcoded as `"EURUSD"` in `_open_position()`**
```python
symbol = "EURUSD"   # line in ExecutionEngine._open_position
```
Every trade object records `symbol="EURUSD"` regardless of what instrument is actually being backtested. Post-trade analysis—grouping results by symbol, filtering for winner/loser patterns—is corrupted for all non-EURUSD instruments.

**🔴 Commission assumes 1 standard lot regardless of position size**
```python
commission = self.config['commission_per_lot']   # e.g. $7, flat
```
Commission is deducted as a fixed amount irrespective of the actual number of lots traded. For indices or any parametric lot-size run, the net PnL per trade is wrong. When `lot_size` is 0.01 (micro lot), the commission is 100× over-charged; when it's 10 lots, it is 10× under-charged.

**🔴 `raise ValueError` on zero risk distance aborts entire backtest**
```python
if risk_distance == 0:
    raise ValueError(...)
```
A single bar with a degenerate candle (zero ATR in low-volume data) kills the entire run. This should be a `continue` (skip that bar) with a log warning, not a hard abort.

**🟡 PnL scaled by `lot_size` assumes FX pip convention**
```python
pnl = realized_distance * lot_size * 100_000
```
The `× 100_000` multiplier bakes in FX contract size. For US100 (USATECHIDXUSD) with `lot_size=1`, each pip of movement is worth $100,000 — nonsensical. The index backtest scripts work around this by ignoring the dollar PnL column and computing an R-based drawdown directly, but the `Trade.result` field still holds garbage for indices.

---

## 3. Lookahead Bias Risk

### `src/indicators/pivots.py` — **CONFIRMED lookahead** 🔴

```python
for i in range(lookback, len(df) - lookback):
    # Pivot high uses bars i-lookback … i+lookback (future)
    if all(high[i] >= high[i-lookback:i]) and \
       all(high[i] >= high[i+1:i+lookback+1]):   # ← future bars
        highs.append((i, high[i]))
```

When iterating bar `i`, bars `i+1` through `i+lookback` have not occurred yet. The function labels `i` as a confirmed pivot using information from the future—`lookback` bars of lookahead are embedded in every call. Any strategy using this function "knows" pivot locations that could not have been known in real time.

**Affected modules:** `src/backtest/engine.py`, `src/backtest/engine_enhanced.py`, `src/backtest/detect_zones.py`. All backtests routed through the zone-based engine overstate edge.

### `src/structure/pivots.py` — **Anti-lookahead, correct** ✅

```python
def detect_pivots_confirmed(df, lookback=3, confirmation_bars=1):
    # Only labels pivot at bar i if i+confirmation_bars has already closed
    # Caller iterates with current_bar_time; only processes bars <= current_bar_time
```

Pivot `i` is not labelled until bar `i + confirmation_bars` has closed. Used by `trend_following_v1.py`.

### `src/structure/bias.py` — **Safe** ✅

```python
htf_slice = htf_df[htf_df.index <= current_bar_time]
```

HTF bias is always computed on the subset of bars available *at or before* the LTF bar being processed.

### Summary matrix

| Module | Lookahead safe | Strategy using it |
|--------|---------------|------------------------|
| `src/structure/pivots.py` | ✅ | `trend_following_v1.py` (backtest), live runner |
| `src/indicators/pivots.py` | ❌ | `engine.py`, `engine_enhanced.py`, `detect_zones.py` |
| `src/structure/bias.py` | ✅ | Both |

---

## 4. Strategy Logic Consistency

The live runner (`run_paper_ibkr_gateway.py`) instantiates `TrendFollowingStrategy` from `src/core/strategy.py`. The performance reports were produced by `run_trend_backtest()` in `src/strategies/trend_following_v1.py`. These two code paths share a name but differ in three critical ways:

### 4.1 HTF Bias Filter — missing in live strategy 🔴

`trend_following_v1.py`:
```python
htf_bias = get_htf_bias_at_bar(htf_df, bar_time)
if htf_bias == 0:
    continue   # no trend on HTF → no trade
```

`core/strategy.py`: There is no call to `get_htf_bias_at_bar`. Every BOS triggers a trade regardless of the higher-timeframe trend direction. The HTF filter is a primary edge component; without it the live system will enter counter-trend which the backtest data shows degrades expectancy significantly.

### 4.2 Pivot detection — lookahead in live strategy 🔴

`core/strategy.py` uses an internal `_detect_pivots()`:
```python
for i in range(lookback, len(df) - lookback):
    if all(high_col[i] >= high_col[i+1:i+lookback+1]):  # future bars
```

This is the same lookahead window as `src/indicators/pivots.py`. When scanning historical data at startup or on a replayed bar, the strategy "sees" pivot confirmations that would not be available in production.

### 4.3 BOS confirmation delay — weaker in live strategy 🟡

`_check_bos()` in `core/strategy.py`:
```python
if last_high_idx < current_idx - 2:   # 2-bar minimum delay
```

`trend_following_v1.py` uses `detect_pivots_confirmed(..., confirmation_bars=1)` which provides exactly 1 confirmed follow-up bar. The 2-bar cutoff in `core/strategy.py` delays entry slightly more, but the underlying pivot detection still uses future bars to _locate_ the pivot, so the delay is partially cosmetic.

---

## 5. Execution Model Realism

### Spread model
Constant `ASK = BID + fixed_spread` across all hours. Real spreads widen at market open, news events, and low-liquidity periods. For FX this is a minor overstatement of round-trip cost; for US100 pre-market or post-market it understates spread by 3-10×.

### Fill model
**Optimistic for volatile bars.** If a bar moves 100 pips and the limit order is queued, fill is assumed at the exact limit price. In reality, a fast market could gap through the limit. This overstates fill quality on large ATR bars.

No partial fills are modeled (correct for liquid FX/indices at stated sizes; becomes incorrect for large lot sizes against thin books).

### Latency
At H1 granularity, latency is irrelevant for entry detection. However, `IBKRExecutionEngine` submits bracket orders synchronously within the callback; any delay > 30 s can mean the price has moved before the bracket is acknowledged. No queue-age timeout is implemented.

### Commission (live)
`IBKRExecutionEngine._calculate_units()` sizes positions in **units** (e.g., 12,453 units of EURUSD), not lots. IBKR charges commission per share/contract/unit. The backtest charges a flat per-lot fee. These are structurally incompatible and must be reconciled before comparing live versus backtested transaction costs.

---

## 6. Data Pipeline Safety

### Strengths
- Dukascopy 1M CSVs are UTC — no timezone conversion is needed for FX.
- `resample('1h', closed='left', label='left')` is correct: bar labelled at period open, OHLC aggregated inclusively.
- HTF derived by resampling LTF in backtests eliminates cross-source timestamp misalignment.

### Risks

**🟡 Weekend/holiday gaps not explicitly handled**
`resample()` produces rows for every closed period. A gap weekend produces no row (resampler skips empty periods with `how='ohlc'`), but the detection logic uses `.shift(1)` for True Range, which will silently cross the gap and produce an abnormally large TR value on Sunday 17:00 open. No gap-detection guard is in place.

**🟡 No data integrity assertions**
No checks that `open ≤ high`, `low ≤ open`, `close ≥ low`, spread ≥ 0. A corrupted CSV row will propagate silently through the entire backtest.

**🟡 Constant spread ignores intraday spread dynamics**
USATECHIDXUSD has nearly zero spread during RTH and wide spread pre-market. Using a constant spread underestimates cost for off-hours signals. Combined with a session filter this is mitigated but not eliminated.

**🟢 Live bar bootstrap uses IBKR midpoint data**
`ibkr_marketdata.py` applies `BOOTSTRAP_HALF_SPREAD` to convert midpoint to bid/ask — acceptable approximation for liquid instruments but introduces a parameterized constant that must be maintained.

---

## 7. Testing Quality

### Well-covered areas
- `test_state_store.py` — 15+ tests covering schema creation, migration idempotency, save/load, upsert, status transitions (forward only), idempotent `intent_id`, multi-symbol queries.
- `test_pivots_no_lookahead.py` — dedicated test for anti-lookahead behaviour of `structure/pivots.py`.
- `test_bos_pullback_setup.py` — BOS detection and pullback setup lifecycle.
- `test_execution_logic.py` — covers `ExecutionEngine.process_bar()` logic.

### Critical gaps

**🔴 `test_schema_version_is_1` defined twice**
```python
def test_schema_version_is_1(self, store):
    # ... asserts version == 1

def test_schema_version_is_1(self, store):  # same name: silently overrides the first
    # ... asserts version == 2
```
Python's class namespace overwrites the first definition. pytest collects only the second. The v1-schema invariant is never verified. Rename the first to `test_schema_version_starts_at_1`.

**🔴 No tests for `src/core/strategy.py` (live strategy class)**
Zero test coverage for `TrendFollowingStrategy`: pivot detection, BOS detection, setup lifecycle, HTF bias application (which is absent but should be), state persistence. This is the code path that places real orders.

**🟡 No tests for `IBKRExecutionEngine`**
No unit tests for position sizing (`_calculate_units`), trailing stop logic (`_update_trail_sl`), or risk gate (`_check_risk`). These are testable without an actual IBKR connection using a mock `ib` object.

**🟡 No test asserting HTF bias filter is applied by live strategy**
Because `core/strategy.py` is missing the HTF filter entirely, a test that verifies a counter-trend BOS is rejected would have caught this regression.

**🟡 No commission-scaling test**
No test verifies that `commission_per_lot` scales with actual position size rather than being applied as a flat fee.

---

## 8. Trading Risk Assessment

### Overfitting risk
The configuration in `DEFAULT_SYMBOLS` (`src/core/config.py`) contains symbol-specific values for `adx_h4_gate`, `atr_pct_filter_min/max`, `risk_reward`, `trailing_stop` parameters. Each per-symbol override is sourced from session analysis reports that use the same historical data used for strategy development. This is in-sample parameter selection dressed up as optimisation — it passes walk-forward by chance because the OOS windows are short (1 year each).

### Regime robustness
The strategy is a trend-following BOS pullback. The 4-year sample (2021–2024) includes COVID recovery, Fed tightening (2022), and 2023 normalisation — a reasonable spread. However:
- All index tests are on one instrument (USATECHIDXUSD). Single-instrument conclusions have high sampling variance.
- 5M/4H combination (best result: Exp=+0.300R, PF=1.39) has ~1,000+ trades over 4 years — statistically meaningful, but PF=1.39 is a low margin before transaction costs and slippage erode it.

### Live-backtest divergence risk
Given the strategy divergence in §4 (no HTF filter, lookahead pivots), live performance should be expected to differ materially from reported backtests. The most likely scenario is lower selectivity (more trades) with lower average R (counter-trend signals mixed in).

### Drawdown control
- Maximum drawdown guard: `max_dd_pct` in `RiskConfig` — functional.
- Kill switch: persisted to DB and restorable on restart — good design.
- No consecutive-loss circuit breaker: after 5 SLs in a row the system continues to size at full `risk_fraction`. A cooling-off rule would reduce tail risk.

---

## 9. Hidden Technical Risks

### 🔴 Trailing stop state is not persisted — lost on restart

`IBKRExecutionEngine._records` is an in-memory `Dict[int, _OrderRecord]`. `_OrderRecord` holds:
```python
trail_activated: bool = False
trail_sl: float = 0.0
trail_sl_ibkr_id: int = 0
```

On process restart, `restore_positions_from_ibkr()` reconstructs `_records` from live IBKR brackets. However, it has no knowledge of whether `trail_activated` was `True` or what the last trailed SL was. Restart while a winner is in trail mode will:
1. Reuse the original `sl_price` from the `OrderIntent` as the trailing reference.
2. Potentially place a stop **wider** than the currently active IBKR stop if the position has already moved, creating a risk gap.

**Fix:** Persist `trail_activated`, `trail_sl`, `trail_sl_ibkr_id` to the `orders` table and restore them in `restore_positions_from_ibkr()`.

### 🔴 SQLite threading: shared connection with autocommit + `check_same_thread=False`

```python
conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
```

`isolation_level=None` sets autocommit mode. The `_tx()` context manager issues explicit `BEGIN`/`COMMIT`. However, `ib_insync` fires bar-sealed callbacks from its own event loop thread, which may call `store.save_state()` while the poll loop thread is mid-transaction. SQLite WAL mode serialises writers, but if two threads issue `BEGIN` and one is in the middle of writing, the other gets `database is locked` — swallowed by the `except Exception` handler in `_tx()`. Silent write failures leave the DB in a stale state.

**Fix:** Use a `threading.Lock` to serialise all DB writes, or open a separate connection per thread.

### 🔴 `purge_zombie_records()` — symbol normalisation heuristic may miss matches

```python
raw = getattr(p.contract, "localSymbol", "") or getattr(p.contract, "symbol", "")
symbols_with_position.add(raw.replace(".", "").replace("/", "").upper())
```

IBKR returns different `localSymbol` formats depending on whether the contract is an FX pair (`EUR.USD`) or an index (`USATECHIDXUSD` vs `NQ`). The normalisation strips `.` and `/` but does not alias IBKR contract codes to the internal symbol names used in `_records`. A zombie record for `USATECHIDXUSD` may not match `NQ` or `NQ MAR25` as returned by IBKR, keeping a zombie alive indefinitely and blocking new entries via the risk gate.

### 🟡 IBKR `client_id` collision not detected at startup

No check is made to verify that `client_id` is not already in use by another connection. A duplicate run from a second terminal will silently disconnect the first instance without returning an error. IBKR Gateway logs the disconnect; the bot does not.

### 🟡 `equity_override` silently controls all position sizing

```python
override = getattr(self.risk, "equity_override", 0.0)
if override > 0:
    self._account_equity = float(override)
```

If `equity_override` is set in config and the account balance grows significantly, all subsequent sizing is based on the stale override. There is no periodic reconciliation. For paper accounts with unrealistic balances this is intentional — it must be actively maintained for live accounts.

### 🟢 `_kill_switch_from_env` attached as a non-dataclass attribute

```python
config._kill_switch_from_env = kill_switch
```

This is a runtime monkeypatch on a frozen-style dataclass. `mypy` will flag it as an unknown attribute. The runner uses `getattr(config, '_kill_switch_from_env', False)` as a guard — pragmatic but fragile if `Config` is ever frozen with `@dataclass(frozen=True)`.

---

## 10. Refactoring Plan

### Critical — fix before trusting live results

| # | Change | File | Risk without fix |
|---|--------|------|-----------------|
| C1 | Add `get_htf_bias_at_bar()` call to `TrendFollowingStrategy.on_bar()` | `src/core/strategy.py` | Live system trades counter-trend; live/backtest divergence |
| C2 | Replace `_detect_pivots()` with `detect_pivots_confirmed()` from `src/structure/pivots.py` | `src/core/strategy.py` | Lookahead in live pivot detection at startup replay |
| C3 | Persist `trail_activated`, `trail_sl` to `orders` table; restore in `restore_positions_from_ibkr()` | `src/core/state_store.py`, `src/execution/ibkr_exec.py` | Trailing stop widened after restart; uncontrolled risk |
| C4 | Fix `symbol = "EURUSD"` hardcode — pass actual symbol from order dict | `src/backtest/execution.py` | All non-EURUSD trade records labelled wrong; corrupted analysis |
| C5 | Scale commission by actual position size (convert internal units to lots) | `src/backtest/execution.py` | Transaction costs systematically wrong for non-1-lot sizes |
| C6 | Fix duplicate `test_schema_version_is_1` method (rename first to `test_schema_version_starts_at_1`) | `tests/test_state_store.py` | v1 schema invariant never tested |

### Medium — fix before adding new features

| # | Change | File |
|---|--------|------|
| M1 | Unify ATR: choose Wilder EWM (`ewm(alpha=1/14, adjust=False)`) and remove `rolling(14).mean()` | `src/strategies/trend_following_v1.py` |
| M2 | Deprecate or delete `src/indicators/pivots.py`; audit all callers and migrate to `src/structure/pivots.py` | `src/backtest/engine.py`, `engine_enhanced.py`, `detect_zones.py` |
| M3 | Add `threading.Lock` around all SQLite writes in `SQLiteStateStore` | `src/core/state_store.py` |
| M4 | Change `raise ValueError` on zero risk distance to `log.warning + continue` | `src/backtest/execution.py` |
| M5 | Add `localSymbol`→internal name mapping to `purge_zombie_records()` | `src/execution/ibkr_exec.py` |
| M6 | Remove legacy `src/utils/config.py`; migrate remaining scripts to `src/core/config.py` | All backtest scripts |

### Optional — code quality and future proofing

| # | Change |
|---|--------|
| O1 | Add unit tests for `TrendFollowingStrategy.on_bar()` including HTF filter rejection |
| O2 | Add unit tests for `IBKRExecutionEngine._calculate_units()` and `_update_trail_sl()` with mock `ib` |
| O3 | Add input validation in `build_h1_idx.py`/`run_backtest_idx.py` (assert `open ≤ high`, `low ≤ close`, spread ≥ 0) |
| O4 | Add IBKR `client_id` conflict detection at startup (`ib.managedAccounts()` returns empty on conflict) |
| O5 | Add consecutive-loss circuit breaker to `RiskConfig` (e.g., halt after N losses within M bars) |
| O6 | Promote `_kill_switch_from_env` to a proper field in `Config` or `IBKRConfig` |

---

## Summary Table of Critical Issues

| ID | Severity | Location | Description |
|----|----------|----------|-------------|
| C1 | 🔴 Critical | `core/strategy.py` | HTF bias filter absent — live trades counter-trend |
| C2 | 🔴 Critical | `core/strategy.py` | Lookahead in pivot detection used by live strategy |
| C3 | 🔴 Critical | `ibkr_exec.py`, `state_store.py` | Trailing stop state in-memory only — lost on restart |
| C4 | 🔴 Critical | `backtest/execution.py` | `symbol="EURUSD"` hardcoded for all instruments |
| C5 | 🔴 Critical | `backtest/execution.py` | Commission flat-fee ignores actual position size |
| C6 | 🔴 Critical | `tests/test_state_store.py` | Duplicate method silences v1 schema test |
| M1 | 🟡 Medium | `trend_following_v1.py` | ATR uses simple MA not Wilder EWM |
| M2 | 🟡 Medium | `indicators/pivots.py` | Lookahead pivot module not deprecated |
| M3 | 🟡 Medium | `state_store.py` | SQLite threading: no write lock |
| M4 | 🟡 Medium | `backtest/execution.py` | `raise ValueError` on zero-risk aborts full run |
| M5 | 🟡 Medium | `ibkr_exec.py` | Symbol normalisation fails for index contracts |
