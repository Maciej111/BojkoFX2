# ORB v4 Mini Test - Opening Range Breakout (LONG only + EMA filter + OR width filter)
# Standalone research script under strategies/OpeningRangeBreakout/research/
#
# Changes vs v3:
#   - OR width filter: only trade if min_or_atr <= OR_range/ATR14 <= max_or_atr
#   - TP = 1.6R (same as v3)
#   - Everything else identical to v3
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v4_mini_test.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]   # .../US100
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf                        # noqa: E402
from bojkofx_shared.indicators.atr import calculate_atr              # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
START         = "2021-01-01"
END           = "2025-12-31"
OR_START_MIN  = 14 * 60 + 30
OR_END_MIN    = 15 * 60 + 0
SESSION_END_H = 21
RR_V4         = 1.6
EMA_PERIOD    = 50
ATR_PERIOD    = 14
MIN_OR_ATR    = 0.7
MAX_OR_ATR    = 2.0

# v3 reference stats
V3 = dict(trades=660, wr=52.3, er=+0.065, pf=1.17, rr=1.6,
          tp_pct=14.2, eod_pct=52.9)

REPORT_PATH = Path(__file__).parent / "ORB_v4_mini_test_report.md"


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


def run_orb_v4() -> tuple[pd.DataFrame, dict]:
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    df["ema50_1h"] = build_ema50_1h(df)
    df["atr"]      = calculate_atr(df, period=ATR_PERIOD)
    df["date"]     = df.index.normalize()

    trades: list[dict]  = []
    days_filtered_ema   = 0
    days_filtered_width = 0
    or_ratios_traded: list[float] = []

    for date, day in df.groupby("date"):
        day = day.sort_index()

        # Opening range bars [14:30, 15:00)
        or_mask  = (day.index.map(_bar_minutes) >= OR_START_MIN) & \
                   (day.index.map(_bar_minutes) <  OR_END_MIN)
        or_bars  = day[or_mask]
        if len(or_bars) < 3:
            continue

        or_high = or_bars["high_bid"].max()
        or_low  = or_bars["low_bid"].min()
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        # ATR at end of OR window (last OR bar's ATR value)
        atr_at_or = or_bars["atr"].iloc[-1]
        if pd.isna(atr_at_or) or atr_at_or <= 0:
            continue

        or_atr_ratio = or_range / atr_at_or

        # OR width filter
        if not (MIN_OR_ATR <= or_atr_ratio <= MAX_OR_ATR):
            days_filtered_width += 1
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

            if bar["close_bid"] <= or_high:
                continue

            # EMA filter
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                days_filtered_ema += 1
                break

            remaining = post_bars.iloc[i + 1:]
            if len(remaining) == 0:
                break

            entry_price = remaining.iloc[0]["open_bid"]
            entry_time  = remaining.index[0]
            sl   = or_low
            risk = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + RR_V4 * risk

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

            or_ratios_traded.append(or_atr_ratio)
            trades.append({
                "date":          str(date.date()),
                "entry_time":    entry_time,
                "entry_price":   entry_price,
                "sl":            sl,
                "tp":            tp,
                "risk":          risk,
                "exit_time":     exit_time,
                "exit_price":    exit_price,
                "exit_reason":   exit_reason,
                "R":             round((exit_price - entry_price) / risk, 4),
                "or_atr_ratio":  round(or_atr_ratio, 3),
            })
            trade_taken = True

    meta = dict(
        days_filtered_ema=days_filtered_ema,
        days_filtered_width=days_filtered_width,
        avg_or_atr_ratio=round(float(np.mean(or_ratios_traded)), 3) if or_ratios_traded else 0.0,
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

    SEP = "=" * 54
    print()
    print(SEP)
    print("  ORB v4 MINI TEST - US100 (USATECHIDXUSD)")
    print(SEP)
    print(f"  Period        : {START}  ->  {END}")
    print(f"  Direction     : LONG only")
    print(f"  EMA filter    : close > EMA50 (1h)")
    print(f"  OR width      : {MIN_OR_ATR} <= OR/ATR <= {MAX_OR_ATR}")
    print(f"  TP            : {RR_V4}R  |  SL : OR_low")
    print()
    print(f"  Total trades  : {n}")
    print(f"  Trades/year   : {tpy:.1f}")
    print(f"  Skipped (width filter) : {meta['days_filtered_width']}")
    print(f"  Skipped (EMA filter)   : {meta['days_filtered_ema']}")
    print(f"  Avg OR/ATR (traded)    : {meta['avg_or_atr_ratio']:.3f}")
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
    print(f"  {'Metric':<18}  {'v3':>8}  {'v4':>8}")
    print(f"  {'-'*18}  {'-'*8}  {'-'*8}")
    print(f"  {'Trades':<18}  {V3['trades']:>8}  {n:>8}")
    print(f"  {'Win rate':<18}  {V3['wr']:>7.1f}%  {wr:>7.1f}%")
    print(f"  {'Expectancy R':<18}  {V3['er']:>+8.3f}  {er:>+8.3f}")
    print(f"  {'Profit factor':<18}  {V3['pf']:>8.2f}  {pf:>8.2f}")
    tp_pct_v4  = int(reasons.get("TP",  0)) / n * 100
    eod_pct_v4 = int(reasons.get("EOD", 0)) / n * 100
    print(f"  {'TP hit %':<18}  {V3['tp_pct']:>7.1f}%  {tp_pct_v4:>7.1f}%")
    print(f"  {'EOD exits %':<18}  {V3['eod_pct']:>7.1f}%  {eod_pct_v4:>7.1f}%")
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

    promising = er > 0.08 and pf >= 1.20
    verdict = "**Promising** -- worth proceeding to a full strategy module." if promising \
              else "**Marginal** -- improvement needed before building a full module."

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    md = f"""# ORB v4 Mini Test - Results Report

**Strategy:** Opening Range Breakout v4 (LONG only + EMA50 + OR width filter + TP={RR_V4}R)  
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
| Take profit | {RR_V4}R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| OR width filter | {MIN_OR_ATR} <= OR_range/ATR({ATR_PERIOD}) <= {MAX_OR_ATR} |
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
| Avg OR/ATR ratio (traded days) | {meta['avg_or_atr_ratio']:.3f} |
| Days skipped — OR width filter | {meta['days_filtered_width']} |
| Days skipped — EMA filter | {meta['days_filtered_ema']} |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | {tp_cnt} | {tp_cnt/n*100:.1f}% |
| SL | {sl_cnt} | {sl_cnt/n*100:.1f}% |
| EOD | {eod_cnt} | {eod_cnt/n*100:.1f}% |

## Year-by-Year

{yearly_md}
## Comparison: ORB v3 vs ORB v4

| Metric | v3 (no width filter) | v4 (OR width filter) | Delta |
|--------|---------------------|---------------------|-------|
| Trades | {V3['trades']} | {n} | {n - V3['trades']:+d} |
| Win rate | {V3['wr']:.1f}% | {wr:.1f}% | {wr - V3['wr']:+.1f}pp |
| Expectancy R | {V3['er']:+.3f} | {er:+.3f} | {er - V3['er']:+.3f} |
| Profit factor | {V3['pf']:.2f} | {pf:.2f} | {pf - V3['pf']:+.2f} |
| TP hit rate | {V3['tp_pct']:.1f}% | {tp_cnt/n*100:.1f}% | {tp_cnt/n*100 - V3['tp_pct']:+.1f}pp |
| EOD exits | {V3['eod_pct']:.1f}% | {eod_cnt/n*100:.1f}% | {eod_cnt/n*100 - V3['eod_pct']:+.1f}pp |

## Conclusion

{verdict}

**Key observations:**
- OR width filter ({MIN_OR_ATR}–{MAX_OR_ATR}x ATR) removed {meta['days_filtered_width']} days with extreme OR ranges
- {years_profitable}/5 years profitable
- Average OR/ATR ratio on traded days: {meta['avg_or_atr_ratio']:.3f}

## Script

`strategies/OpeningRangeBreakout/research/orb_v4_mini_test.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    tdf, meta = run_orb_v4()
    print_results(tdf, meta)
    save_report(tdf, meta)
