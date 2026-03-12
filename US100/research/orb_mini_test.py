# ORB Mini Test - Opening Range Breakout on US100 (USATECHIDXUSD)
# Quick standalone research script.  NOT part of the strategy framework.
#
# Rules
# -----
# * Opening range: 14:30-15:00 UTC (first 30 min of US session)
# * LONG  entry: break above OR_high -> enter at next-bar open
# * SHORT entry: break below OR_low  -> enter at next-bar open
# * SL:  LONG -> OR_low   | SHORT -> OR_high
# * TP:  RR = 2.0  (entry +/- 2 x risk)
# * 1 trade per day; session EOD close at 21:00 UTC if neither TP nor SL hit
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe research\orb_mini_test.py

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]   # …/US100
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import load_ltf  # noqa: E402 — after sys.path

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL       = "usatechidxusd"
TIMEFRAME    = "5min"
START        = "2021-01-01"
END          = "2025-12-31"
OR_START_H   = 14
OR_START_M   = 30
OR_END_H     = 15
OR_END_M     = 0
SESSION_END_H = 21
RR           = 2.0


def _calc_max_dd_r(r_series: pd.Series) -> float:
    """Max drawdown in R units from a series of R values."""
    equity = np.cumsum(r_series.values)
    equity = np.concatenate([[0.0], equity])
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    return float(dd.max())


def run_orb() -> None:
    # ── 1. Load data ──────────────────────────────────────────────────────────
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")]

    # ── 2. Session date (UTC date at bar close) ───────────────────────────────
    df = df.copy()
    df["date"] = df.index.normalize()   # UTC date

    trades: list[dict] = []

    for date, day in df.groupby("date"):
        day = day.sort_index()

        # ── 3. Opening range bars: [14:30, 15:00) ────────────────────────────
        or_mask = (
            (day.index.hour == OR_START_H) & (day.index.minute >= OR_START_M)
        ) | (
            (day.index.hour == OR_END_H)   & (day.index.minute < OR_END_M)
        )
        # Simpler: time >= 14:30 and time < 15:00
        or_mask = (day.index.hour * 60 + day.index.minute >= OR_START_H * 60 + OR_START_M) & \
                  (day.index.hour * 60 + day.index.minute <  OR_END_H   * 60 + OR_END_M)
        or_bars = day[or_mask]

        if len(or_bars) < 3:          # need a proper range (≥3 bars = 15 min)
            continue

        or_high = or_bars["high_bid"].max()
        or_low  = or_bars["low_bid"].min()
        or_range = or_high - or_low

        if or_range <= 0:
            continue

        # ── 4. Post-OR bars: ≥ 15:00 and < 21:00 UTC ─────────────────────────
        post_mask = (day.index.hour * 60 + day.index.minute >= OR_END_H * 60 + OR_END_M) & \
                    (day.index.hour < SESSION_END_H)
        post_bars = day[post_mask]

        if len(post_bars) < 2:
            continue

        trade_taken = False

        for i, (ts, bar) in enumerate(post_bars.iterrows()):
            if trade_taken:
                break

            # Check if this bar's close breaks the OR level
            broke_high = bar["close_bid"] > or_high
            broke_low  = bar["close_bid"] < or_low

            # Only first breakout counts; prefer LONG on tie
            if not broke_high and not broke_low:
                continue

            # Entry bar is the NEXT bar after signal bar
            remaining = post_bars.iloc[i + 1:]
            if len(remaining) == 0:
                break

            entry_bar  = remaining.iloc[0]
            entry_time = remaining.index[0]
            entry_price = entry_bar["open_bid"]

            if broke_high:
                direction = "LONG"
                sl = or_low
                risk = entry_price - sl
                if risk <= 0:
                    continue
                tp = entry_price + RR * risk
            else:
                direction = "SHORT"
                sl = or_high
                risk = sl - entry_price
                if risk <= 0:
                    continue
                tp = entry_price - RR * risk

            # ── 5. Simulate trade through remaining bars ───────────────────
            exit_price  = None
            exit_reason = "EOD"
            exit_time   = None

            for ets, ebar in remaining.iloc[1:].iterrows():
                h = ebar["high_bid"]
                l = ebar["low_bid"]

                if direction == "LONG":
                    if l <= sl:
                        exit_price  = sl
                        exit_reason = "SL"
                        exit_time   = ets
                        break
                    if h >= tp:
                        exit_price  = tp
                        exit_reason = "TP"
                        exit_time   = ets
                        break
                else:  # SHORT
                    if h >= sl:
                        exit_price  = sl
                        exit_reason = "SL"
                        exit_time   = ets
                        break
                    if l <= tp:
                        exit_price  = tp
                        exit_reason = "TP"
                        exit_time   = ets
                        break

            # EOD close at last available bar before 21:00
            if exit_price is None:
                eod_bars = post_bars[post_bars.index < post_bars.index[0].replace(
                    hour=SESSION_END_H, minute=0, second=0
                )]
                if len(eod_bars) == 0:
                    continue
                last_bar   = eod_bars.iloc[-1]
                exit_price = last_bar["close_bid"]
                exit_time  = eod_bars.index[-1]
                exit_reason = "EOD"

            # ── 6. R multiple ─────────────────────────────────────────────
            if direction == "LONG":
                pnl_pts = exit_price - entry_price
            else:
                pnl_pts = entry_price - exit_price

            r_val = pnl_pts / risk

            trades.append({
                "date":         str(date.date()),
                "direction":    direction,
                "entry_time":   entry_time,
                "entry_price":  entry_price,
                "sl":           sl,
                "tp":           tp,
                "risk":         risk,
                "exit_time":    exit_time,
                "exit_price":   exit_price,
                "exit_reason":  exit_reason,
                "R":            round(r_val, 4),
                "or_high":      or_high,
                "or_low":       or_low,
            })

            trade_taken = True

    # ── 7. Results ────────────────────────────────────────────────────────────
    if not trades:
        print("No trades generated.")
        return

    tdf = pd.DataFrame(trades)
    tdf["year"] = pd.to_datetime(tdf["date"]).dt.year

    n = len(tdf)
    years = tdf["year"].nunique()
    tpy   = n / years if years > 0 else 0

    wr    = (tdf["R"] > 0).mean() * 100
    er    = tdf["R"].mean()
    gross_win  = tdf.loc[tdf["R"] > 0, "R"].sum()
    gross_loss = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    pf    = gross_win / gross_loss if gross_loss > 0 else float("inf")
    mdd   = _calc_max_dd_r(tdf["R"])

    longs  = tdf[tdf["direction"] == "LONG"]
    shorts = tdf[tdf["direction"] == "SHORT"]

    def _stats(sub: pd.DataFrame) -> tuple[int, float, float]:
        if len(sub) == 0:
            return 0, 0.0, 0.0
        return len(sub), (sub["R"] > 0).mean() * 100, sub["R"].mean()

    ln, lwr, ler = _stats(longs)
    sn, swr, ser = _stats(shorts)

    # Exit reason breakdown
    reasons = tdf["exit_reason"].value_counts()

    # Year-by-year
    yearly = tdf.groupby("year").apply(
        lambda g: pd.Series({
            "trades": len(g),
            "wr%":    round((g["R"] > 0).mean() * 100, 1),
            "E(R)":   round(g["R"].mean(), 3),
        })
    )

    print()
    print("=" * 48)
    print("  ORB MINI TEST - US100 (USATECHIDXUSD)")
    print("=" * 48)
    print(f"  Period       : {START}  ->  {END}")
    print(f"  OR window    : 14:30-15:00 UTC")
    print(f"  RR           : {RR}")
    print()
    print(f"  Total trades : {n}")
    print(f"  Trades/year  : {tpy:.1f}")
    print()
    print(f"  Win rate     : {wr:.1f}%")
    print(f"  Expectancy   : {er:+.3f} R")
    print(f"  Profit factor: {pf:.2f}")
    print(f"  Max DD (R)   : {mdd:.1f} R")
    print()
    print(f"  Exit reasons : {dict(reasons)}")
    print()
    print("  LONG")
    print(f"    trades : {ln}")
    print(f"    WR     : {lwr:.1f}%")
    print(f"    E(R)   : {ler:+.3f}")
    print()
    print("  SHORT")
    print(f"    trades : {sn}")
    print(f"    WR     : {swr:.1f}%")
    print(f"    E(R)   : {ser:+.3f}")
    print()
    print("  Year-by-year")
    print(yearly.to_string())
    print("=" * 48)
    print()


if __name__ == "__main__":
    run_orb()
