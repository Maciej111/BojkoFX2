"""
Smoke test for BojkoIDX — US100/NAS100USD live runner.

Tests (without placing real orders):
  1. Import check        — all modules load without errors
  2. CSV bars            — 5m bars file exists and loads correctly
  3. Strategy logic      — process_bar() fires on synthetic data
  4. IBKR connection     — optional, requires Gateway running on port 4002
  5. Market data IDX     — optional, subscribe to NAS100USD CFD

Run (no IBKR needed):
    python tests/smoke_test_idx.py

Run with IBKR connectivity:
    python tests/smoke_test_idx.py --ibkr
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Imports
# ─────────────────────────────────────────────────────────────────────────────

def test_imports() -> bool:
    print("=" * 60)
    print("TEST 1: Module imports")
    print("=" * 60)
    ok = True
    # Modules that only require our own code (always tested)
    core_modules = [
        ("src.core.strategy",    "TrendFollowingStrategy"),
        ("src.core.config",      "StrategyConfig"),
        ("src.core.state_store", "SQLiteStateStore"),
        ("src.reporting.logger", "TradingLogger"),
    ]
    # Modules that require ib_insync (skipped if ib_insync not installed)
    ibkr_modules = [
        ("src.data.ibkr_marketdata_idx", "IBKRMarketDataIdx, SYMBOL"),
        ("src.execution.ibkr_exec",      "IBKRExecutionEngine"),
        ("src.runners.run_live_idx",     "main"),
    ]

    ibkr_available = True
    try:
        import ib_insync  # noqa: F401
    except ImportError:
        ibkr_available = False
        print("  NOTE  ib_insync not installed — IBKR modules skipped")

    for mod, names in core_modules:
        try:
            m = __import__(mod, fromlist=names.split(","))
            for name in names.replace(" ", "").split(","):
                getattr(m, name)
            print(f"  OK  {mod}")
        except Exception as e:
            print(f"  FAIL {mod}: {e}")
            ok = False

    for mod, names in ibkr_modules:
        if not ibkr_available:
            print(f"  SKIP {mod}")
            continue
        try:
            m = __import__(mod, fromlist=names.split(","))
            for name in names.replace(" ", "").split(","):
                getattr(m, name)
            print(f"  OK  {mod}")
        except Exception as e:
            print(f"  FAIL {mod}: {e}")
            ok = False
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — CSV bars
# ─────────────────────────────────────────────────────────────────────────────

def test_csv_bars() -> bool:
    print("\n" + "=" * 60)
    print("TEST 2: 5m CSV bars")
    print("=" * 60)
    import pandas as pd

    csv_path = Path("data/bars_idx/usatechidxusd_5m_bars.csv")
    if not csv_path.exists():
        print(f"  SKIP  {csv_path} not found — no CSV fallback available")
        print("        (IBKR historical data will be used instead)")
        return True   # not required — IBKR bootstraps automatically

    try:
        df = pd.read_csv(csv_path, nrows=5000)
        df.columns = [c.strip().lower() for c in df.columns]
        ts_col = next(
            (c for c in df.columns if c in ("datetime", "timestamp") or "time" in c or "date" in c),
            df.columns[0]
        )
        df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df.dropna(subset=[ts_col], inplace=True)
        print(f"  OK  Loaded {len(df)} rows from {csv_path}")
        print(f"      Columns : {list(df.columns[:6])}")
        print(f"      First   : {df[ts_col].iloc[0]}")
        print(f"      Last    : {df[ts_col].iloc[-1]}")
        return True
    except Exception as e:
        print(f"  FAIL  {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — Strategy logic on synthetic data
# ─────────────────────────────────────────────────────────────────────────────

def test_strategy_logic() -> bool:
    print("\n" + "=" * 60)
    print("TEST 3: Strategy logic (synthetic data)")
    print("=" * 60)
    import numpy as np
    import pandas as pd
    from src.core.strategy import TrendFollowingStrategy
    from src.core.config import StrategyConfig

    try:
        # Build a synthetic 5m trending dataset (300 bars, uptrend)
        n = 300
        base = 18000.0
        half = 0.5
        rng = np.random.default_rng(42)
        closes = base + np.cumsum(rng.normal(2, 10, n))
        opens  = closes - rng.uniform(1, 5, n)
        highs  = np.maximum(opens, closes) + rng.uniform(1, 8, n)
        lows   = np.minimum(opens, closes) - rng.uniform(1, 8, n)

        timestamps = pd.date_range("2024-01-02 13:00", periods=n, freq="5min")
        df = pd.DataFrame({
            "open_bid":  opens  - half, "open_ask":  opens  + half,
            "high_bid":  highs  - half, "high_ask":  highs  + half,
            "low_bid":   lows   - half, "low_ask":   lows   + half,
            "close_bid": closes - half, "close_ask": closes + half,
        }, index=timestamps)

        # Build 4h HTF
        agg = {
            "open_bid": "first", "high_bid": "max", "low_bid": "min", "close_bid": "last",
            "open_ask": "first", "high_ask": "max", "low_ask": "min", "close_ask": "last",
        }
        htf = df.resample("4h").agg(agg).dropna(how="all")

        cfg = StrategyConfig(
            pivot_lookback_ltf=3, pivot_lookback_htf=5, confirmation_bars=1,
            require_close_break=True, risk_reward=2.0,
            entry_offset_atr_mult=0.3, pullback_max_bars=20,
        )
        strat = TrendFollowingStrategy(cfg)

        intents = []
        for i in range(len(df)):
            intents.extend(strat.process_bar(df, htf, i))

        print(f"  OK  process_bar() ran on {n} bars without error")
        print(f"      Signals generated: {len(intents)}")
        if intents:
            first = intents[0]
            print(f"      First signal: {first.side.value}  "
                  f"entry={first.entry_price:.2f}  sl={first.sl_price:.2f}  tp={first.tp_price:.2f}")
            # Sanity: sl < entry < tp for LONG
            from src.core.models import Side
            if first.side == Side.LONG:
                assert first.sl_price < first.entry_price < first.tp_price, \
                    f"Price ordering wrong: SL={first.sl_price} entry={first.entry_price} TP={first.tp_price}"
            else:
                assert first.tp_price < first.entry_price < first.sl_price, \
                    f"Price ordering wrong: TP={first.tp_price} entry={first.entry_price} SL={first.sl_price}"
            print("      Price ordering: OK (SL < entry < TP for LONG)")
        return True
    except Exception as e:
        import traceback
        print(f"  FAIL  {e}")
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — IBKR connection (optional)
# ─────────────────────────────────────────────────────────────────────────────

def test_ibkr_connection() -> bool:
    print("\n" + "=" * 60)
    print("TEST 4: IBKR Gateway connection")
    print("=" * 60)
    from ib_insync import IB
    ib = IB()
    try:
        print("  Connecting to 127.0.0.1:4002 (clientId=99)...")
        ib.connect("127.0.0.1", 4002, clientId=99, timeout=10)
        ts = ib.reqCurrentTime()
        print(f"  OK  Connected — server time: {ts}")
        ib.disconnect()
        return True
    except Exception as e:
        print(f"  FAIL  {e}")
        print("        Is IB Gateway (paper) running on port 4002?")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — Market data subscription (optional, needs IBKR)
# ─────────────────────────────────────────────────────────────────────────────

def test_market_data_idx() -> bool:
    print("\n" + "=" * 60)
    print("TEST 5: NAS100USD market data subscription")
    print("=" * 60)
    from src.data.ibkr_marketdata_idx import IBKRMarketDataIdx, SYMBOL

    md = IBKRMarketDataIdx(host="127.0.0.1", port=4002, client_id=99, historical_days=3)
    try:
        if not md.connect():
            print("  FAIL  Could not connect to IBKR Gateway")
            return False

        print("  Subscribing to NAS100USD CFD...")
        if not md.subscribe():
            print("  FAIL  subscribe() returned False")
            md.disconnect()
            return False

        bars = md.ltf_bars
        if bars is not None and not bars.empty:
            print(f"  OK  {len(bars)} 5m bars loaded for {SYMBOL}")
            print(f"      Last bar: {bars.index[-1]}")
            bid, ask = md.get_current_quote()
            print(f"      Current quote: bid={bid}  ask={ask}")
        else:
            print("  WARN  No bars loaded (market may be closed)")

        md.disconnect()
        return True
    except Exception as e:
        import traceback
        print(f"  FAIL  {e}")
        traceback.print_exc()
        try:
            md.disconnect()
        except Exception:
            pass
        return False


# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BojkoIDX smoke test")
    parser.add_argument("--ibkr", action="store_true",
                        help="Include IBKR connectivity tests (requires Gateway running)")
    args = parser.parse_args()

    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   BOJKOIDX — SMOKE TESTS                                  ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    results = []

    results.append(("Imports",        test_imports()))
    results.append(("CSV bars",       test_csv_bars()))
    results.append(("Strategy logic", test_strategy_logic()))

    if args.ibkr:
        conn_ok = test_ibkr_connection()
        results.append(("IBKR connection", conn_ok))
        if conn_ok:
            results.append(("Market data IDX", test_market_data_idx()))
        else:
            results.append(("Market data IDX", None))  # skipped

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    problems = 0
    for name, status in results:
        if status is True:
            label = "PASS"
        elif status is False:
            label = "FAIL"
            problems += 1
        else:
            label = "SKIP"
        print(f"  {label:<6}  {name}")

    print()
    if problems == 0:
        print("All tests passed.")
        if not args.ibkr:
            print()
            print("For full check (with IBKR):")
            print("  python tests/smoke_test_idx.py --ibkr")
        print()
        print("Dry-run (no orders, 5 min):")
        print("  python -m src.runners.run_live_idx --minutes 5")
    else:
        print(f"{problems} test(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
