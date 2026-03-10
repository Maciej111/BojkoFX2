"""
Backtest runner for index instruments (US100 / USATECHIDXUSD).

Loads pre-built bars from data/bars_idx/, resamples to HTF,
then runs the BOS+Pullback strategy.

Saves:
  reports/IDX_<SYMBOL>_<LTF>_BACKTEST_TRADES.csv
  reports/IDX_<SYMBOL>_<LTF>_BACKTEST_REPORT.md

Usage:
    python -m scripts.run_backtest_idx
    python -m scripts.run_backtest_idx --start 2022-01-01 --end 2024-12-31
    python -m scripts.run_backtest_idx --ltf 30min --htf 4h
    python -m scripts.run_backtest_idx --ltf 1h --htf 4h --rr 3.0
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.strategies.trend_following_v1 import run_trend_backtest

BARS_IDX_DIR = ROOT / "data" / "bars_idx"
REPORTS_DIR  = ROOT / "reports"


def _tf_label(tf: str) -> str:
    """Normalize timeframe string to a short filename-safe label."""
    return tf.replace("min", "m").replace("T", "m").replace(" ", "")


def load_ltf(symbol: str, ltf: str = "1h") -> pd.DataFrame:
    """Load LTF bars CSV built by build_h1_idx.py."""
    tf = _tf_label(ltf)
    path = BARS_IDX_DIR / f"{symbol}_{tf}_bars.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Bars not found: {path}\n"
            f"Run:  python -m scripts.build_h1_idx --symbol {symbol} --timeframe {ltf}"
        )
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    print(f"Loaded {tf} bars: {len(df):,}  [{df.index[0]} → {df.index[-1]}]")
    return df


# Keep old name for backward compatibility
def load_h1(symbol: str) -> pd.DataFrame:
    return load_ltf(symbol, "1h")


def build_htf_from_ltf(ltf_df: pd.DataFrame, htf: str = "4h") -> pd.DataFrame:
    """Resample LTF bars → HTF, no-lookahead."""
    htf_df = ltf_df.resample(htf, closed="left", label="left").agg({
        "open_bid":  "first",
        "high_bid":  "max",
        "low_bid":   "min",
        "close_bid": "last",
        "open_ask":  "first",
        "high_ask":  "max",
        "low_ask":   "min",
        "close_ask": "last",
    }).dropna(how="all")
    htf_df = htf_df[htf_df["open_bid"].notna()]
    print(f"Built {_tf_label(htf)} (HTF) bars: {len(htf_df):,}")
    return htf_df


# Keep old name for backward compatibility
def build_h4_from_h1(h1: pd.DataFrame) -> pd.DataFrame:
    return build_htf_from_ltf(h1, "4h")


def filter_by_date(df: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index <= pd.Timestamp(end, tz="UTC")]
    return df


def _calc_r_drawdown(trades_df: pd.DataFrame) -> float:
    """Compute max drawdown in R units (independent of dollar PNL multiplier)."""
    if trades_df is None or len(trades_df) == 0:
        return 0.0
    equity_r = [0.0]
    for r in trades_df["R"]:
        equity_r.append(equity_r[-1] + r)
    peak = equity_r[0]
    max_dd = 0.0
    for val in equity_r:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
    return max_dd


def build_report_md(symbol: str, metrics: dict, trades_df: pd.DataFrame,
                    start: str, end: str, params: dict, ltf: str = "1h", htf: str = "4h") -> str:
    n = metrics.get("trades_count", 0)
    wr = metrics.get("win_rate", 0)   # already in % (e.g. 48.5)
    er = metrics.get("expectancy_R", 0)
    pf = metrics.get("profit_factor", 0)
    streak = metrics.get("max_losing_streak", 0)
    total_setups = metrics.get("total_setups", 0)
    missed_rate = metrics.get("missed_rate", 0)  # decimal 0-1
    r_dd = _calc_r_drawdown(trades_df)

    long_trades  = trades_df[trades_df["direction"] == "LONG"]  if len(trades_df) else pd.DataFrame()
    short_trades = trades_df[trades_df["direction"] == "SHORT"] if len(trades_df) else pd.DataFrame()

    tp_count = (trades_df["exit_reason"] == "TP").sum() if len(trades_df) else 0
    sl_count = (trades_df["exit_reason"].str.startswith("SL")).sum() if len(trades_df) else 0

    lines = [
        f"# Index Backtest Report: {symbol.upper()}",
        f"",
        f"**Period:** {start} → {end}",
        f"**LTF:** {_tf_label(ltf)}  |  **HTF:** {_tf_label(htf)}",
        f"**Strategy:** BOS + Pullback (trend_following_v1)",
        f"",
        f"## Strategy Parameters",
        f"",
        f"| Parameter | Value |",
        f"|-----------|-------|",
    ]
    for k, v in params.items():
        lines.append(f"| {k} | {v} |")

    lines += [
        f"",
        f"## Results Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total trades | {n} |",
        f"| Win rate | {wr:.1f}% |",
        f"| Expectancy (R) | {er:.3f} |",
        f"| Profit factor | {pf:.2f} |",
        f"| Max R-drawdown | {r_dd:.2f}R |",
        f"| Max losing streak | {streak} |",
        f"| Total setups detected | {total_setups} |",
        f"| Missed rate | {missed_rate * 100:.1f}% |",
        f"| TP exits | {tp_count} |",
        f"| SL exits | {sl_count} |",
        f"",
    ]

    if len(trades_df):
        lines += [
            f"## Trade Direction Breakdown",
            f"",
            f"| Direction | Trades | Win Rate | Avg R |",
            f"|-----------|--------|----------|-------|",
        ]
        for label, subset in [("LONG", long_trades), ("SHORT", short_trades)]:
            if len(subset):
                subset_wr = (subset["R"] > 0).mean()
                avg_r = subset["R"].mean()
                lines.append(f"| {label} | {len(subset)} | {subset_wr:.1%} | {avg_r:.3f} |")

        lines += [
            f"",
            f"## R Distribution",
            f"",
            f"| Bucket | Count |",
            f"|--------|-------|",
        ]
        buckets = [
            ("< -1R",   trades_df["R"] < -1),
            ("-1R to 0", (trades_df["R"] >= -1) & (trades_df["R"] < 0)),
            ("0 to 1R",  (trades_df["R"] >= 0) & (trades_df["R"] < 1)),
            ("1R to 2R", (trades_df["R"] >= 1) & (trades_df["R"] < 2)),
            ("2R to 3R", (trades_df["R"] >= 2) & (trades_df["R"] < 3)),
            (">= 3R",    trades_df["R"] >= 3),
        ]
        for label, mask in buckets:
            lines.append(f"| {label} | {mask.sum()} |")

    return "\n".join(lines)


def run_backtest(
    symbol: str = "usatechidxusd",
    start: str = None,
    end: str = None,
    params: dict = None,
    initial_balance: float = 10_000.0,
    ltf: str = "1h",
    htf: str = "4h",
) -> tuple:
    """Run full backtest pipeline and save results."""

    if params is None:
        params = {
            "pivot_lookback_ltf":    3,
            "pivot_lookback_htf":    5,
            "confirmation_bars":     1,
            "require_close_break":   True,
            "entry_offset_atr_mult": 0.3,
            "pullback_max_bars":     20,
            "sl_anchor":             "last_pivot",
            "sl_buffer_atr_mult":    0.5,
            "risk_reward":           2.0,
        }

    ltf_df = load_ltf(symbol, ltf)
    htf_df = build_htf_from_ltf(ltf_df, htf)

    # Apply date filter
    if start or end:
        ltf_df = filter_by_date(ltf_df, start, end)
        htf_df = filter_by_date(htf_df, start, end)
        print(f"After date filter: {_tf_label(ltf)}={len(ltf_df):,} {_tf_label(htf)}={len(htf_df):,}")

    if len(ltf_df) < 300:
        print(f"ERROR: Not enough bars ({len(ltf_df)}) — need at least 300. Aborting.")
        return None, None

    display_start = str(ltf_df.index[0].date())
    display_end   = str(ltf_df.index[-1].date())

    print(f"\nRunning backtest: {symbol.upper()}  {display_start} → {display_end}")
    print(f"LTF ({_tf_label(ltf)}) bars: {len(ltf_df):,} | HTF ({_tf_label(htf)}) bars: {len(htf_df):,}")
    print(f"Params: {params}\n")

    trades_df, metrics = run_trend_backtest(
        symbol=symbol.upper(),
        ltf_df=ltf_df,
        htf_df=htf_df,
        params_dict=params,
        initial_balance=initial_balance,
    )

    # Print results
    # win_rate from strategy is already stored as % value (e.g. 48.5 means 48.5%)
    win_rate_pct = metrics.get("win_rate", 0)
    # Compute R-based drawdown (PNL * 100000 multiplier is FX-only, not valid for indices)
    r_dd = _calc_r_drawdown(trades_df)

    print(f"\n{'='*60}")
    print(f"  RESULTS: {symbol.upper()}  {display_start} → {display_end}")
    print(f"{'='*60}")
    print(f"  Trades:           {metrics.get('trades_count', 0)}")
    print(f"  Win rate:         {win_rate_pct:.1f}%")
    print(f"  Expectancy (R):   {metrics.get('expectancy_R', 0):.3f}")
    print(f"  Profit factor:    {metrics.get('profit_factor', 0):.2f}")
    print(f"  Max R-drawdown:   {r_dd:.2f}R")
    print(f"  Max lose streak:  {metrics.get('max_losing_streak', 0)}")
    print(f"  Total setups:     {metrics.get('total_setups', 0)}")
    print(f"  Missed rate:      {metrics.get('missed_rate', 0) * 100:.1f}%")
    print(f"{'='*60}\n")

    # Save trades CSV
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sym_upper = symbol.upper()
    tf_tag = _tf_label(ltf)
    trades_path = REPORTS_DIR / f"IDX_{sym_upper}_{tf_tag}_BACKTEST_TRADES.csv"
    if len(trades_df):
        trades_df.to_csv(trades_path, index=False)
        print(f"Trades saved → {trades_path}")
    else:
        print("No trades to save.")

    # Save report MD
    report_md = build_report_md(symbol, metrics, trades_df, display_start, display_end, params,
                                ltf=ltf, htf=htf)
    report_path = REPORTS_DIR / f"IDX_{sym_upper}_{tf_tag}_BACKTEST_REPORT.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Report saved → {report_path}")

    return trades_df, metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest BOS+Pullback strategy on index data")
    parser.add_argument("--symbol", default="usatechidxusd", help="Symbol name (default: usatechidxusd)")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: all)")
    parser.add_argument("--end",   default=None, help="End date YYYY-MM-DD (default: all)")
    parser.add_argument("--ltf",   default="1h",  help="LTF timeframe: 1h, 30min, 15min (default: 1h)")
    parser.add_argument("--htf",   default="4h",  help="HTF timeframe: 4h, 1h, 1D (default: 4h)")
    parser.add_argument("--rr",    type=float, default=2.0, help="Risk:Reward ratio (default: 2.0)")
    parser.add_argument("--ltf_lookback", type=int, default=3, help="LTF pivot lookback (default: 3)")
    parser.add_argument("--htf_lookback", type=int, default=5, help="HTF pivot lookback (default: 5)")
    parser.add_argument("--balance", type=float, default=10000.0, help="Initial balance (default: 10000)")
    # Session filter
    parser.add_argument("--use-session-filter", action="store_true", default=True,
                        help="Enable session filter (default: on)")
    parser.add_argument("--no-session-filter", dest="use_session_filter", action="store_false",
                        help="Disable session filter")
    parser.add_argument("--session-start-hour", type=int, default=13,
                        help="Session start hour UTC (default: 13)")
    parser.add_argument("--session-end-hour",   type=int, default=20,
                        help="Session end hour UTC (default: 20)")
    # BOS momentum filter
    parser.add_argument("--use-bos-momentum-filter", action="store_true", default=True,
                        help="Enable BOS momentum filter (default: on)")
    parser.add_argument("--no-bos-momentum-filter", dest="use_bos_momentum_filter", action="store_false",
                        help="Disable BOS momentum filter")
    parser.add_argument("--bos-min-range-atr-mult", type=float, default=1.2,
                        help="BOS min impulse range as ATR multiple (default: 1.2)")
    parser.add_argument("--bos-min-body-ratio",     type=float, default=0.6,
                        help="BOS min body-to-range ratio (default: 0.6)")
    # ── FLAG_CONTRACTION setup params ───────────────────────────────────────
    parser.add_argument("--use-flag-contraction-setup", action="store_true", default=False,
                        help="Enable FLAG_CONTRACTION setup type (default: off)")
    parser.add_argument("--no-flag-contraction-setup", dest="use_flag_contraction_setup",
                        action="store_false", help="Disable FLAG_CONTRACTION setup type")
    parser.add_argument("--flag-impulse-lookback-bars",    type=int,   default=8,
                        help="Bars to look back for impulse move (default: 8)")
    parser.add_argument("--flag-contraction-bars",         type=int,   default=5,
                        help="Bars in consolidation/flag (default: 5)")
    parser.add_argument("--flag-min-impulse-atr-mult",     type=float, default=2.5,
                        help="Min impulse size as ATR multiple (default: 2.5)")
    parser.add_argument("--flag-max-contraction-atr-mult", type=float, default=1.2,
                        help="Max contraction range as ATR multiple (default: 1.2)")
    parser.add_argument("--flag-breakout-buffer-atr-mult", type=float, default=0.1,
                        help="Entry offset beyond contraction edge (default: 0.1)")
    parser.add_argument("--flag-sl-buffer-atr-mult",       type=float, default=0.3,
                        help="SL buffer beyond opposite contraction edge (default: 0.3)")
    args = parser.parse_args()

    params = {
        "pivot_lookback_ltf":       args.ltf_lookback,
        "pivot_lookback_htf":       args.htf_lookback,
        "confirmation_bars":        1,
        "require_close_break":      True,
        "entry_offset_atr_mult":    0.3,
        "pullback_max_bars":        20,
        "sl_anchor":                "last_pivot",
        "sl_buffer_atr_mult":       0.5,
        "risk_reward":              args.rr,
        # Session filter
        "use_session_filter":       args.use_session_filter,
        "session_start_hour_utc":   args.session_start_hour,
        "session_end_hour_utc":     args.session_end_hour,
        # BOS momentum filter
        "use_bos_momentum_filter":  args.use_bos_momentum_filter,
        "bos_min_range_atr_mult":   args.bos_min_range_atr_mult,
        "bos_min_body_to_range_ratio": args.bos_min_body_ratio,
        # FLAG_CONTRACTION setup
        "use_flag_contraction_setup":    args.use_flag_contraction_setup,
        "flag_impulse_lookback_bars":    args.flag_impulse_lookback_bars,
        "flag_contraction_bars":         args.flag_contraction_bars,
        "flag_min_impulse_atr_mult":     args.flag_min_impulse_atr_mult,
        "flag_max_contraction_atr_mult": args.flag_max_contraction_atr_mult,
        "flag_breakout_buffer_atr_mult": args.flag_breakout_buffer_atr_mult,
        "flag_sl_buffer_atr_mult":       args.flag_sl_buffer_atr_mult,
    }

    run_backtest(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        ltf=args.ltf,
        htf=args.htf,
        params=params,
        initial_balance=args.balance,
    )
