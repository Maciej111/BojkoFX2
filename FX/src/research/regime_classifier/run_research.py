"""
src/research/regime_classifier/run_research.py
===============================================
Single entry point for the full regime classifier research pipeline.

Usage
-----
python src/research/regime_classifier/run_research.py \\
    --symbols EURUSD,GBPUSD,USDJPY,XAUUSD \\
    --start 2023-01-01 \\
    --end 2024-12-31

Options
-------
--symbols       Comma-separated list of FX symbols (default: EURUSD,GBPUSD,USDJPY,XAUUSD)
--start         OOS period start (default: 2023-01-01)
--end           OOS period end   (default: 2024-12-31)
--data-dir      Override data directory (default: ./data)
--output-dir    Override output directory (default: ./data/research)
--no-report     Skip report generation (grid search only)

RESEARCH ONLY — no production code is modified.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as script
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.research.regime_classifier.grid_search import run_grid_search, BASELINE
from src.research.regime_classifier.generate_report import generate_report
from src.research.regime_classifier.backtest_with_regime import load_h1_bars


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="BojkoFx — Market Regime Classifier Research Pipeline"
    )
    p.add_argument(
        "--symbols",
        default="EURUSD,GBPUSD,USDJPY,XAUUSD",
        help="Comma-separated symbol list",
    )
    p.add_argument("--start", default="2023-01-01", help="OOS start date")
    p.add_argument("--end",   default="2024-12-31", help="OOS end date")
    p.add_argument(
        "--data-dir",
        default=str(_ROOT / "data"),
        help="Data directory",
    )
    p.add_argument(
        "--output-dir",
        default=str(_ROOT / "data" / "research"),
        help="Output directory for CSV and report",
    )
    p.add_argument(
        "--no-report",
        action="store_true",
        help="Skip report generation",
    )
    return p.parse_args()


def _print_quick_summary(grid_csv_path: str, symbols: list) -> str:
    """Print quick summary table to stdout. Returns overall verdict string."""
    import pandas as pd
    from src.research.regime_classifier.grid_search import _best_config

    df = pd.read_csv(grid_csv_path)
    df = df[df["expectancy_R"].notna()]

    print("\n" + "=" * 60)
    print("  QUICK SUMMARY")
    print("=" * 60)

    verdicts = []
    for sym in symbols:
        df_sym = df[df["symbol"] == sym]
        base = BASELINE.get(sym, {})
        base_exp = float(base.get("expectancy_R", 0.0))

        if df_sym.empty:
            print(f"  {sym}: no data")
            verdicts.append("NEUTRAL")
            continue

        best = _best_config(df_sym)
        if best is None:
            print(f"  {sym}: no valid config")
            verdicts.append("NEUTRAL")
            continue

        best_exp = float(best["expectancy_R"])
        delta    = best_exp - base_exp
        cfg_tag  = (f"te={best['trend_enter']} "
                    f"ce={best['chop_enter']} "
                    f"hvt={int(best['high_vol_threshold'])}")
        filtered = float(best.get("trades_filtered_pct", 0))

        print(
            f"  {sym}: baseline {base_exp:+.3f}R → best {best_exp:+.3f}R "
            f"(Δ={delta:+.3f}, -{filtered:.0f}% trades)  "
            f"[{cfg_tag}]"
        )

        delta_pct = (delta / abs(base_exp) * 100) if base_exp != 0 else 0.0
        if delta_pct > 15 and filtered < 40:
            verdicts.append("IMPLEMENT")
        elif delta_pct > 5:
            verdicts.append("PARTIAL")
        else:
            verdicts.append("REJECT")

    implement = verdicts.count("IMPLEMENT")
    partial   = verdicts.count("PARTIAL")
    n = len(verdicts)

    if implement >= n * 0.75:
        overall = "IMPLEMENT"
    elif implement + partial >= n * 0.5:
        overall = "PARTIAL"
    else:
        overall = "REJECT"

    print(f"\n  Verdict: {overall}")
    print("=" * 60)
    return overall


def main() -> None:
    args = _parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    output_dir  = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    grid_csv    = str(output_dir / "regime_grid_search.csv")
    report_md   = str(output_dir / "REGIME_CLASSIFIER_REPORT.md")

    print(f"\nBojkoFx — Market Regime Classifier Research")
    print(f"  Symbols : {', '.join(symbols)}")
    print(f"  Period  : {args.start} → {args.end}")
    print(f"  Output  : {args.output_dir}")
    print()

    # ── Step 1: Grid search ────────────────────────────────────────────────
    t0 = time.perf_counter()
    print("Running grid search (18 configs × symbols)…")
    run_grid_search(
        symbols=symbols,
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        output_path=grid_csv,
        verbose=True,
    )
    elapsed_gs = time.perf_counter() - t0
    print(f"\nGrid search complete in {elapsed_gs:.1f}s")
    print(f"Results: {grid_csv}")

    # ── Step 2: Generate report ───────────────────────────────────────────
    if not args.no_report:
        print("\nGenerating report…")
        try:
            generate_report(input_csv=grid_csv, output_md=report_md)
            print(f"Report saved to: {report_md}")
        except Exception as exc:
            print(f"[WARN] Report generation failed: {exc}")

    # ── Step 3: Quick summary ─────────────────────────────────────────────
    try:
        _print_quick_summary(grid_csv, symbols)
    except Exception as exc:
        print(f"[WARN] Could not print summary: {exc}")

    print(f"\nTotal time: {time.perf_counter() - t0:.1f}s")
    print()
    print("Results:")
    print(f"  data/research/regime_grid_search.csv")
    print(f"  data/research/REGIME_CLASSIFIER_REPORT.md")
    print()
    print("To view report:")
    print("  type data\\research\\REGIME_CLASSIFIER_REPORT.md")
    print()
    print("To inspect grid results:")
    print('  python -c "import pandas as pd; df=pd.read_csv(\'data/research/regime_grid_search.csv\'); print(df.sort_values(\'expectancy_R\', ascending=False).head(10).to_string())"')


if __name__ == "__main__":
    main()

