# ORB GAP Mini Test - Opening Range Breakout with overnight GAP filter
# Standalone research script under strategies/OpeningRangeBreakout/research/
#
# Base: ORB v3 logic (LONG only + EMA50 1h + TP=1.6R)
# New:  GAP filter -- only trade days where overnight gap >= 0.3x ATR14
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_gap_mini_test.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]   # .../US100
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf                    # noqa: E402
from bojkofx_shared.indicators.atr import calculate_atr          # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
START         = "2021-01-01"
END           = "2025-12-31"
OR_START_MIN  = 14 * 60 + 30
OR_END_MIN    = 15 * 60 + 0
SESSION_END_H = 21
RR            = 1.6
EMA_PERIOD    = 50
ATR_PERIOD    = 14
MIN_GAP_ATR   = 10.0         # gap/ATR threshold (session gap 21:00 UTC prev -> 14:30 UTC)
                             # P50 ≈ 6.5, P62 ≈ 10.0 on this dataset

# v3 reference stats (from ORB_v3_mini_test_report.md)
V3 = dict(trades=660, wr=52.3, er=+0.065, pf=1.17, rr=1.6, tp_pct=14.2, eod_pct=52.9)

REPORT_PATH = Path(__file__).parent / "ORB_gap_mini_test_report.md"


def _calc_max_dd_r(r_series: pd.Series) -> float:
    equity = np.concatenate([[0.0], np.cumsum(r_series.values)])
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def build_ema50_1h(df5m: pd.DataFrame) -> pd.Series:
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    ema = _ema(h1, EMA_PERIOD)
    return ema.reindex(df5m.index, method="ffill")


def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


def run_orb_gap() -> tuple[pd.DataFrame, dict]:
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    df["ema50_1h"] = build_ema50_1h(df)
    df["atr"]      = calculate_atr(df, period=ATR_PERIOD)
    df["date"]     = df.index.normalize()

    # Build daily session-close series:
    # US100 session ends at 21:00 UTC.  Use last bar at/before 21:00 as prev-close
    # so that gap = OR_open (14:30) - prev_session_close is the true overnight gap.
    session_close = (
        df[df.index.hour < SESSION_END_H]
        .groupby("date")["close_bid"]
        .last()
    )

    trades: list[dict] = []
    days_filtered_gap = 0
    days_filtered_ema = 0
    gap_ratios_traded: list[float] = []

    dates_sorted = sorted(df["date"].unique())

    for i, date in enumerate(dates_sorted):
        day = df[df["date"] == date].sort_index()

        # Previous session close
        if i == 0:
            continue
        prev_date = dates_sorted[i - 1]
        if prev_date not in session_close.index:
            continue
        prev_close = session_close[prev_date]

        # OR first bar open (14:30 UTC) as current session open
        or_mask_full = (day.index.map(_bar_minutes) >= OR_START_MIN)
        or_open_day  = day[or_mask_full]
        if len(or_open_day) == 0:
            continue
        current_open = or_open_day.iloc[0]["open_bid"]

        atr_day = day["atr"].dropna()
        if len(atr_day) == 0:
            continue
        atr_val = atr_day.iloc[0]
        if pd.isna(atr_val) or atr_val <= 0:
            continue

        gap_size  = abs(current_open - prev_close)
        gap_ratio = gap_size / atr_val

        # GAP filter
        if gap_ratio < MIN_GAP_ATR:
            days_filtered_gap += 1
            continue

        # Opening range bars [14:30, 15:00)
        or_mask = (day.index.map(_bar_minutes) >= OR_START_MIN) & \
                  (day.index.map(_bar_minutes) <  OR_END_MIN)
        or_bars = day[or_mask]
        if len(or_bars) < 3:
            continue

        or_high  = or_bars["high_bid"].max()
        or_low   = or_bars["low_bid"].min()
        if (or_high - or_low) <= 0:
            continue

        # Post-OR bars [15:00, 21:00)
        post_mask = (day.index.map(_bar_minutes) >= OR_END_MIN) & \
                    (day.index.hour < SESSION_END_H)
        post_bars = day[post_mask]
        if len(post_bars) < 2:
            continue

        trade_taken = False

        for i_bar, (ts, bar) in enumerate(post_bars.iterrows()):
            if trade_taken:
                break

            if bar["close_bid"] <= or_high:
                continue

            # EMA filter
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                days_filtered_ema += 1
                break

            remaining = post_bars.iloc[i_bar + 1:]
            if len(remaining) == 0:
                break

            entry_price = remaining.iloc[0]["open_bid"]
            entry_time  = remaining.index[0]
            sl   = or_low
            risk = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + RR * risk

            exit_price  = None
            exit_reason = "EOD"
            exit_time   = None

            for ets, ebar in remaining.iloc[1:].iterrows():
                if ebar["low_bid"] <= sl:
                    exit_price, exit_reason, exit_time = sl, "SL", ets
                    break
                if ebar["high_bid"] >= tp:
                    exit_price, exit_reason, exit_time = tp, "TP", ets
                    break

            if exit_price is None:
                eod_cutoff = post_bars.index[0].replace(hour=SESSION_END_H, minute=0, second=0)
                eod_bars   = post_bars[post_bars.index < eod_cutoff]
                if len(eod_bars) == 0:
                    continue
                exit_price  = eod_bars.iloc[-1]["close_bid"]
                exit_time   = eod_bars.index[-1]
                exit_reason = "EOD"

            gap_ratios_traded.append(gap_ratio)
            trades.append({
                "date":        str(date.date()),
                "entry_time":  entry_time,
                "entry_price": entry_price,
                "sl":          sl,
                "tp":          tp,
                "risk":        risk,
                "exit_time":   exit_time,
                "exit_price":  exit_price,
                "exit_reason": exit_reason,
                "R":           round((exit_price - entry_price) / risk, 4),
                "gap_ratio":   round(gap_ratio, 3),
            })
            trade_taken = True

    meta = dict(
        days_filtered_gap=days_filtered_gap,
        days_filtered_ema=days_filtered_ema,
        avg_gap_ratio=round(float(np.mean(gap_ratios_traded)), 3) if gap_ratios_traded else 0.0,
    )
    return pd.DataFrame(trades), meta


def print_results(tdf: pd.DataFrame, meta: dict) -> None:
    if tdf.empty:
        print("No trades generated.")
        return

    tdf["year"] = pd.to_datetime(tdf["date"]).dt.year
    n     = len(tdf)
    years = tdf["year"].nunique()
    tpy   = n / years if years > 0 else 0
    wr    = (tdf["R"] > 0).mean() * 100
    er    = tdf["R"].mean()
    gw    = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl    = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    pf    = gw / gl if gl > 0 else float("inf")
    mdd   = _calc_max_dd_r(tdf["R"])
    reasons = tdf["exit_reason"].value_counts()

    yearly = tdf.groupby("year").apply(
        lambda g: pd.Series({
            "trades": int(len(g)),
            "wr%":    round((g["R"] > 0).mean() * 100, 1),
            "E(R)":   round(g["R"].mean(), 3),
        })
    )

    tp_pct  = int(reasons.get("TP",  0)) / n * 100
    eod_pct = int(reasons.get("EOD", 0)) / n * 100

    SEP = "=" * 54
    print()
    print(SEP)
    print("  ORB GAP MINI TEST - US100 (USATECHIDXUSD)")
    print(SEP)
    print(f"  Period        : {START}  ->  {END}")
    print(f"  Direction     : LONG only")
    print(f"  EMA filter    : close > EMA50 (1h)")
    print(f"  GAP filter    : (14:30 open - prev 21:00 close) / ATR >= {MIN_GAP_ATR}")
    print(f"  TP            : {RR}R  |  SL : OR_low")
    print()
    print(f"  Total trades  : {n}")
    print(f"  Trades/year   : {tpy:.1f}")
    print(f"  Skipped (GAP filter) : {meta['days_filtered_gap']}")
    print(f"  Skipped (EMA filter) : {meta['days_filtered_ema']}")
    print(f"  Avg gap/ATR (traded) : {meta['avg_gap_ratio']:.3f}")
    print()
    print(f"  Win rate      : {wr:.1f}%")
    print(f"  Expectancy    : {er:+.3f} R")
    print(f"  Profit factor : {pf:.2f}")
    print(f"  Max DD (R)    : {mdd:.1f} R")
    print()
    print("  Exit reasons")
    for reason in ["TP", "SL", "EOD"]:
        cnt = int(reasons.get(reason, 0))
        print(f"    {reason:<4} : {cnt:>4}  ({cnt/n*100:.1f}%)")
    print()
    print("  Year-by-year")
    print(yearly.to_string())
    print()
    print("  COMPARISON vs ORB v3")
    print(f"  {'Metric':<18}  {'v3':>8}  {'gap':>8}")
    print(f"  {'-'*18}  {'-'*8}  {'-'*8}")
    print(f"  {'Trades':<18}  {V3['trades']:>8}  {n:>8}")
    print(f"  {'Win rate':<18}  {V3['wr']:>7.1f}%  {wr:>7.1f}%")
    print(f"  {'Expectancy R':<18}  {V3['er']:>+8.3f}  {er:>+8.3f}")
    print(f"  {'Profit factor':<18}  {V3['pf']:>8.2f}  {pf:>8.2f}")
    print(f"  {'TP hit %':<18}  {V3['tp_pct']:>7.1f}%  {tp_pct:>7.1f}%")
    print(f"  {'EOD exits %':<18}  {V3['eod_pct']:>7.1f}%  {eod_pct:>7.1f}%")
    print(SEP)
    print()


def save_report(tdf: pd.DataFrame, meta: dict) -> None:
    if tdf.empty:
        return

    tdf["year"] = pd.to_datetime(tdf["date"]).dt.year
    n     = len(tdf)
    tpy   = n / tdf["year"].nunique()
    wr    = (tdf["R"] > 0).mean() * 100
    er    = tdf["R"].mean()
    gw    = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl    = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    pf    = gw / gl if gl > 0 else float("inf")
    mdd   = _calc_max_dd_r(tdf["R"])
    reasons = tdf["exit_reason"].value_counts()

    tp_cnt  = int(reasons.get("TP",  0))
    sl_cnt  = int(reasons.get("SL",  0))
    eod_cnt = int(reasons.get("EOD", 0))

    yearly = tdf.groupby("year").apply(
        lambda g: pd.Series({
            "trades": int(len(g)),
            "wr%":    round((g["R"] > 0).mean() * 100, 1),
            "E(R)":   round(g["R"].mean(), 3),
        })
    )
    years_profitable = sum(1 for _, r in yearly.iterrows() if r["E(R)"] > 0)

    yearly_md = "| Year | Trades | WR% | E(R) |\n|------|--------|-----|------|\n"
    for year, row in yearly.iterrows():
        yearly_md += f"| {year} | {int(row['trades'])} | {row['wr%']:.1f}% | {row['E(R)']:+.3f} |\n"

    promising = er >= 0.08 and pf >= 1.25 and (n / tdf["year"].nunique()) >= 40
    verdict   = "**Promising** -- worth proceeding to a full strategy module." if promising \
                else "**Not yet convincing** -- needs further refinement."

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tp_pct  = tp_cnt  / n * 100
    eod_pct = eod_cnt / n * 100

    md = f"""# ORB GAP Mini Test - Results Report

**Strategy:** Opening Range Breakout + GAP filter (LONG only + EMA50 + GAP >= {MIN_GAP_ATR}x ATR + TP={RR}R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** {START} -> {END} (5 years)  
**Timeframe:** 5min  
**Generated:** {now}  

## Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30-15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | {RR}R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| GAP filter | abs(14:30 open - prev 21:00 close) / ATR({ATR_PERIOD}) >= {MIN_GAP_ATR} |
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | {n} |
| Trades/year | {tpy:.1f} |
| Win rate | {wr:.1f}% |
| Expectancy R | {er:+.3f} R |
| Profit factor | {pf:.2f} |
| Max DD (R) | {mdd:.1f} R |
| Avg gap/ATR ratio (traded days) | {meta['avg_gap_ratio']:.3f} |
| Days skipped — GAP filter | {meta['days_filtered_gap']} |
| Days skipped — EMA filter | {meta['days_filtered_ema']} |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | {tp_cnt} | {tp_pct:.1f}% |
| SL | {sl_cnt} | {sl_cnt/n*100:.1f}% |
| EOD | {eod_cnt} | {eod_pct:.1f}% |

## Year-by-Year

{yearly_md}
## Comparison: ORB v3 vs ORB GAP

| Metric | v3 (no GAP filter) | ORB GAP | Delta |
|--------|-------------------|---------|-------|
| Trades | {V3['trades']} | {n} | {n - V3['trades']:+d} |
| Win rate | {V3['wr']:.1f}% | {wr:.1f}% | {wr - V3['wr']:+.1f}pp |
| Expectancy R | {V3['er']:+.3f} | {er:+.3f} | {er - V3['er']:+.3f} |
| Profit factor | {V3['pf']:.2f} | {pf:.2f} | {pf - V3['pf']:+.2f} |
| TP hit rate | {V3['tp_pct']:.1f}% | {tp_pct:.1f}% | {tp_pct - V3['tp_pct']:+.1f}pp |
| EOD exits | {V3['eod_pct']:.1f}% | {eod_pct:.1f}% | {eod_pct - V3['eod_pct']:+.1f}pp |

## Conclusion

{verdict}

**Key observations:**
- GAP filter (>= {MIN_GAP_ATR}x ATR) removed {meta['days_filtered_gap']} days
  - Gap defined as: abs(14:30 UTC open - prev 21:00 UTC close) / ATR(14) on 5m bars
  - P50 of overnight session gap on this dataset: ~6.5x ATR; P62: ~10.0x ATR
- {years_profitable}/5 years profitable
- Average gap/ATR on traded days: {meta['avg_gap_ratio']:.3f}
- Trades/year: {tpy:.1f} (success criterion: >= 40)

## Script

`strategies/OpeningRangeBreakout/research/orb_gap_mini_test.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    tdf, meta = run_orb_gap()
    print_results(tdf, meta)
    save_report(tdf, meta)
