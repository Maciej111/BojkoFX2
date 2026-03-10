"""
src/research/regime_classifier/generate_report.py
===================================================
Reads grid search results and generates a Markdown report.
Output: data/research/REGIME_CLASSIFIER_REPORT.md

RESEARCH ONLY.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import sys

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from .backtest_with_regime import BASELINE
from .grid_search import _best_config


DEFAULT_INPUT  = str(_ROOT / "data" / "research" / "regime_grid_search.csv")
DEFAULT_OUTPUT = str(_ROOT / "data" / "research" / "REGIME_CLASSIFIER_REPORT.md")

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _worst_config(df_sym: pd.DataFrame):
    valid = df_sym[df_sym["expectancy_R"].notna()]
    if valid.empty:
        return None
    return valid.loc[valid["expectancy_R"].idxmin()]


def _fmt(val, fmt=".4f", prefix="") -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "n/a"
    if isinstance(val, float):
        return f"{prefix}{val:{fmt}}"
    return str(val)


def _delta_str(new, old) -> str:
    if new is None or old is None:
        return "n/a"
    try:
        d = float(new) - float(old)
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.3f}"
    except Exception:
        return "n/a"


# ─── Report sections ──────────────────────────────────────────────────────────

def _section_executive_summary(df: pd.DataFrame) -> str:
    lines = ["## Section 1: Executive Summary\n"]

    symbol_verdicts: Dict[str, str] = {}

    for sym in SYMBOLS:
        df_sym = df[df["symbol"] == sym]
        if df_sym.empty:
            lines.append(f"- **{sym}**: no data\n")
            continue

        best = _best_config(df_sym)
        worst = _worst_config(df_sym)
        base_exp = BASELINE.get(sym, {}).get("expectancy_R", 0.0)

        if best is None:
            symbol_verdicts[sym] = "NEUTRAL"
            lines.append(f"- **{sym}**: insufficient data\n")
            continue

        best_exp = float(best.get("expectancy_R", 0.0))
        delta_exp = best_exp - base_exp
        filtered_pct = float(best.get("trades_filtered_pct", 0.0))

        if delta_exp > 0.03 and filtered_pct < 60:
            verdict = "HELPS"
        elif delta_exp < -0.03 or filtered_pct > 70:
            verdict = "HURTS"
        else:
            verdict = "NEUTRAL"
        symbol_verdicts[sym] = verdict

        best_tag = (f"trend_enter={best['trend_enter']} "
                    f"chop_enter={best['chop_enter']} "
                    f"hvt={int(best['high_vol_threshold'])}")
        lines.append(
            f"- **{sym}** ({verdict}): "
            f"baseline ExpR={base_exp:+.3f} → best ExpR={best_exp:+.3f} "
            f"(Δ={delta_exp:+.3f}, filtered={filtered_pct:.0f}%) "
            f"| config: `{best_tag}`\n"
        )

        if worst is not None:
            worst_exp = float(worst.get("expectancy_R", 0.0))
            worst_tag = (f"trend_enter={worst['trend_enter']} "
                         f"chop_enter={worst['chop_enter']} "
                         f"hvt={int(worst['high_vol_threshold'])}")
            lines.append(
                f"  - Worst: ExpR={worst_exp:+.3f} | config: `{worst_tag}`\n"
            )

    # Overall verdict
    helps  = sum(1 for v in symbol_verdicts.values() if v == "HELPS")
    hurts  = sum(1 for v in symbol_verdicts.values() if v == "HURTS")
    total  = len(symbol_verdicts)

    if helps >= total * 0.75:
        overall = "**HELPS** — regime filter improves performance across most symbols"
    elif hurts >= total * 0.5:
        overall = "**HURTS** — regime filter degrades performance"
    elif helps >= total * 0.5:
        overall = "**PARTIAL** — regime filter helps some symbols, neutral/negative on others"
    else:
        overall = "**NEUTRAL** — regime filter has minimal impact overall"

    lines.append(f"\n### Overall Verdict: {overall}\n")
    return "\n".join(lines)


def _section_baseline_vs_best(df: pd.DataFrame) -> str:
    lines = ["## Section 2: Baseline vs Best Config\n"]

    for sym in SYMBOLS:
        df_sym = df[df["symbol"] == sym]
        if df_sym.empty:
            continue

        best = _best_config(df_sym)
        base = BASELINE.get(sym, {})
        lines.append(f"### {sym}\n")

        if best is None:
            lines.append("_No valid config found._\n")
            continue

        n_base   = int(base.get("n_trades", 0))
        n_best   = int(best.get("trades_allowed", 0))
        n_pct    = f"-{(1 - n_best/n_base)*100:.0f}%" if n_base > 0 else "n/a"

        wr_base  = base.get("win_rate", 0.0)
        wr_best  = float(best.get("win_rate", 0.0))

        exp_base = base.get("expectancy_R", 0.0)
        exp_best = float(best.get("expectancy_R", 0.0))

        dd_base  = base.get("max_dd_pct", 0.0)
        dd_best  = float(best.get("max_dd_pct", 0.0))

        pf_base  = base.get("profit_factor", 0.0)
        pf_best  = float(best.get("profit_factor", 0.0))

        lines.append("| Metric | Baseline | Best Config | Delta |")
        lines.append("|--------|----------|-------------|-------|")
        lines.append(f"| Trades | {n_base} | {n_best} | {n_pct} |")
        lines.append(f"| Win Rate | {wr_base:.1%} | {wr_best:.1%} | {_delta_str(wr_best, wr_base)} |")
        lines.append(f"| Exp(R) | {exp_base:+.3f} | {exp_best:+.3f} | {_delta_str(exp_best, exp_base)} |")
        lines.append(f"| Max DD | {dd_base:.1f}% | {dd_best:.1f}% | {_delta_str(dd_best, dd_base)}% |")
        lines.append(f"| PF | {pf_base:.2f} | {pf_best:.2f} | {_delta_str(pf_best, pf_base)} |")
        lines.append("")

    return "\n".join(lines)


def _section_heatmap(df: pd.DataFrame) -> str:
    lines = ["## Section 3: Grid Search Heatmap (ExpR)\n"]
    te_vals  = sorted(df["trend_enter"].dropna().unique())
    ce_vals  = sorted(df["chop_enter"].dropna().unique())
    hvt_vals = sorted(df["high_vol_threshold"].dropna().unique())

    for sym in SYMBOLS:
        df_sym = df[df["symbol"] == sym]
        if df_sym.empty:
            continue
        lines.append(f"### {sym}\n")

        for hvt in hvt_vals:
            lines.append(f"**high_vol_threshold = {int(hvt)}**\n")
            # Header
            header = "| trend_enter↓ / chop_enter→ |" + \
                     "".join(f" {ce} |" for ce in ce_vals)
            sep = "|---|" + "---|" * len(ce_vals)
            lines.append(header)
            lines.append(sep)
            for te in te_vals:
                row_parts = [f"| **{te}** |"]
                for ce in ce_vals:
                    subset = df_sym[
                        (df_sym["trend_enter"] == te) &
                        (df_sym["chop_enter"]  == ce) &
                        (df_sym["high_vol_threshold"] == hvt)
                    ]
                    if subset.empty or subset["expectancy_R"].isna().all():
                        row_parts.append(" n/a |")
                    else:
                        v = float(subset["expectancy_R"].iloc[0])
                        row_parts.append(f" {v:+.3f} |")
                lines.append("".join(row_parts))
            lines.append("")

    return "\n".join(lines)


def _section_regime_distribution(df: pd.DataFrame) -> str:
    lines = ["## Section 4: Regime Distribution\n"]
    lines.append(
        "_Note: Regime distribution is derived from per-run regime series. "
        "Summary approximated from filter stats in grid results._\n"
    )

    for sym in SYMBOLS:
        df_sym = df[df["symbol"] == sym]
        if df_sym.empty:
            continue
        best = _best_config(df_sym)
        if best is None:
            continue

        lines.append(f"### {sym} (best config)\n")
        lines.append(
            f"- Config: trend_enter={best['trend_enter']} "
            f"chop_enter={best['chop_enter']} "
            f"hvt={int(best['high_vol_threshold'])}\n"
        )
        n_total   = int(best.get("trades_total", 0))
        n_allowed = int(best.get("trades_allowed", 0))
        n_filtered = n_total - n_allowed
        lines.append(
            f"- Trades baseline: {n_total} | "
            f"Allowed by regime: {n_allowed} ({n_allowed/n_total*100:.0f}% of baseline) | "
            f"Filtered: {n_filtered} ({n_filtered/n_total*100:.0f}%)\n"
            if n_total > 0 else "- No trade data.\n"
        )
        lines.append("")

    return "\n".join(lines)


def _section_filter_analysis(df: pd.DataFrame) -> str:
    lines = ["## Section 5: Trade Filter Analysis\n"]

    for sym in SYMBOLS:
        df_sym = df[df["symbol"] == sym]
        if df_sym.empty:
            continue
        best = _best_config(df_sym)
        if best is None:
            continue

        lines.append(f"### {sym}\n")
        tp_f  = int(best.get("tp_filtered", 0))
        sl_f  = int(best.get("sl_filtered", 0))
        total_f = tp_f + sl_f
        prec  = float(best.get("filter_precision", 0.0))
        lines.append(f"| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| TP trades filtered (false negatives) | {tp_f} |")
        lines.append(f"| SL trades filtered (correct blocks) | {sl_f} |")
        lines.append(f"| Total filtered | {total_f} |")
        lines.append(f"| Filter precision (SL_filtered / total) | {prec:.1%} |")
        lines.append("")

    return "\n".join(lines)


def _section_recommendation(df: pd.DataFrame) -> str:
    lines = ["## Section 6: Recommendation\n"]

    symbol_results = {}
    for sym in SYMBOLS:
        df_sym = df[df["symbol"] == sym]
        if df_sym.empty:
            continue
        best = _best_config(df_sym)
        base = BASELINE.get(sym, {})
        if best is None:
            continue

        base_exp  = float(base.get("expectancy_R", 0.0))
        base_dd   = float(base.get("max_dd_pct", 0.0))
        best_exp  = float(best.get("expectancy_R", 0.0))
        best_dd   = float(best.get("max_dd_pct", 0.0))
        filt_pct  = float(best.get("trades_filtered_pct", 0.0))

        delta_exp_pct = (best_exp - base_exp) / abs(base_exp) * 100 if base_exp != 0 else 0.0
        dd_improved   = best_dd < base_dd

        symbol_results[sym] = {
            "delta_exp_pct": delta_exp_pct,
            "dd_improved": dd_improved,
            "filt_pct": filt_pct,
            "best_exp": best_exp,
            "config": (f"trend_enter={best['trend_enter']} "
                       f"chop_enter={best['chop_enter']} "
                       f"hvt={int(best['high_vol_threshold'])}"),
        }

    # Classify
    implement_syms  = []
    partial_syms    = []
    reject_syms     = []

    for sym, r in symbol_results.items():
        if r["delta_exp_pct"] > 15 and r["filt_pct"] < 40:
            implement_syms.append(sym)
        elif r["delta_exp_pct"] > 5 or r["dd_improved"]:
            partial_syms.append(sym)
        else:
            reject_syms.append(sym)

    if len(implement_syms) >= 3:
        verdict = "A"
    elif len(implement_syms) + len(partial_syms) >= 2:
        verdict = "B"
    else:
        verdict = "C"

    verdict_text = {
        "A": "**IMPLEMENT**: Classifier improves expectancy >15% AND reduces DD with <40% trade reduction",
        "B": "**PARTIAL**: Helps some symbols, not others — implement per-symbol",
        "C": "**REJECT**: No meaningful improvement or hurts performance",
    }
    lines.append(f"### Verdict: {verdict_text[verdict]}\n")

    if verdict in ("A", "B"):
        lines.append("### Recommended configurations:\n")
        for sym in implement_syms + partial_syms:
            r = symbol_results[sym]
            lines.append(
                f"- **{sym}**: `{r['config']}` "
                f"→ ExpR={r['best_exp']:+.3f} "
                f"(Δ={r['delta_exp_pct']:+.1f}%)\n"
            )

    lines.append("\n### Symbols analysis:\n")
    for sym, r in symbol_results.items():
        tag = "✅ IMPLEMENT" if sym in implement_syms \
              else "⚠️ PARTIAL"  if sym in partial_syms \
              else "❌ REJECT"
        lines.append(
            f"- {sym}: {tag} | "
            f"ExpR delta={r['delta_exp_pct']:+.1f}% | "
            f"filtered={r['filt_pct']:.0f}% | "
            f"DD improved={r['dd_improved']}\n"
        )

    lines.append("\n### Overfit risk:\n")
    lines.append(
        "The grid search was performed on OOS 2023-2024 data only (no in-sample optimisation).\n"
        "Risk: 18 configs × 4 symbols = 72 evaluations. With multiple comparisons, "
        "some positive results may be noise.\n"
        "Recommendation: validate the top config on 2025 data (out-of-sample) before production use.\n"
    )

    return "\n".join(lines)


# ─── Main entry point ─────────────────────────────────────────────────────────

def generate_report(
    input_csv: Optional[str] = None,
    output_md: Optional[str] = None,
) -> str:
    """
    Read grid search CSV, generate Markdown report, save to file.

    Returns the report as a string.
    """
    if input_csv is None:
        input_csv = DEFAULT_INPUT
    if output_md is None:
        output_md = DEFAULT_OUTPUT

    if not Path(input_csv).exists():
        raise FileNotFoundError(f"Grid search CSV not found: {input_csv}")

    df = pd.read_csv(input_csv)
    # Drop rows with errors
    df = df[df["expectancy_R"].notna()].copy()

    lines = [
        "# Market Regime Classifier — Research Report",
        "",
        f"**Generated**: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Data source**: {input_csv}",
        f"**OOS period**: 2023-01-01 to 2024-12-31",
        f"**Symbols**: {', '.join(BASELINE.keys())}",
        f"**Strategy**: BOS + Pullback (PROOF V2 params, frozen)",
        f"**Grid**: 18 configs × {len(df['symbol'].unique())} symbols = {len(df)} runs",
        "",
        "---",
        "",
    ]

    lines.append(_section_executive_summary(df))
    lines.append("---\n")
    lines.append(_section_baseline_vs_best(df))
    lines.append("---\n")
    lines.append(_section_heatmap(df))
    lines.append("---\n")
    lines.append(_section_regime_distribution(df))
    lines.append("---\n")
    lines.append(_section_filter_analysis(df))
    lines.append("---\n")
    lines.append(_section_recommendation(df))

    report = "\n".join(lines)
    Path(output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(output_md).write_text(report, encoding="utf-8")
    return report



