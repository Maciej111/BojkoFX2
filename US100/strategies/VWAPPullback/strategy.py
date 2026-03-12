"""
VWAPPullback — core strategy logic.

Public API
----------
compute_daily_vwap(df)          -> pd.Series    (add vwap column)
build_ema_htf(df5m, period)     -> pd.Series    (1h EMA, forward-filled to 5m index)
prepare_data(df, cfg)           -> pd.DataFrame (adds vwap, atr, ema_htf, date columns)
run_backtest(df_prep, cfg)      -> (trades_df, meta_dict)
compute_metrics(trades_df)      -> dict
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── resolve project roots ─────────────────────────────────────────────────────
_STRATEGY_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT  = _STRATEGY_DIR.parent.parent        # …/US100
_SHARED_ROOT   = _PROJECT_ROOT.parent / "shared"    # …/shared

for _p in [str(_PROJECT_ROOT), str(_SHARED_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bojkofx_shared.indicators.atr import calculate_atr  # noqa: E402

from strategies.VWAPPullback.config import VWAPPullbackConfig, VWAPPullbackV2Config  # noqa: E402


# ── VWAP ──────────────────────────────────────────────────────────────────────

def compute_daily_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Intraday VWAP anchored at midnight UTC, reset each calendar day.

    No volume available for NAS100 CFD bars — uses equal-weight cumulative
    average of typical price (identical to price-anchored VWAP):
        TP[i]   = (high_bid[i] + low_bid[i] + close_bid[i]) / 3
        VWAP[i] = mean(TP[0 .. i])  within each day
    """
    parts: list[pd.Series] = []
    for _date, day in df.groupby(df.index.normalize()):
        day  = day.sort_index()
        tp   = (day["high_bid"] + day["low_bid"] + day["close_bid"]) / 3.0
        vwap = tp.expanding().mean()
        parts.append(vwap)
    return pd.concat(parts).sort_index()


# ── EMA on 1h bars ────────────────────────────────────────────────────────────

def build_ema_htf(df5m: pd.DataFrame, period: int) -> pd.Series:
    """EMA(period) on hourly close_bid, forward-filled back to the 5m index."""
    h1 = df5m["close_bid"].resample("1h").last().dropna()
    return h1.ewm(span=period, adjust=False).mean().reindex(df5m.index, method="ffill")


# ── Data preparation ──────────────────────────────────────────────────────────

def prepare_data(df: pd.DataFrame, cfg: VWAPPullbackConfig) -> pd.DataFrame:
    """
    Add indicator columns to a 5m bars DataFrame.

    Adds: vwap, atr, ema_htf, date
    """
    df = df.copy()
    df["vwap"]    = compute_daily_vwap(df)
    df["atr"]     = calculate_atr(df, period=cfg.atr_period)
    df["ema_htf"] = build_ema_htf(df, cfg.ema_period_htf)
    df["date"]    = df.index.normalize()
    return df


# ── Backtest ──────────────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    cfg: VWAPPullbackConfig,
) -> tuple[pd.DataFrame, dict]:
    """
    VWAP Pullback backtest on a prepared 5m DataFrame.

    df must have columns: open_bid, high_bid, low_bid, close_bid,
                          vwap, atr, ema_htf, date

    Strategy rules (LONG only, max 1 trade/day by default):
      1. Trend filter: close_bid > ema_htf
      2. Prior regime: last N bars all closed above VWAP
      3. Pullback: current bar's low_bid <= vwap + tolerance*ATR
      4. Confirmation: bullish candle (close > open), close > VWAP,
                       body ratio >= min_body_ratio
      5. Entry: next bar open
      6. SL: pullback_low - stop_buffer*ATR
      7. TP: entry + RR * risk
      8. EOD: close at session_end_hour_utc if neither SL nor TP hit
    """
    trades: list[dict] = []
    meta = {"days_total": 0, "days_no_setup": 0}

    for date, day in df.groupby("date"):
        day  = day.sort_index()
        meta["days_total"] += 1
        day_trades  = 0
        bars_list   = [(ts, row) for ts, row in day.iterrows()]
        n           = len(bars_list)

        for i, (ts, bar) in enumerate(bars_list):
            if day_trades >= cfg.max_trades_per_day:
                break

            # session filter: ignore bars outside US day session
            if ts.hour < cfg.session_start_hour_utc:
                continue
            if ts.hour >= cfg.session_end_hour_utc:
                break

            # need at least one more bar for entry
            if i + 1 >= n:
                break

            atr  = bar["atr"]
            vwap = bar["vwap"]
            if np.isnan(atr) or atr <= 0 or np.isnan(vwap):
                continue

            # ── 1. EMA trend filter ───────────────────────────────────────────
            if cfg.ema_filter_enabled:
                ema_v = bar["ema_htf"]
                if np.isnan(ema_v) or bar["close_bid"] <= ema_v:
                    continue

            # ── 2. Prior bullish regime ───────────────────────────────────────
            n_req = cfg.min_bars_above_vwap
            if n_req > 0:
                if i < n_req:
                    continue
                prior = [bars_list[i - k - 1][1] for k in range(n_req)]
                if not all(r["close_bid"] > r["vwap"] for r in prior):
                    continue

            # ── 3. Pullback: low touched within tolerance of VWAP ────────────
            if bar["low_bid"] > vwap + cfg.vwap_tolerance_atr_mult * atr:
                continue

            # ── 4. Bullish confirmation ───────────────────────────────────────
            bar_range = bar["high_bid"] - bar["low_bid"]
            if bar_range <= 0:
                continue
            bar_body  = bar["close_bid"] - bar["open_bid"]
            if bar_body <= 0:
                continue  # bearish candle — not a confirmation
            if cfg.require_close_above_vwap and bar["close_bid"] <= vwap:
                continue
            if (bar_body / bar_range) < cfg.min_body_ratio:
                continue

            # ── 5. Entry on next bar open ─────────────────────────────────────
            _, entry_row  = bars_list[i + 1]
            entry_price   = entry_row["open_bid"]
            sl            = bar["low_bid"] - cfg.stop_buffer_atr_mult * atr
            risk          = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + cfg.take_profit_rr * risk

            # ── 6. Exit resolution ─────────────────────────────────────────────
            exit_price  = entry_row["close_bid"]   # fallback: use entry bar close
            exit_reason = "EOD"

            for j in range(i + 2, n):
                ts2, ebar = bars_list[j]
                if ts2.hour >= cfg.session_end_hour_utc:
                    break
                exit_price = ebar["close_bid"]      # keep updating EOD fallback
                if ebar["low_bid"] <= sl:
                    exit_price, exit_reason = sl, "SL"
                    break
                if ebar["high_bid"] >= tp:
                    exit_price, exit_reason = tp, "TP"
                    break

            R = round((exit_price - entry_price) / risk, 4)
            trades.append({
                "date":        str(date.date()),
                "year":        int(date.year),
                "R":           R,
                "exit_reason": exit_reason,
                "entry_price": round(entry_price, 2),
                "sl":          round(sl, 2),
                "tp":          round(tp, 2),
                "vwap_at_signal": round(vwap, 2),
                "atr_at_signal":  round(atr, 2),
            })
            day_trades += 1

        if day_trades == 0:
            meta["days_no_setup"] += 1

    return pd.DataFrame(trades), meta


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_metrics(trades_df: pd.DataFrame) -> dict:
    """R-based metrics — same style as ORB research scripts."""
    if trades_df.empty:
        return dict(n=0, tpy=0.0, wr=0.0, er=0.0, pf=0.0, mdd=0.0,
                    avg_r=0.0, std_r=0.0, mcl=0, tp_pct=0.0, eod_pct=0.0, sl_pct=0.0)

    arr   = trades_df["R"].to_numpy(dtype=float)
    exits = trades_df["exit_reason"].tolist()
    years = len(trades_df["year"].unique())
    n     = len(arr)
    gw    = float(arr[arr > 0].sum())
    gl    = float(abs(arr[arr < 0].sum()))

    # max drawdown
    eq    = np.concatenate([[0.0], np.cumsum(arr)])
    mdd   = float((np.maximum.accumulate(eq) - eq).max())

    # max consecutive losses
    mx, cur = 0, 0
    for x in arr:
        if x < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0

    return dict(
        n      = n,
        tpy    = round(n / years, 1),
        wr     = round(float((arr > 0).mean()) * 100, 1),
        er     = round(float(arr.mean()), 3),
        pf     = round(gw / gl if gl > 0 else float("inf"), 2),
        mdd    = round(mdd, 1),
        avg_r  = round(float(arr.mean()), 4),
        std_r  = round(float(arr.std()), 4),
        mcl    = mx,
        tp_pct  = round(exits.count("TP")  / n * 100, 1),
        sl_pct  = round(exits.count("SL")  / n * 100, 1),
        eod_pct = round(exits.count("EOD") / n * 100, 1),
    )


# ── Session VWAP (v2) ─────────────────────────────────────────────────────────

def compute_session_vwap(
    df: pd.DataFrame,
    open_hour: int = 14,
    open_minute: int = 30,
) -> pd.Series:
    """
    Session VWAP anchored at the US session open (default 14:30 UTC).

    For each calendar day:
      - Bars before session open  -> NaN
      - VWAP = expanding cumulative mean of TP from the first session bar

    TP = (high_bid + low_bid + close_bid) / 3
    No volume available for NAS100 CFD -- equal-weight, same as v1.
    """
    result = pd.Series(np.nan, index=df.index, dtype=float)

    for _date, day in df.groupby(df.index.normalize()):
        day = day.sort_index()
        session_mask = (day.index.hour > open_hour) | (
            (day.index.hour == open_hour) & (day.index.minute >= open_minute)
        )
        session_bars = day.loc[session_mask]
        if session_bars.empty:
            continue
        tp = (
            session_bars["high_bid"]
            + session_bars["low_bid"]
            + session_bars["close_bid"]
        ) / 3.0
        result.loc[session_bars.index] = tp.expanding().mean().values

    return result


# ── Data preparation (v2) ─────────────────────────────────────────────────────

def prepare_data_v2(
    df: pd.DataFrame,
    cfg: VWAPPullbackV2Config,
) -> pd.DataFrame:
    """
    Add indicator columns for VWAPPullback v2.

    Adds: vwap (session-anchored at 14:30 UTC), atr, ema_htf, date
    """
    df = df.copy()
    df["vwap"]    = compute_session_vwap(df, cfg.session_open_hour, cfg.session_open_minute)
    df["atr"]     = calculate_atr(df, period=cfg.atr_period)
    df["ema_htf"] = build_ema_htf(df, cfg.ema_period_htf)
    df["date"]    = df.index.normalize()
    return df


# ── Backtest (v2) ─────────────────────────────────────────────────────────────

def run_backtest_v2(
    df: pd.DataFrame,
    cfg: VWAPPullbackV2Config,
) -> tuple[pd.DataFrame, dict]:
    """
    VWAPPullback v2 backtest.

    Key rule differences vs v1 (run_backtest):
      - Pullback: strict VWAP touch -- low_bid <= vwap  (no ATR buffer)
      - Confirmation: close > open AND close > vwap  (no body_ratio check)
      - Session VWAP: NaN before 14:30 UTC -- signals only after session open
      - max_trades_per_day = 2 by default

    df must have columns: open_bid, high_bid, low_bid, close_bid,
                          vwap, atr, ema_htf, date
    """
    trades: list[dict] = []
    meta = {"days_total": 0, "days_no_setup": 0}

    open_h = cfg.session_open_hour
    open_m = cfg.session_open_minute

    for date, day in df.groupby("date"):
        day = day.sort_index()
        meta["days_total"] += 1
        day_trades = 0
        bars_list  = [(ts, row) for ts, row in day.iterrows()]
        n          = len(bars_list)

        for i, (ts, bar) in enumerate(bars_list):
            if day_trades >= cfg.max_trades_per_day:
                break

            # session filter: skip bars before session open
            in_session = (ts.hour > open_h) or (
                ts.hour == open_h and ts.minute >= open_m
            )
            if not in_session:
                continue
            if ts.hour >= cfg.session_close_hour:
                break

            # need at least one more bar for entry
            if i + 1 >= n:
                break

            atr  = bar["atr"]
            vwap = bar["vwap"]
            if np.isnan(atr) or atr <= 0 or np.isnan(vwap):
                continue

            # ── 1. EMA trend filter ───────────────────────────────────────────
            if cfg.ema_filter_enabled:
                ema_v = bar["ema_htf"]
                if np.isnan(ema_v) or bar["close_bid"] <= ema_v:
                    continue

            # ── 2. Prior bullish regime (optional, default disabled) ──────────
            n_req = cfg.min_bars_above_vwap
            if n_req > 0:
                if i < n_req:
                    continue
                prior = [bars_list[i - k - 1][1] for k in range(n_req)]
                if not all(
                    (not np.isnan(r["vwap"])) and r["close_bid"] > r["vwap"]
                    for r in prior
                ):
                    continue

            # ── 3. Strict VWAP touch: low_bid <= vwap ─────────────────────────
            if bar["low_bid"] > vwap:
                continue

            # ── 4. Bullish confirmation: close > open AND close > vwap ────────
            if bar["close_bid"] <= bar["open_bid"]:
                continue  # bearish candle
            if cfg.require_close_above_vwap and bar["close_bid"] <= vwap:
                continue

            # ── 5. Entry on next bar open ─────────────────────────────────────
            _, entry_row = bars_list[i + 1]
            entry_price  = entry_row["open_bid"]
            sl           = bar["low_bid"] - cfg.stop_buffer_atr_mult * atr
            risk         = entry_price - sl
            if risk <= 0:
                continue
            tp = entry_price + cfg.take_profit_rr * risk

            # ── 6. Exit resolution ────────────────────────────────────────────
            exit_price  = entry_row["close_bid"]
            exit_reason = "EOD"

            for j in range(i + 2, n):
                ts2, ebar = bars_list[j]
                if ts2.hour >= cfg.session_close_hour:
                    break
                exit_price = ebar["close_bid"]
                if ebar["low_bid"] <= sl:
                    exit_price, exit_reason = sl, "SL"
                    break
                if ebar["high_bid"] >= tp:
                    exit_price, exit_reason = tp, "TP"
                    break

            R = round((exit_price - entry_price) / risk, 4)
            trades.append({
                "date":           str(date.date()),
                "year":           int(date.year),
                "R":              R,
                "exit_reason":    exit_reason,
                "entry_price":    round(entry_price, 2),
                "sl":             round(sl, 2),
                "tp":             round(tp, 2),
                "vwap_at_signal": round(vwap, 2),
                "atr_at_signal":  round(atr, 2),
            })
            day_trades += 1

        if day_trades == 0:
            meta["days_no_setup"] += 1

    return pd.DataFrame(trades), meta
