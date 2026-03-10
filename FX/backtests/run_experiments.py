"""
backtests/run_experiments.py
CLI pipeline runner.

Użycie:
  python -m backtests.run_experiments --config backtests/config_backtest.yaml
  python -m backtests.run_experiments --config backtests/config_backtest.yaml --symbols EURUSD USDJPY --quick
  python -m backtests.run_experiments --config backtests/config_backtest.yaml --stage1-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

# Dodaj root projektu do ścieżki
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from backtests.engine import PortfolioSimulator
from backtests.experiments import all_experiments, stage2_experiments, adx_v2_experiments
from backtests.metrics import calc_metrics, metrics_per_symbol, equity_series
from backtests.reporting import (
    save_results_all, save_results_summary, save_top_configs,
    generate_report, plot_equity_curves, plot_r_histogram,
)
from backtests.signals_bos_pullback import (
    BOSPullbackSignalGenerator, build_d1, build_h4, filter_and_adjust,
)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_h1(symbol: str, data_cfg: dict) -> Optional[pd.DataFrame]:
    """
    Wczytuje H1 bid CSV dla symbolu.
    Wybiera plik _2021_2025 jeśli dostępny i prefer_2025=True, inaczej _2021_2024.
    """
    m60_dir = Path(data_cfg.get("m60_dir", "data/raw_dl_fx/download/m60"))
    sym_l = symbol.lower()
    prefer_2025 = data_cfg.get("prefer_2025", True)

    candidates = []
    if prefer_2025:
        candidates = [
            m60_dir / f"{sym_l}_m60_bid_2021_2025.csv",
            m60_dir / f"{sym_l}_m60_bid_2021_2024.csv",
        ]
    else:
        candidates = [
            m60_dir / f"{sym_l}_m60_bid_2021_2024.csv",
            m60_dir / f"{sym_l}_m60_bid_2021_2025.csv",
        ]

    path = None
    for c in candidates:
        if c.exists():
            path = c
            break

    if path is None:
        print(f"  [WARN] No data file for {symbol} in {m60_dir}")
        return None

    df = pd.read_csv(path)
    # Normalize column names to lowercase
    df.columns = [c.lower() for c in df.columns]
    ts_col = None
    for candidate in ("timestamp", "time", "date", "datetime"):
        if candidate in df.columns:
            ts_col = candidate
            break
    if ts_col is None:
        # First column as fallback
        ts_col = df.columns[0]

    ts_series = df[ts_col]
    # Detect millisecond integers (values > 1e10 are ms-epoch)
    try:
        first_val = float(ts_series.iloc[0])
        if first_val > 1e10:
            df.index = pd.to_datetime(ts_series, unit="ms", utc=True)
        else:
            df.index = pd.to_datetime(ts_series, utc=True)
    except (ValueError, TypeError):
        df.index = pd.to_datetime(ts_series, utc=True)

    # Ensure required OHLC columns exist
    ohlc_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
    if len(ohlc_cols) < 4:
        print(f"  [WARN] {path.name}: missing OHLC columns (found: {list(df.columns)})")
        return None
    df = df[["open", "high", "low", "close"]].copy()
    df = df.sort_index()
    # Drop duplicates
    df = df[~df.index.duplicated(keep="first")]
    return df


def slice_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df.loc[start:end].copy()


# ── Fold definitions ──────────────────────────────────────────────────────────

def build_folds(cfg: dict) -> List[dict]:
    """
    Zwraca listę foldów z config + opcjonalne rolling quarters.
    Każdy fold: {name, train_start, train_end, val_start, val_end, test_start, test_end}
    """
    folds = list(cfg.get("folds", []))

    rq = cfg.get("rolling_quarters", {})
    if rq.get("enabled", False):
        for year in rq.get("years", []):
            quarters = [
                (f"{year}-01-01", f"{year}-03-31"),
                (f"{year}-04-01", f"{year}-06-30"),
                (f"{year}-07-01", f"{year}-09-30"),
                (f"{year}-10-01", f"{year}-12-31"),
            ]
            for qi, (qs, qe) in enumerate(quarters, 1):
                folds.append({
                    "name":        f"Q{qi}_{year}",
                    "train_start": f"{year - 2}-01-01",
                    "train_end":   f"{year}-{['03','06','09','12'][qi-1]}-{['31','30','30','31'][qi-1]}",
                    "val_start":   qs,
                    "val_end":     qe,
                    "test_start":  qs,
                    "test_end":    qe,
                    "has_test_split": False,   # val == test, skip duplicate test run
                })
    return folds


# ── Single experiment runner ──────────────────────────────────────────────────

def run_one_experiment(
    exp: dict,
    symbols: List[str],
    h1_data: Dict[str, pd.DataFrame],
    all_setups_by_sym: Dict[str, Any],
    fold: dict,
    strategy_cfg: dict,
    session_cfg: Dict[str, dict],
    portfolio_cfg: dict,
    split: str,   # "val" | "test" | "train"
) -> Tuple[List[dict], dict]:
    """
    Uruchamia jeden eksperyment na jednym foldzie/splicie.
    Przyjmuje pre-generated setups (generate_all) i filtruje je per exp.
    Zwraca (all_rows, portfolio_metrics_row).
    """
    start_key = f"{split}_start"
    end_key   = f"{split}_end"
    period_start = fold[start_key]
    period_end   = fold[end_key]

    # Slice H1 data for period
    h1_sliced: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        if sym not in h1_data or h1_data[sym] is None:
            continue
        sliced = slice_period(h1_data[sym], period_start, period_end)
        if not sliced.empty:
            h1_sliced[sym] = sliced

    if not h1_sliced:
        return [], {}

    # Filter pre-generated setups to this period + experiment parameters
    period_start_ts = pd.Timestamp(period_start, tz="UTC")
    period_end_ts   = pd.Timestamp(period_end,   tz="UTC") + pd.Timedelta(days=1)
    setups_by_sym: Dict[str, Any] = {}
    for sym in h1_sliced:
        full_setups = all_setups_by_sym.get(sym, [])
        time_filtered = [
            s for s in full_setups
            if period_start_ts <= s.bar_ts < period_end_ts
        ]
        setups_by_sym[sym] = filter_and_adjust(time_filtered, exp)

    # Sizing config
    sizing_cfg = {
        "mode":     exp["sizing_mode"],
        "units":    exp["fixed_units"],
        "risk_pct": exp["risk_pct"],
    }

    max_total  = portfolio_cfg.get("max_positions_total", 3)
    initial_eq = float(portfolio_cfg.get("initial_equity", 10000))

    sim = PortfolioSimulator(
        h1_data=h1_sliced,
        setups=setups_by_sym,
        sizing_cfg=sizing_cfg,
        session_cfg={sym: session_cfg.get(sym, {}) for sym in h1_sliced},
        same_bar_mode=strategy_cfg.get("same_bar_mode", "conservative"),
        max_positions_total=max_total,
        max_positions_per_symbol=portfolio_cfg.get("max_positions_per_symbol", 1),
        initial_equity=initial_eq,
    )
    closed_trades = sim.run()

    sym_metrics  = metrics_per_symbol(closed_trades, initial_eq)
    port_metrics = calc_metrics(closed_trades, initial_eq, label="PORTFOLIO")

    exp_meta = {k: exp[k] for k in exp}
    base = {
        "exp_name":  exp["name"],
        "exp_block": exp.get("block", ""),
        "fold":      fold["name"],
        "split":     split,
    }
    base.update(exp_meta)

    all_rows = []
    for sym, m in sym_metrics.items():
        row = {**base, "symbol": sym}
        row.update(m)
        all_rows.append(row)

    port_row = {**base, "symbol": "PORTFOLIO"}
    port_row.update(port_metrics)
    all_rows.append(port_row)

    return all_rows, port_row


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_pipeline(cfg: dict, symbols_override: Optional[List[str]] = None,
                 stage1_only: bool = False, quick: bool = False) -> None:
    """Pełny pipeline: wczytaj dane, uruchom eksperymenty, zapisz wyniki."""
    t0 = time.time()

    symbols = symbols_override or cfg.get("symbols", [])
    data_cfg = cfg.get("data", {})
    strategy_cfg = cfg.get("strategy", {})
    session_cfg = {s: v for s, v in cfg.get("session_filter", {}).items()}
    portfolio_cfg = cfg.get("portfolio", {})
    output_cfg = cfg.get("output", {})
    out_dir = Path(output_cfg.get("dir", "backtests/outputs"))

    print(f"\n{'='*60}")
    print(f"BojkoFx Research Backtest Pipeline")
    print(f"Symbols: {symbols}")
    print(f"{'='*60}\n")

    # ── Load data ─────────────────────────────────────────────────────────────
    print("[1/5] Loading H1 data...")
    h1_data: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = load_h1(sym, data_cfg)
        if df is not None and not df.empty:
            h1_data[sym] = df
            print(f"  {sym}: {len(df)} bars "
                  f"({df.index[0].date()} – {df.index[-1].date()})")
        else:
            print(f"  {sym}: SKIP (no data)")

    symbols = [s for s in symbols if s in h1_data]
    if not symbols:
        print("ERROR: No valid symbols with data. Aborting.")
        return

    # ── Pre-generate all candidate setups once per symbol (expensive O(n) step)
    # Each subsequent experiment call just filters this list — no re-scan of bars.
    print("\n[1b/5] Pre-generating signals (one full scan per symbol)...")
    baseline_sig_cfg = {
        **strategy_cfg,
        "atr_pct_window": strategy_cfg.get("atr_pct_window", 100),
    }
    gen = BOSPullbackSignalGenerator(baseline_sig_cfg)
    all_setups_by_sym: Dict[str, Any] = {}
    for sym in symbols:
        d1 = build_d1(h1_data[sym], adx_period=strategy_cfg.get("atr_period", 14))
        h4 = build_h4(h1_data[sym], adx_period=strategy_cfg.get("atr_period", 14))
        all_setups_by_sym[sym] = gen.generate_all(sym, h1_data[sym], d1, h4)
        print(f"  {sym}: {len(all_setups_by_sym[sym])} candidate setups")

    # ── Build folds ───────────────────────────────────────────────────────────
    print("\n[2/5] Building folds...")
    folds = build_folds(cfg)
    if quick:
        # W trybie quick: tylko fold_2021_2025 + Q4_2024
        folds = [f for f in folds
                 if f["name"] in ("fold_2021_2025", "Q4_2024", "Q4_2025")][:2]
        if not folds:
            folds = folds[:2]
    print(f"  {len(folds)} folds: {[f['name'] for f in folds]}")

    # ── Stage 1 experiments ───────────────────────────────────────────────────
    print("\n[3/5] Running Stage 1 experiments (one-factor-at-a-time)...")
    stage1_exps = all_experiments(cfg)
    if quick:
        # Quick mode: tylko baseline + 3 ADX + 3 ATR pct + 2 sizing + 2 RR
        stage1_exps = (
            [e for e in stage1_exps if e["block"] == "baseline"] +
            [e for e in stage1_exps if e["block"] == "adx"][:4] +
            [e for e in stage1_exps if e["block"] == "atr_pct"][:4] +
            [e for e in stage1_exps if e["block"] == "sizing"][:3] +
            [e for e in stage1_exps if e["block"] == "rr"][:3]
        )
    print(f"  {len(stage1_exps)} experiments × {len(folds)} folds × 2 splits")

    all_rows: List[dict] = []
    summary_rows: List[dict] = []

    # ── For each fold run all experiments on val and (optionally) test ────────
    # Quarterly folds have val==test window — skip redundant test split
    def _splits_for(fold: dict) -> List[str]:
        if fold.get("has_test_split", True):
            return ["val", "test"]
        return ["val"]

    total_runs = sum(len(stage1_exps) * len(_splits_for(f)) for f in folds)
    done = 0
    stage1_val_results: List[dict] = []   # for stage2 selection

    for fold in folds:
        for exp in stage1_exps:
            for split in _splits_for(fold):
                rows, port_row = run_one_experiment(
                    exp=exp,
                    symbols=symbols,
                    h1_data=h1_data,
                    all_setups_by_sym=all_setups_by_sym,
                    fold=fold,
                    strategy_cfg=strategy_cfg,
                    session_cfg=session_cfg,
                    portfolio_cfg=portfolio_cfg,
                    split=split,
                )
                all_rows.extend(rows)
                if port_row:
                    summary_rows.append(port_row)
                    if split == "val":
                        stage1_val_results.append({
                            "exp": exp,
                            "metrics_val": {
                                k: port_row.get(k, 0)
                                for k in ["expectancy_R", "profit_factor",
                                          "max_dd_pct", "win_rate"]
                            },
                        })
                done += 1
                if done % 20 == 0 or done == total_runs:
                    elapsed = time.time() - t0
                    print(f"  Progress: {done}/{total_runs} "
                          f"({done/total_runs*100:.0f}%) — {elapsed:.0f}s")

    # ── Stage 2 (cross-product) ───────────────────────────────────────────────
    if not stage1_only and not quick:
        print(f"\n[4/5] Running Stage 2 experiments (cross-product)...")
        exp_pipeline_cfg = cfg.get("experiments", {}).get("pipeline", {})
        stage2_exps = stage2_experiments(
            stage1_val_results,
            top_n=exp_pipeline_cfg.get("stage1_top_n", 10),
            max_total=exp_pipeline_cfg.get("max_experiments", 350),
            seed=exp_pipeline_cfg.get("seed", 42),
        )
        print(f"  {len(stage2_exps)} cross experiments")

        total_s2 = sum(len(stage2_exps) * len(_splits_for(f)) for f in folds)
        done_s2 = 0
        for fold in folds:
            for exp in stage2_exps:
                for split in _splits_for(fold):
                    rows, port_row = run_one_experiment(
                        exp=exp, symbols=symbols, h1_data=h1_data,
                        all_setups_by_sym=all_setups_by_sym,
                        fold=fold, strategy_cfg=strategy_cfg,
                        session_cfg=session_cfg, portfolio_cfg=portfolio_cfg,
                        split=split,
                    )
                    all_rows.extend(rows)
                    if port_row:
                        summary_rows.append(port_row)
                    done_s2 += 1
                    if done_s2 % 30 == 0 or done_s2 == total_s2:
                        print(f"  S2 progress: {done_s2}/{total_s2} "
                              f"({done_s2/total_s2*100:.0f}%)")
    else:
        print("\n[4/5] Stage 2 skipped (--stage1-only or --quick)")

    # ── Save results ──────────────────────────────────────────────────────────
    print("\n[5/5] Saving results...")

    save_results_all(all_rows, out_dir / output_cfg.get("results_all_csv", "results_all.csv"))
    save_results_summary(summary_rows, out_dir / output_cfg.get("results_summary_csv", "results_summary.csv"))

    # Top configs (by val expectancy_R portfolio average across folds)
    val_port = [r for r in summary_rows
                if r.get("split") == "val" and r.get("symbol") == "PORTFOLIO"]
    test_port = [r for r in summary_rows
                 if r.get("split") == "test" and r.get("symbol") == "PORTFOLIO"]

    if val_port:
        df_v = pd.DataFrame(val_port)
        df_t = pd.DataFrame(test_port) if test_port else None

        agg_v = df_v.groupby("exp_name").agg(
            val_expectancy_R=("expectancy_R", "mean"),
            val_profit_factor=("profit_factor", "mean"),
            val_max_dd_pct=("max_dd_pct", "mean"),
            val_win_rate=("win_rate", "mean"),
            val_pct_pos_q=("pct_pos_quarters", "mean"),
        ).reset_index()

        if df_t is not None and not df_t.empty:
            agg_t = df_t.groupby("exp_name").agg(
                test_expectancy_R=("expectancy_R", "mean"),
                test_profit_factor=("profit_factor", "mean"),
                test_max_dd_pct=("max_dd_pct", "mean"),
            ).reset_index()
            agg = agg_v.merge(agg_t, on="exp_name", how="left")
        else:
            agg = agg_v
            agg["test_expectancy_R"] = None
            agg["test_max_dd_pct"] = None

        top10 = agg.sort_values("val_expectancy_R", ascending=False).head(10)
        # Add exp config
        exp_map = {e["name"]: e for e in stage1_exps}
        top_configs = []
        for _, row in top10.iterrows():
            exp = exp_map.get(row["exp_name"], {"name": row["exp_name"]})
            rec = {**exp, **row.to_dict()}
            top_configs.append(rec)
        save_top_configs(top_configs, out_dir / output_cfg.get("top_configs_json", "top_configs.json"))
    else:
        top_configs = []

    # Generate report
    generate_report(
        all_rows=all_rows,
        summary_rows=summary_rows,
        top_configs=top_configs,
        output_path=out_dir / output_cfg.get("report_md", "report.md"),
        cfg=cfg,
    )

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"DONE in {elapsed:.1f}s")
    print(f"Results: {out_dir}/")
    print(f"  results_all.csv     — {len(all_rows)} rows")
    print(f"  results_summary.csv — {len(summary_rows)} rows")
    print(f"  top_configs.json    — top {len(top_configs)} configs")
    print(f"  report.md           — full report")
    print(f"{'='*60}\n")


# ── ADX v2 pipeline ───────────────────────────────────────────────────────────

def run_adx_v2_pipeline(cfg: dict,
                        symbols_override: Optional[List[str]] = None) -> None:
    """
    Uruchamia TYLKO eksperymenty ADX v2 i generuje adx_v2_report.md.
    Szybszy od pełnego run_pipeline (38 eksperymentów × 9 foldów).
    """
    from backtests.reporting import generate_adx_v2_report

    t0 = time.time()
    symbols      = symbols_override or cfg.get("symbols", [])
    data_cfg     = cfg.get("data", {})
    strategy_cfg = cfg.get("strategy", {})
    session_cfg  = {s: v for s, v in cfg.get("session_filter", {}).items()}
    portfolio_cfg = cfg.get("portfolio", {})
    output_cfg   = cfg.get("output", {})
    out_dir      = Path(output_cfg.get("dir", "backtests/outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"BojkoFx ADX v2 Test Pipeline")
    print(f"Symbols: {symbols}")
    print(f"{'='*60}\n")

    # Load H1 data
    print("[1/4] Loading H1 data...")
    h1_data: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = load_h1(sym, data_cfg)
        if df is not None and not df.empty:
            h1_data[sym] = df
            print(f"  {sym}: {len(df)} bars")
    symbols = [s for s in symbols if s in h1_data]
    if not symbols:
        print("ERROR: No data. Aborting.")
        return

    # Pre-generate setups with full H4 context
    print("\n[2/4] Pre-generating signals with H4 context...")
    gen = BOSPullbackSignalGenerator({
        **strategy_cfg,
        "atr_pct_window": strategy_cfg.get("atr_pct_window", 100),
    })
    all_setups_by_sym: Dict[str, Any] = {}
    for sym in symbols:
        d1 = build_d1(h1_data[sym], adx_period=strategy_cfg.get("atr_period", 14))
        h4 = build_h4(h1_data[sym], adx_period=strategy_cfg.get("atr_period", 14))
        all_setups_by_sym[sym] = gen.generate_all(sym, h1_data[sym], d1, h4)
        # Quick check H4 coverage
        h4_nonzero = sum(1 for s in all_setups_by_sym[sym] if s.adx_h4_val > 0)
        print(f"  {sym}: {len(all_setups_by_sym[sym])} setups, "
              f"{h4_nonzero} with H4 ADX > 0")

    folds = build_folds(cfg)
    v2_exps = adx_v2_experiments()
    print(f"\n[3/4] Running {len(v2_exps)} ADX v2 experiments × {len(folds)} folds...")

    all_rows: List[dict] = []
    summary_rows: List[dict] = []

    def _splits_for(fold: dict) -> List[str]:
        return ["val"] if not fold.get("has_test_split", True) else ["val", "test"]

    total = sum(len(v2_exps) * len(_splits_for(f)) for f in folds)
    done = 0
    for fold in folds:
        for exp in v2_exps:
            for split in _splits_for(fold):
                rows, port_row = run_one_experiment(
                    exp=exp, symbols=symbols, h1_data=h1_data,
                    all_setups_by_sym=all_setups_by_sym,
                    fold=fold, strategy_cfg=strategy_cfg,
                    session_cfg=session_cfg, portfolio_cfg=portfolio_cfg,
                    split=split,
                )
                all_rows.extend(rows)
                if port_row:
                    summary_rows.append(port_row)
                done += 1
                if done % 30 == 0 or done == total:
                    print(f"  {done}/{total} ({done/total*100:.0f}%) "
                          f"— {time.time()-t0:.0f}s")

    # Save raw results
    print("\n[4/4] Saving results...")
    csv_path = out_dir / "results_adx_v2.csv"
    save_results_summary(summary_rows, csv_path)
    # Zapisz też all_rows (per-symbol) do osobnego pliku dla raportu per-symbol
    all_csv_path = out_dir / "results_adx_v2_all.csv"
    save_results_all(all_rows, all_csv_path)

    # Generate ADX v2 report
    generate_adx_v2_report(
        summary_rows=summary_rows,
        output_path=out_dir / "adx_v2_report.md",
        cfg=cfg,
    )

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"ADX v2 DONE in {elapsed:.1f}s")
    print(f"  results_adx_v2.csv — {len(summary_rows)} rows")
    print(f"  adx_v2_report.md   — full report")
    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="BojkoFx Research Backtest Pipeline"
    )
    parser.add_argument(
        "--config", default="backtests/config_backtest.yaml",
        help="Path to config YAML"
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="Override symbols from config"
    )
    parser.add_argument(
        "--stage1-only", action="store_true",
        help="Run only Stage 1, skip Stage 2 cross-product"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick run: fewer experiments + fewer folds"
    )
    parser.add_argument(
        "--adx-v2-only", action="store_true",
        help="Run only ADX v2 experiments → adx_v2_report.md (faster)"
    )
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"ERROR: Config not found: {cfg_path}")
        sys.exit(1)

    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.adx_v2_only:
        run_adx_v2_pipeline(cfg=cfg, symbols_override=args.symbols)
    else:
        run_pipeline(
            cfg=cfg,
            symbols_override=args.symbols,
            stage1_only=args.stage1_only,
            quick=args.quick,
        )


if __name__ == "__main__":
    main()



