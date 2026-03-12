"""
CLI backtest runner for VCLSMB strategy.

Integrates with existing project infrastructure:
  - Reuses load_ltf, build_htf_from_ltf, filter_by_date from scripts.run_backtest_idx
  - Writes outputs to strategies/VolatilityContractionLiquiditySweepMomentumBreakout/output/
  - Writes markdown report to strategies/VolatilityContractionLiquiditySweepMomentumBreakout/report/

Usage (from US100/ root):
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest
    python -m strategies.VolatilityContractionLiquiditySweepMomentumBreakout.run_backtest \\
        --start 2022-01-01 --end 2024-12-31 --rr 2.5 --no-session-filter
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[2]   # US100/
_SHARED = _ROOT.parent / "shared"
for _p in [str(_ROOT), str(_SHARED)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.run_backtest_idx import load_ltf, filter_by_date

from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.config import VCLSMBConfig
from strategies.VolatilityContractionLiquiditySweepMomentumBreakout.strategy import run_vclsmb_backtest

_STRATEGY_DIR = Path(__file__).resolve().parent
_OUTPUT_DIR   = _STRATEGY_DIR / "output"
_REPORT_DIR   = _STRATEGY_DIR / "report"


def _build_report_md(symbol, metrics, trades_df, start, end, cfg) -> str:
    from scripts.run_backtest_idx import _calc_r_drawdown
    n     = metrics.get("trades_count", 0)
    wr    = metrics.get("win_rate", 0)
    er    = metrics.get("expectancy_R", 0)
    pf    = metrics.get("profit_factor", 0)
    r_dd  = _calc_r_drawdown(trades_df) if n > 0 else 0.0

    lines = [
        f"# VCLSMB Backtest Report: {symbol.upper()}",
        f"",
        f"**Strategy:** VolatilityContraction → LiquiditySweep → MomentumBreakout",
        f"**Period:** {start} -> {end}",
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"## Performance Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Trades | {n} |",
        f"| Win Rate | {wr:.1f}% |",
        f"| Expectancy R | {er:+.3f} R |",
        f"| Profit Factor | {pf:.2f} |",
        f"| Max DD (R) | {r_dd:.1f} R |",
        *([
            f"| First Entries | {metrics.get('first_entries', n)} |",
            f"| Pullback Entries | {metrics.get('pullback_entries', 0)} |",
        ] if cfg.enable_pullback_entry else []),
        f"",
        f"## Strategy Parameters",
        f"",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| ATR Period | {cfg.atr_period} |",
        f"| Compression Lookback | {cfg.compression_lookback} bars |",
        f"| Compression ATR Ratio | {cfg.compression_atr_ratio} |",
        f"| Range Window | {cfg.range_window} bars |",
        f"| Sweep ATR Mult | {cfg.sweep_atr_mult} |",
        f"| Sweep Close Inside | {cfg.sweep_close_inside} |",
        f"| Momentum ATR Mult | {cfg.momentum_atr_mult} |",
        f"| Momentum Body Ratio | {cfg.momentum_body_ratio} |",
        f"| Risk:Reward | {cfg.risk_reward} |",
        f"| SL Buffer ATR Mult | {cfg.sl_buffer_atr_mult} |",
        f"| SL Anchor | {cfg.sl_anchor} |",
        f"| Session Filter | {cfg.use_session_filter} ({cfg.session_start_hour_utc}-{cfg.session_end_hour_utc} UTC) |",
        f"| Max Bars In State | {cfg.max_bars_in_state} |",
        *([
            f"| Pullback Entry | Enabled |",
            f"| Pullback ATR Mult | {cfg.pullback_atr_mult} |",
            f"| Max Entries / Setup | {cfg.max_entries_per_setup} |",
        ] if cfg.enable_pullback_entry else []),
        f"",
    ]

    if n > 0:
        # Direction split
        longs  = trades_df[trades_df["direction"] == "LONG"]
        shorts = trades_df[trades_df["direction"] == "SHORT"]
        lines += [
            f"## Direction Breakdown",
            f"",
            f"| Direction | Trades | Win Rate | E(R) |",
            f"|-----------|--------|----------|------|",
            f"| LONG  | {len(longs)} | {(longs['R']>0).mean()*100:.0f}% | {longs['R'].mean():+.3f} |" if len(longs) else "| LONG  | 0 | — | — |",
            f"| SHORT | {len(shorts)} | {(shorts['R']>0).mean()*100:.0f}% | {shorts['R'].mean():+.3f} |" if len(shorts) else "| SHORT | 0 | — | — |",
            f"",
            f"## Exit Reason Breakdown",
            f"",
        ]
        for reason, grp in trades_df.groupby("exit_reason"):
            lines.append(f"- **{reason}**: {len(grp)} trades")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="VCLSMB strategy backtest runner"
    )
    parser.add_argument("--symbol",   default="usatechidxusd")
    parser.add_argument("--ltf",      default="5min",
                        help="LTF timeframe: 5min | 15min | 30min | 1h")
    parser.add_argument("--start",    default="2021-01-01")
    parser.add_argument("--end",      default="2025-12-31")
    parser.add_argument("--rr",       type=float,  default=2.0)
    parser.add_argument("--atr-period",           type=int,   default=14)
    parser.add_argument("--compression-lookback", type=int,   default=20)
    parser.add_argument("--compression-atr-ratio",type=float, default=0.6)
    parser.add_argument("--range-window",         type=int,   default=10)
    parser.add_argument("--sweep-atr-mult",       type=float, default=0.5)
    parser.add_argument("--momentum-atr-mult",    type=float, default=1.3)
    parser.add_argument("--momentum-body-ratio",  type=float, default=0.65)
    parser.add_argument("--sl-anchor",  default="range_extreme",
                        choices=["range_extreme", "sweep_wick"])
    parser.add_argument("--session-filter",    dest="session_filter",
                        action="store_true",  default=False)
    parser.add_argument("--no-session-filter", dest="session_filter",
                        action="store_false")
    parser.add_argument("--trend-filter",    dest="trend_filter",
                        action="store_true",  default=False)
    parser.add_argument("--no-trend-filter", dest="trend_filter",
                        action="store_false")
    parser.add_argument("--trend-ema-period",     type=int,   default=50)
    parser.add_argument("--trailing-stop",        dest="trailing_stop",
                        action="store_true",  default=False)
    parser.add_argument("--trailing-atr-mult",    type=float, default=2.0)
    parser.add_argument("--breakeven-atr-mult",   type=float, default=1.0)
    parser.add_argument(
        "--pullback-entry", dest="pullback_entry",
        action="store_true", default=False,
        help="Enable BOS+Pullback continuation entry (TREND_EXPANSION state)",
    )
    parser.add_argument("--pullback-atr-mult",     type=float, default=0.2,
                        help="Pullback zone width in ATR units (default: 0.2)")
    parser.add_argument("--max-entries-per-setup", type=int,   default=2,
                        help="Max entries per setup when pullback enabled (default: 2)")
    args = parser.parse_args()

    cfg = VCLSMBConfig(
        atr_period              = args.atr_period,
        compression_lookback    = args.compression_lookback,
        compression_atr_ratio   = args.compression_atr_ratio,
        range_window            = args.range_window,
        sweep_atr_mult          = args.sweep_atr_mult,
        momentum_atr_mult       = args.momentum_atr_mult,
        momentum_body_ratio     = args.momentum_body_ratio,
        risk_reward             = args.rr,
        use_session_filter      = args.session_filter,
        enable_trend_filter     = args.trend_filter,
        trend_ema_period        = args.trend_ema_period,
        use_trailing_stop       = args.trailing_stop,
        trailing_atr_multiplier = args.trailing_atr_mult,
        breakeven_atr_mult      = args.breakeven_atr_mult,
        enable_pullback_entry   = args.pullback_entry,
        pullback_atr_mult       = args.pullback_atr_mult,
        max_entries_per_setup   = args.max_entries_per_setup,
    )

    print(f"Loading {args.ltf} bars for {args.symbol}...")
    ltf_df = load_ltf(args.symbol, args.ltf)
    ltf_df = filter_by_date(ltf_df, args.start, args.end)
    print(f"Filtered: {len(ltf_df):,} bars  [{args.start} -> {args.end}]")

    print("Running VCLSMB backtest...")
    trades_df, metrics = run_vclsmb_backtest(args.symbol, ltf_df, cfg)

    n  = metrics["trades_count"]
    er = metrics["expectancy_R"]
    wr = metrics["win_rate"]
    print(f"\nResults: n={n}  WR={wr:.1f}%  E(R)={er:+.3f}")
    if cfg.enable_pullback_entry:
        print(f"  First entries:    {metrics.get('first_entries', n)}")
        print(f"  Pullback entries: {metrics.get('pullback_entries', 0)}")

    # ── Save outputs ──────────────────────────────────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)

    date_tag = datetime.utcnow().strftime("%Y-%m-%d")
    sym_upper = args.symbol.upper()

    trades_path = _OUTPUT_DIR / f"{sym_upper}_VCLSMB_{args.ltf}_{date_tag}_TRADES.csv"
    trades_df.to_csv(trades_path, index=False)
    print(f"Trades saved: {trades_path}")

    report_md = _build_report_md(args.symbol, metrics, trades_df, args.start, args.end, cfg)
    report_path = _REPORT_DIR / f"{sym_upper}_VCLSMB_{args.ltf}_{date_tag}_REPORT.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
