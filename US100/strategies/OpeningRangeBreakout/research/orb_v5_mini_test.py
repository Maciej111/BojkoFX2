# ORB v5 Mini Test – Bullish Opening Range Filter
# ================================================
# Base: ORB v3 (LONG only + EMA50 1h + TP=1.6R)
# New:  Only trade if OR_close > OR_open (bullish OR)
#
# Usage
# -----
#   cd C:\dev\projects\BojkoFX2\US100
#   .\venv_test\Scripts\python.exe strategies\OpeningRangeBreakout\research\orb_v5_mini_test.py

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "shared"))

from scripts.run_backtest_idx import load_ltf                  # noqa: E402
from bojkofx_shared.indicators.atr import calculate_atr        # noqa: E402

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL        = "usatechidxusd"
TIMEFRAME     = "5min"
START         = "2021-01-01"
END           = "2025-12-31"
OR_START_MIN  = 14 * 60 + 30   # 14:30 UTC
OR_END_MIN    = 15 * 60 + 0    # 15:00 UTC
SESSION_END_H = 21
RR            = 1.6
EMA_PERIOD    = 50

# v3 reference (from ORB_v3_mini_test_report.md)
V3 = dict(trades=660, wr=52.3, er=+0.065, pf=1.17, rr=1.6, tp_pct=14.2, eod_pct=52.9)

REPORT_PATH = Path(__file__).parent / "ORB_v5_mini_test_report.md"


def _bar_minutes(ts) -> int:
    return ts.hour * 60 + ts.minute


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _build_ema50_1h(df5m: pd.DataFrame) -> pd.Series:
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    return _ema(h1, EMA_PERIOD).reindex(df5m.index, method="ffill")


def _max_dd_r(r_series: pd.Series) -> float:
    equity = np.concatenate([[0.0], np.cumsum(r_series.values)])
    peaks  = np.maximum.accumulate(equity)
    return float((peaks - equity).max())


# ── main backtest ─────────────────────────────────────────────────────────────

def run_orb_v5() -> tuple[pd.DataFrame, dict]:
    df = load_ltf(SYMBOL, TIMEFRAME)
    df = df[(df.index >= START) & (df.index < "2026-01-01")].copy()

    df["ema50_1h"] = _build_ema50_1h(df)
    df["date"]     = df.index.normalize()

    trades: list[dict] = []
    days_filtered_bearish_or = 0
    days_filtered_ema        = 0

    for date, day in df.groupby("date"):
        day = day.sort_index()

        # Opening range bars [14:30, 15:00)
        or_mask = (day.index.map(_bar_minutes) >= OR_START_MIN) & \
                  (day.index.map(_bar_minutes) <  OR_END_MIN)
        or_bars = day[or_mask]
        if len(or_bars) < 3:
            continue

        or_open  = or_bars.iloc[0]["open_bid"]
        or_close = or_bars.iloc[-1]["close_bid"]
        or_high  = or_bars["high_bid"].max()
        or_low   = or_bars["low_bid"].min()

        if (or_high - or_low) <= 0:
            continue

        # Bullish OR filter
        if or_close <= or_open:
            days_filtered_bearish_or += 1
            continue

        # Post-OR bars [15:00, 21:00)
        post_mask = (day.index.map(_bar_minutes) >= OR_END_MIN) & \
                    (day.index.hour < SESSION_END_H)
        post_bars = day[post_mask]
        if len(post_bars) < 2:
            continue

        trade_taken = False

        for bar_i, (ts, bar) in enumerate(post_bars.iterrows()):
            if trade_taken:
                break
            if bar["close_bid"] <= or_high:
                continue

            # EMA trend filter
            if pd.isna(bar["ema50_1h"]) or bar["close_bid"] <= bar["ema50_1h"]:
                days_filtered_ema += 1
                break

            remaining = post_bars.iloc[bar_i + 1:]
            if len(remaining) == 0:
                break

            entry_price = remaining.iloc[0]["open_bid"]
            sl          = or_low
            risk        = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + RR * risk

            exit_price  = None
            exit_reason = "EOD"

            for _ts, ebar in remaining.iloc[1:].iterrows():
                if ebar["low_bid"] <= sl:
                    exit_price, exit_reason = sl, "SL"
                    break
                if ebar["high_bid"] >= tp:
                    exit_price, exit_reason = tp, "TP"
                    break

            if exit_price is None:
                eod_cutoff = post_bars.index[0].replace(
                    hour=SESSION_END_H, minute=0, second=0)
                eod_bars   = post_bars[post_bars.index < eod_cutoff]
                if len(eod_bars) == 0:
                    continue
                exit_price  = eod_bars.iloc[-1]["close_bid"]
                exit_reason = "EOD"

            trades.append({
                "date":        str(date.date()),
                "year":        int(date.year),
                "R":           round((exit_price - entry_price) / risk, 4),
                "exit_reason": exit_reason,
                "or_open":     round(or_open,  2),
                "or_close":    round(or_close, 2),
            })
            trade_taken = True

    meta = dict(
        days_filtered_bearish_or=days_filtered_bearish_or,
        days_filtered_ema=days_filtered_ema,
    )
    return pd.DataFrame(trades), meta


# ── output helpers ────────────────────────────────────────────────────────────

def _summary(tdf: pd.DataFrame) -> dict:
    n   = len(tdf)
    tpy = n / tdf["year"].nunique()
    wr  = (tdf["R"] > 0).mean() * 100
    er  = tdf["R"].mean()
    gw  = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl  = abs(tdf.loc[tdf["R"] < 0, "R"].sum())
    pf  = gw / gl if gl > 0 else float("inf")
    mdd = _max_dd_r(tdf["R"])
    vc  = tdf["exit_reason"].value_counts()
    return dict(n=n, tpy=tpy, wr=wr, er=er, pf=pf, mdd=mdd, vc=vc)


def print_results(tdf: pd.DataFrame, meta: dict) -> None:
    if tdf.empty:
        print("No trades generated.")
        return

    s   = _summary(tdf)
    n   = s["n"]
    vc  = s["vc"]
    tp_pct  = int(vc.get("TP",  0)) / n * 100
    eod_pct = int(vc.get("EOD", 0)) / n * 100

    yearly = tdf.groupby("year").apply(
        lambda g: pd.Series({
            "trades": len(g),
            "wr%":    round((g["R"] > 0).mean() * 100, 1),
            "E(R)":   round(g["R"].mean(), 3),
        })
    )

    SEP = "=" * 54
    print()
    print(SEP)
    print("  ORB v5 MINI TEST - US100 (USATECHIDXUSD)")
    print(SEP)
    print(f"  Period         : {START}  ->  {END}")
    print(f"  Direction      : LONG only")
    print(f"  Trend filter   : close > EMA50 (1h)")
    print(f"  OR bias filter : OR_close > OR_open (bullish OR)")
    print(f"  TP             : {RR}R  |  SL : OR_low")
    print()
    print(f"  Total trades   : {n}")
    print(f"  Trades/year    : {s['tpy']:.1f}")
    print(f"  Skipped (bearish OR) : {meta['days_filtered_bearish_or']}")
    print(f"  Skipped (EMA filter) : {meta['days_filtered_ema']}")
    print()
    print(f"  Win rate       : {s['wr']:.1f}%")
    print(f"  Expectancy     : {s['er']:+.3f} R")
    print(f"  Profit factor  : {s['pf']:.2f}")
    print(f"  Max DD (R)     : {s['mdd']:.1f} R")
    print()
    print("  Exit reasons")
    for reason in ["TP", "SL", "EOD"]:
        cnt = int(vc.get(reason, 0))
        print(f"    {reason:<4} : {cnt:>4}  ({cnt/n*100:.1f}%)")
    print()
    print("  Year-by-year")
    print(yearly.to_string())
    print()
    print("  COMPARISON vs ORB v3")
    print(f"  {'Metric':<18}  {'v3':>8}  {'v5':>8}")
    print(f"  {'-'*18}  {'-'*8}  {'-'*8}")
    print(f"  {'Trades':<18}  {V3['trades']:>8}  {n:>8}")
    print(f"  {'Win rate':<18}  {V3['wr']:>7.1f}%  {s['wr']:>7.1f}%")
    print(f"  {'Expectancy R':<18}  {V3['er']:>+8.3f}  {s['er']:>+8.3f}")
    print(f"  {'Profit factor':<18}  {V3['pf']:>8.2f}  {s['pf']:>8.2f}")
    print(f"  {'TP hit %':<18}  {V3['tp_pct']:>7.1f}%  {tp_pct:>7.1f}%")
    print(f"  {'EOD exits %':<18}  {V3['eod_pct']:>7.1f}%  {eod_pct:>7.1f}%")
    print(SEP)
    print()


def save_report(tdf: pd.DataFrame, meta: dict) -> None:
    if tdf.empty:
        return

    s   = _summary(tdf)
    n   = s["n"]
    vc  = s["vc"]
    tp_cnt  = int(vc.get("TP",  0))
    sl_cnt  = int(vc.get("SL",  0))
    eod_cnt = int(vc.get("EOD", 0))
    tp_pct  = tp_cnt  / n * 100
    eod_pct = eod_cnt / n * 100

    yearly = tdf.groupby("year").apply(
        lambda g: pd.Series({
            "trades": len(g),
            "wr%":    round((g["R"] > 0).mean() * 100, 1),
            "E(R)":   round(g["R"].mean(), 3),
        })
    )
    yearly_md  = "| Year | Trades | WR% | E(R) |\n|------|--------|-----|------|\n"
    for year, row in yearly.iterrows():
        yearly_md += f"| {year} | {int(row['trades'])} | {row['wr%']:.1f}% | {row['E(R)']:+.3f} |\n"

    years_pos = sum(1 for _, r in yearly.iterrows() if r["E(R)"] > 0)
    meets = s["er"] >= 0.08 and s["pf"] >= 1.20 and s["tpy"] >= 60
    verdict = "**Promising** — worth further investigation." if meets \
              else "**Not convincing** — bullish OR filter does not materially improve ORB v3."

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    md = f"""# ORB v5 Mini Test – Bullish OR Filter

**Strategy:** Opening Range Breakout + Bullish OR bias (LONG only + EMA50 + OR_close > OR_open + TP={RR}R)  
**Symbol:** USATECHIDXUSD (US100)  
**Period:** {START} -> {END} (5 years)  
**Timeframe:** 5min  
**Generated:** {now}

## Rules

| Parameter | Value |
|-----------|-------|
| OR window | 14:30–15:00 UTC |
| Direction | LONG only |
| Entry | Next bar open after close breaks above OR_high |
| Stop loss | OR_low |
| Take profit | {RR}R |
| EOD close | 21:00 UTC |
| Trend filter | close_bid > EMA50 (1h bars) |
| OR bias filter | OR_close > OR_open (first bar open vs last bar close of OR window) |
| Max trades/day | 1 |

## Summary Results

| Metric | Value |
|--------|-------|
| Total trades | {n} |
| Trades/year | {s['tpy']:.1f} |
| Win rate | {s['wr']:.1f}% |
| Expectancy R | {s['er']:+.3f} R |
| Profit factor | {s['pf']:.2f} |
| Max DD (R) | {s['mdd']:.1f} R |
| Days skipped — bearish OR | {meta['days_filtered_bearish_or']} |
| Days skipped — EMA filter | {meta['days_filtered_ema']} |

## Exit Reason Breakdown

| Exit | Count | % |
|------|-------|---|
| TP | {tp_cnt} | {tp_pct:.1f}% |
| SL | {sl_cnt} | {sl_cnt/n*100:.1f}% |
| EOD | {eod_cnt} | {eod_pct:.1f}% |

## Year-by-Year

{yearly_md}
## Comparison: ORB v3 vs ORB v5

| Metric | v3 (no OR filter) | v5 (bullish OR) | Delta |
|--------|-------------------|-----------------|-------|
| Trades | {V3['trades']} | {n} | {n - V3['trades']:+d} |
| Win rate | {V3['wr']:.1f}% | {s['wr']:.1f}% | {s['wr'] - V3['wr']:+.1f}pp |
| Expectancy R | {V3['er']:+.3f} | {s['er']:+.3f} | {s['er'] - V3['er']:+.3f} |
| Profit factor | {V3['pf']:.2f} | {s['pf']:.2f} | {s['pf'] - V3['pf']:+.2f} |
| TP hit rate | {V3['tp_pct']:.1f}% | {tp_pct:.1f}% | {tp_pct - V3['tp_pct']:+.1f}pp |
| EOD exits | {V3['eod_pct']:.1f}% | {eod_pct:.1f}% | {eod_pct - V3['eod_pct']:+.1f}pp |

## Conclusion

{verdict}

**Key observations:**
- Bullish OR filter removed {meta['days_filtered_bearish_or']} days
- {years_pos}/5 years profitable
- Success criteria: E(R) > +0.08R, PF >= 1.20, Trades/year >= 60

## Script

`strategies/OpeningRangeBreakout/research/orb_v5_mini_test.py`
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(md, encoding="utf-8")
    print(f"Report saved: {REPORT_PATH}")


if __name__ == "__main__":
    tdf, meta = run_orb_v5()
    print_results(tdf, meta)
    save_report(tdf, meta)
