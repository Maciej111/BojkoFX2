# ORB v2 Mini Test - Opening Range Breakout (LONG only + EMA filter)
# Standalone research script under strategies/OpeningRangeBreakout/research/
#
# Changes vs v1 (research/orb_mini_test.py):
#   1. LONG only  -- SHORT removed entirely
#   2. EMA50 1h trend filter -- only enter if close_bid > EMA50 on 1h bars
#   3. TP = 1.3R  -- closer target vs 2.0R in v1
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v2_mini_test.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]   # …/US100
sys.path.insert(0, str(ROOT))

from scripts.run_backtest_idx import load_ltf  # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
START         = "2021-01-01"
END           = "2025-12-31"
OR_START_MIN  = 14 * 60 + 30   # 14:30 UTC in minutes
OR_END_MIN    = 15 * 60 + 0    # 15:00 UTC
SESSION_END_H = 21
RR_V2         = 1.3
EMA_PERIOD    = 50

# v1 reference stats (from ORB_MINI_TEST_RESULTS_2026-03-12.md — LONG only slice)
V1_LONG = dict(trades=672, wr=50.3, er=+0.072, pf=None)

REPORT_PATH = Path(__file__).parent / "ORB_v2_mini_test_report.md"


def _calc_max_dd_r(r_series: pd.Series) -> float:
    equity = np.concatenate([[0.0], np.cumsum(r_series.values)])
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def build_ema50_1h(df5m: pd.DataFrame) -> pd.Series:
    """Resample 5m bars to 1h, compute EMA50 on close_bid, forward-fill to 5m index."""
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    ema = _ema(h1, EMA_PERIOD)
    # Reindex to 5m and forward-fill so each 5m bar knows the last confirmed 1h EMA
    ema_5m = ema.reindex(df5m.index, method="ffill")
    return ema_5m


def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


def run_orb_v2() -> tuple[pd.DataFrame, dict]:
    # ── 1. Load and slice data ────────────────────────────────────────────────
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    # ── 2. Build EMA50 on 1h, aligned to 5m index ────────────────────────────
    df["ema50_1h"] = build_ema50_1h(df)
    df["date"] = df.index.normalize()

    trades: list[dict] = []
    days_no_breakout = 0
    days_filtered_ema = 0

    for date, day in df.groupby("date"):
        day = day.sort_index()

        # Opening range bars [14:30, 15:00)
        or_mask = (day.index.map(_bar_minutes) >= OR_START_MIN) & \
                  (day.index.map(_bar_minutes) <  OR_END_MIN)
        or_bars = day[or_mask]

        if len(or_bars) < 3:
            continue

        or_high  = or_bars["high_bid"].max()
        or_low   = or_bars["low_bid"].min()
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        # Post-OR bars [15:00, 21:00)
        post_mask = (day.index.map(_bar_minutes) >= OR_END_MIN) & \
                    (day.index.hour < SESSION_END_H)
        post_bars = day[post_mask]
        if len(post_bars) < 2:
            continue

        trade_taken = False

        for i, (ts, bar) in enumerate(post_bars.iterrows()):
            if trade_taken:
                break

            # LONG only: close must break above OR_high
            if bar["close_bid"] <= or_high:
                continue

            # EMA filter: close must be above EMA50 1h
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                days_filtered_ema += 1
                break   # only first breakout per day; if filtered, skip day

            # Entry on next bar open
            remaining = post_bars.iloc[i + 1:]
            if len(remaining) == 0:
                break

            entry_bar   = remaining.iloc[0]
            entry_time  = remaining.index[0]
            entry_price = entry_bar["open_bid"]

            sl   = or_low
            risk = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + RR_V2 * risk

            # Simulate trade
            exit_price  = None
            exit_reason = "EOD"
            exit_time   = None

            for ets, ebar in remaining.iloc[1:].iterrows():
                h = ebar["high_bid"]
                l = ebar["low_bid"]
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

            # EOD close
            if exit_price is None:
                eod_cutoff = post_bars.index[0].replace(hour=SESSION_END_H, minute=0, second=0)
                eod_bars   = post_bars[post_bars.index < eod_cutoff]
                if len(eod_bars) == 0:
                    continue
                exit_price  = eod_bars.iloc[-1]["close_bid"]
                exit_time   = eod_bars.index[-1]
                exit_reason = "EOD"

            r_val = (exit_price - entry_price) / risk

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
                "R":           round(r_val, 4),
                "ema50_1h":    round(bar["ema50_1h"], 2),
                "or_high":     or_high,
                "or_low":      or_low,
            })
            trade_taken = True

    meta = dict(days_filtered_ema=days_filtered_ema)
    return pd.DataFrame(trades), meta


def print_and_report(tdf: pd.DataFrame, meta: dict) -> str:
    if tdf.empty:
        print("No trades generated.")
        return ""

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

    SEP = "=" * 52

    lines = [
        "",
        SEP,
        "  ORB v2 MINI TEST - US100 (USATECHIDXUSD)",
        SEP,
        f"  Period        : {START}  ->  {END}",
        f"  OR window     : 14:30-15:00 UTC",
        f"  Direction     : LONG only",
        f"  EMA filter    : close > EMA50 (1h)",
        f"  TP            : {RR_V2}R",
        f"  SL            : OR_low",
        f"  EOD close     : 21:00 UTC",
        "",
        f"  Total trades  : {n}",
        f"  Trades/year   : {tpy:.1f}",
        f"  EMA-filtered  : {meta['days_filtered_ema']} breakout days skipped",
        "",
        f"  Win rate      : {wr:.1f}%",
        f"  Expectancy    : {er:+.3f} R",
        f"  Profit factor : {pf:.2f}",
        f"  Max DD (R)    : {mdd:.1f} R",
        "",
        "  Exit reasons",
    ]
    for reason in ["TP", "SL", "EOD"]:
        cnt = int(reasons.get(reason, 0))
        pct = cnt / n * 100 if n > 0 else 0
        lines.append(f"    {reason:<4} : {cnt:>4}  ({pct:.1f}%)")

    lines += [
        "",
        "  Year-by-year",
        yearly.to_string(),
        "",
        "  COMPARISON vs ORB v1 (LONG slice from v1 run)",
        f"  {'Metric':<16}  {'v1 LONG':>10}  {'v2 LONG':>10}",
        f"  {'-'*16}  {'-'*10}  {'-'*10}",
        f"  {'Trades':<16}  {V1_LONG['trades']:>10}  {n:>10}",
        f"  {'Win rate':<16}  {V1_LONG['wr']:>9.1f}%  {wr:>9.1f}%",
        f"  {'Expectancy R':<16}  {V1_LONG['er']:>+10.3f}  {er:>+10.3f}",
        f"  {'TP (RR)':<16}  {'2.0R':>10}  {RR_V2}R",
        SEP,
        "",
    ]

    output = "\n".join(lines)
    print(output)
    return output


def save_report(tdf: pd.DataFrame, meta: dict, console_output: str) -> None:
    if tdf.empty:
        return

    tdf["year"] = pd.to_datetime(tdf["date"]).dt.year
    n   = len(tdf)
    tpy = n / tdf["year"].nunique()
    wr  = (tdf["R"] > 0).mean() * 100
    er  = tdf["R"].mean()
    gw  = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl  = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    pf  = gw / gl if gl > 0 else float("inf")
    mdd = _calc_max_dd_r(tdf["R"])
    reasons = tdf["exit_reason"].value_counts()

    yearly = tdf.groupby("year").apply(
        lambda g: pd.Series({
            "trades": int(len(g)),
            "wr%":    round((g["R"] > 0).mean() * 100, 1),
            "E(R)":   round(g["R"].mean(), 3),
        })
    )

    tp_cnt  = int(reasons.get("TP",  0))
    sl_cnt  = int(reasons.get("SL",  0))
    eod_cnt = int(reasons.get("EOD", 0))

    promising = er > 0.07 and pf >= 1.15
    verdict = "**Promising** -- worth building a full strategy module." if promising \
              else "**Marginal / not yet convincing** -- needs further refinement before proceeding."

    yearly_md = "| Year | Trades | WR% | E(R) |\n|------|--------|-----|------|\n"
    for year, row in yearly.iterrows():
        yearly_md += f"| {year} | {int(row['trades'])} | {row['wr%']:.1f}% | {row['E(R)']:+.3f} |\n"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    md = f"""# ORB v2 Mini Test - Results Report

**Strategy:** Opening Range Breakout v2 (LONG only + EMA filter + TP=1.3R)  
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
| Take profit | {RR_V2}R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
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
| EMA-filtered days | {meta['days_filtered_ema']} |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | {tp_cnt} | {tp_cnt/n*100:.1f}% |
| SL | {sl_cnt} | {sl_cnt/n*100:.1f}% |
| EOD | {eod_cnt} | {eod_cnt/n*100:.1f}% |

## Year-by-Year

{yearly_md}
## Comparison: ORB v1 LONG vs ORB v2

| Metric | v1 LONG | v2 LONG | Delta |
|--------|---------|---------|-------|
| Trades | {V1_LONG['trades']} | {n} | {n - V1_LONG['trades']:+d} |
| Win rate | {V1_LONG['wr']:.1f}% | {wr:.1f}% | {wr - V1_LONG['wr']:+.1f}pp |
| Expectancy R | {V1_LONG['er']:+.3f} | {er:+.3f} | {er - V1_LONG['er']:+.3f} |
| TP (RR) | 2.0R | {RR_V2}R | -- |
| EOD exits | 51.5% | {eod_cnt/n*100:.1f}% | {eod_cnt/n*100 - 51.5:+.1f}pp |

## Conclusion

{verdict}

**Key observations:**
- EMA50 filter eliminated {meta['days_filtered_ema']} LONG breakout days that occurred in downtrends
- Closer TP ({RR_V2}R vs 2.0R) {"improved" if tp_cnt/n > 0.117 else "did not improve"} TP hit rate ({tp_cnt/n*100:.1f}% vs 11.7% in v1)
- EOD closes {"reduced" if eod_cnt/n < 0.515 else "increased"} from 51.5% to {eod_cnt/n*100:.1f}%
- Year-by-year consistency: {sum(1 for _, r in yearly.iterrows() if r['E(R)'] > 0)}/5 years profitable

## Script

`strategies/OpeningRangeBreakout/research/orb_v2_mini_test.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    tdf, meta = run_orb_v2()
    console_out = print_and_report(tdf, meta)
    save_report(tdf, meta, console_out)
