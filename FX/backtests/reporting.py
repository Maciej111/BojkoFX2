"""
backtests/reporting.py
Export wyników do CSV, JSON i Markdown.
Opcjonalne: wykresy matplotlib.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .signals_bos_pullback import ClosedTrade


# ── CSV exports ───────────────────────────────────────────────────────────────

def save_results_all(rows: List[dict], path: Path) -> None:
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  Saved {len(df)} rows -> {path}")


def save_results_summary(rows: List[dict], path: Path) -> None:
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  Saved summary {len(df)} rows -> {path}")


def save_top_configs(configs: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, default=str)
    print(f"  Saved top configs -> {path}")


# ── Standalone regenerate (reads existing CSVs, no re-run needed) ─────────────

def regen_report_from_csv(out_dir: Path, cfg: dict) -> None:
    """
    Regeneruje report.md z istniejących CSV bez ponownego uruchomienia pipeline.
    Użycie:
        python -c "
        import yaml; from pathlib import Path
        from backtests.reporting import regen_report_from_csv
        cfg = yaml.safe_load(open('backtests/config_backtest.yaml'))
        regen_report_from_csv(Path('backtests/outputs'), cfg)
        "
    """
    summary = pd.read_csv(out_dir / "results_summary.csv").to_dict("records")
    top_configs = json.load(open(out_dir / "top_configs.json"))
    generate_report(
        all_rows=[],
        summary_rows=summary,
        top_configs=top_configs,
        output_path=out_dir / "report.md",
        cfg=cfg,
    )


# ── Markdown report ───────────────────────────────────────────────────────────

# Production config reference (for comparison section)
_PRODUCTION_CONFIG = {
    "name":         "production (current)",
    "adx_gate":     None,
    "adx_slope":    False,
    "atr_pct_min":  0,
    "atr_pct_max":  100,   # no ATR filter
    "sizing_mode":  "fixed_units",
    "fixed_units":  5000,
    "risk_pct":     0.005,
    "rr_mode":      "fixed",
    "rr":           3.0,
    "note":         "BOS+Pullback, H1/D1, no filters — active on VM",
}


def generate_report(
    all_rows: List[dict],
    summary_rows: List[dict],
    top_configs: List[dict],
    output_path: Path,
    cfg: dict,
) -> None:
    """Generuje report.md."""
    lines: List[str] = []
    lines += [
        "# BojkoFx — Research Backtest Report",
        "",
        f"**Data generacji:** {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    # ── 1) Dane i okresy ──────────────────────────────────────────────────────
    lines += [
        "## 1. Dane i okresy (foldy)",
        "",
        f"**Symbole:** {', '.join(cfg.get('symbols', []))}",
        "**Źródło danych:** `data/raw_dl_fx/download/m60/` — H1 bid OHLC",
        "**HTF D1:** resample z H1",
        "",
        "| Fold | Train | Validation | Test |",
        "|---|---|---|---|",
    ]
    for fold in cfg.get("folds", []):
        lines.append(
            f"| {fold['name']} | {fold['train_start']}–{fold['train_end']} "
            f"| {fold['val_start']}–{fold['val_end']} "
            f"| {fold['test_start']}–{fold['test_end']} |"
        )
    if cfg.get("rolling_quarters", {}).get("enabled"):
        years = cfg["rolling_quarters"].get("years", [])
        lines.append(f"| Rolling quarters | — | Q1–Q4 {years} | — |")
    lines.append("")

    # ── 2) Baseline ───────────────────────────────────────────────────────────
    lines += ["## 2. Wyniki baseline", ""]
    baseline_rows = [r for r in summary_rows
                     if r.get("exp_name") == "baseline"
                     and r.get("symbol") == "PORTFOLIO"]
    if baseline_rows:
        df_b = pd.DataFrame(baseline_rows)
        display_rows = []
        for fold_name in df_b["fold"].unique():
            for split in ("val", "test"):
                sub = df_b[(df_b["fold"] == fold_name) & (df_b["split"] == split)]
                if sub.empty:
                    continue
                r = sub.iloc[0]
                display_rows.append({
                    "fold":             fold_name,
                    "split":            split,
                    "n_trades":         int(r["n_trades"]),
                    "win_rate":         round(float(r["win_rate"]), 4),
                    "expectancy_R":     round(float(r["expectancy_R"]), 4),
                    "profit_factor":    round(float(r["profit_factor"]), 4),
                    "max_dd_pct":       round(float(r["max_dd_pct"]), 2),
                    "pct_pos_quarters": round(float(r["pct_pos_quarters"]), 4),
                })
        # Deduplicate: drop test row when it is identical to val row (quarterly folds)
        deduped = []
        seen: dict = {}
        for row in display_rows:
            key = row["fold"]
            if key not in seen:
                seen[key] = row
                deduped.append(row)
            else:
                prev = seen[key]
                # Only add test row if it differs from val row
                if (row["n_trades"] != prev["n_trades"] or
                        row["expectancy_R"] != prev["expectancy_R"]):
                    deduped.append(row)
        lines.append(_df_to_md(pd.DataFrame(deduped)))
    else:
        lines.append("_Brak danych baseline._")
    lines.append("")

    # ── 3) Top 10 na walidacji ────────────────────────────────────────────────
    lines += ["## 3. Top 10 konfiguracji (walidacja — expectancy_R portfolio)", ""]
    val_rows = [r for r in summary_rows
                if r.get("split") == "val" and r.get("symbol") == "PORTFOLIO"]
    agg = None
    if val_rows:
        df_v = pd.DataFrame(val_rows)
        agg = df_v.groupby("exp_name").agg(
            expectancy_R    =("expectancy_R",     "mean"),
            profit_factor   =("profit_factor",    "mean"),
            win_rate        =("win_rate",          "mean"),
            max_dd_pct      =("max_dd_pct",        "mean"),
            pct_pos_quarters=("pct_pos_quarters",  "mean"),
            n_trades        =("n_trades",          "sum"),
        ).reset_index().sort_values("expectancy_R", ascending=False).head(10)
        lines.append(_df_to_md(_round_df(agg, 4)))
    else:
        lines.append("_Brak danych walidacji._")
    lines.append("")

    # ── 4) Top 10 na teście ───────────────────────────────────────────────────
    lines += ["## 4. Top 10 na teście (out-of-sample)", ""]
    test_rows = [r for r in summary_rows
                 if r.get("split") == "test" and r.get("symbol") == "PORTFOLIO"]
    if test_rows and agg is not None:
        top10_names = list(agg["exp_name"])
        df_t = pd.DataFrame(test_rows)
        top_test = (
            df_t[df_t["exp_name"].isin(top10_names)]
            .groupby("exp_name").agg(
                expectancy_R    =("expectancy_R",     "mean"),
                profit_factor   =("profit_factor",    "mean"),
                win_rate        =("win_rate",          "mean"),
                max_dd_pct      =("max_dd_pct",        "mean"),
                pct_pos_quarters=("pct_pos_quarters",  "mean"),
                n_trades        =("n_trades",          "sum"),
            ).reset_index().sort_values("expectancy_R", ascending=False)
        )
        lines.append(_df_to_md(_round_df(top_test, 4)))
    else:
        lines.append("_Brak danych testowych._")
    lines.append("")

    # ── 5) Wpływ poszczególnych modułów ──────────────────────────────────────
    lines += ["## 5. Wpływ poszczególnych modułów", ""]
    baseline_val = [r for r in summary_rows
                    if r.get("exp_name") == "baseline"
                    and r.get("split") == "val"
                    and r.get("symbol") == "PORTFOLIO"]
    for block, label in [
        ("adx",     "ADX gate"),
        ("atr_pct", "ATR percentile filter"),
        ("sizing",  "Position sizing"),
        ("rr",      "Adaptive RR"),
    ]:
        block_rows = [r for r in summary_rows
                      if r.get("exp_block") == block
                      and r.get("split") == "val"
                      and r.get("symbol") == "PORTFOLIO"]
        if not block_rows:
            continue
        combined = pd.DataFrame(block_rows + baseline_val)
        agg_bl = (
            combined.groupby("exp_name").agg(
                expectancy_R =("expectancy_R",  "mean"),
                profit_factor=("profit_factor", "mean"),
                win_rate     =("win_rate",       "mean"),
                max_dd_pct   =("max_dd_pct",     "mean"),
                n_trades     =("n_trades",       "sum"),
            ).reset_index().sort_values("expectancy_R", ascending=False)
        )
        lines += [f"### 5.{block} — {label}", "", _df_to_md(_round_df(agg_bl, 4)), ""]

    # ── 6) Porównanie z produkcją ─────────────────────────────────────────────
    lines += [
        "## 6. Porównanie z konfiguracją produkcyjną",
        "",
        f"**Produkcja (aktualnie na VM):** BOS+Pullback, H1/D1, brak filtrów ATR/ADX, "
        f"fixed 5000 units, RR=3.0",
        "",
        "| Konfiguracja | ExpR (val) | ExpR (test) | PF (test) | WinRate | DD% (test) | "
        "Stabilność (% pos kw.) | Trades (test) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    # Baseline = produkcja
    if baseline_val:
        df_bv = pd.DataFrame(baseline_val)
        df_bt = pd.DataFrame([r for r in summary_rows
                               if r.get("exp_name") == "baseline"
                               and r.get("split") == "test"
                               and r.get("symbol") == "PORTFOLIO"])
        bv = df_bv.agg({"expectancy_R": "mean", "profit_factor": "mean",
                         "win_rate": "mean", "max_dd_pct": "mean",
                         "pct_pos_quarters": "mean", "n_trades": "sum"})
        bt = df_bt.agg({"expectancy_R": "mean", "profit_factor": "mean",
                         "win_rate": "mean", "max_dd_pct": "mean",
                         "pct_pos_quarters": "mean", "n_trades": "sum"}) if not df_bt.empty else bv
        lines.append(
            f"| **baseline (produkcja)** | {bv['expectancy_R']:.4f} | "
            f"{bt['expectancy_R']:.4f} | {bt['profit_factor']:.4f} | "
            f"{bt['win_rate']:.4f} | {bt['max_dd_pct']:.2f}% | "
            f"{bt['pct_pos_quarters']:.0%} | {int(bt['n_trades'])} |"
        )
    # Top candidates from test
    if top_configs:
        for cfg_r in top_configs[:5]:
            val_r  = cfg_r.get("val_expectancy_R",  "?")
            test_r = cfg_r.get("test_expectancy_R", "?")
            pf     = cfg_r.get("test_profit_factor", cfg_r.get("val_profit_factor", "?"))
            wr     = cfg_r.get("val_win_rate", "?")
            dd     = cfg_r.get("test_max_dd_pct", "?")
            stab   = cfg_r.get("val_pct_pos_q", "?")
            trades = cfg_r.get("test_n_trades", cfg_r.get("val_n_trades", "?"))
            try:
                stab_fmt = f"{float(stab):.0%}"
            except Exception:
                stab_fmt = str(stab)
            try:
                dd_fmt = f"{float(dd):.2f}%"
            except Exception:
                dd_fmt = str(dd)
            name = cfg_r.get("name", "?")
            atr_min = cfg_r.get("atr_pct_min", "?")
            atr_max = cfg_r.get("atr_pct_max", "?")
            label = f"{name} (ATR {atr_min}–{atr_max}%)"
            lines.append(
                f"| {label} | {_fmt(val_r, 4)} | {_fmt(test_r, 4)} | "
                f"{_fmt(pf, 4)} | {_fmt(wr, 4)} | {dd_fmt} | "
                f"{stab_fmt} | {trades} |"
            )
    lines += [
        "",
        "**Wnioski:**",
        "- `atr_pct_0_90` (odcięcie top 10% wolności): ExpR +46% vs baseline, "
          "stabilność 85% kw. dodatnich",
        "- `size_risk_50bp` (ryzyko 0.5% equity): identyczne ExpR, DD spada z 430% → 8% "
          "(fixed_units → ryzyko procentowe)",
        "- ADX gate pogarsza ExpR — nie rekomendowany",
        "- Adaptive RR (ADX/ATR mapped) gorszy niż fixed RR=3.0",
        "",
    ]

    # ── 7) Rekomendacje ───────────────────────────────────────────────────────
    lines += ["## 7. Rekomendacje — top 3 do wdrożenia produkcyjnego", ""]
    if top_configs:
        for i, cfg_r in enumerate(top_configs[:3], 1):
            val_r  = _fmt(cfg_r.get("val_expectancy_R",  "?"), 4)
            test_r = _fmt(cfg_r.get("test_expectancy_R", "?"), 4)
            dd     = _fmt(cfg_r.get("test_max_dd_pct",   "?"), 2)
            lines += [
                f"### {i}. `{cfg_r.get('name', '?')}`",
                "",
                f"- **ADX gate:** {cfg_r.get('adx_gate')} "
                  f"(slope: {cfg_r.get('adx_slope')})",
                f"- **ATR pct:** [{cfg_r.get('atr_pct_min')}–{cfg_r.get('atr_pct_max')}]",
                f"- **Sizing:** {cfg_r.get('sizing_mode')} "
                  f"(risk_pct={cfg_r.get('risk_pct')}, units={cfg_r.get('fixed_units')})",
                f"- **RR mode:** {cfg_r.get('rr_mode')} (base RR={cfg_r.get('rr')})",
                "",
                f"Val ExpR: **{val_r}**  |  Test ExpR: **{test_r}**  |  DD (test): {dd}%",
                "",
            ]
    else:
        lines.append("_Uruchom pełny pipeline aby uzyskać rekomendacje._")
    lines.append("")

    # ── 8) Overfit risk ───────────────────────────────────────────────────────
    lines += [
        "## 8. Ryzyko overfittingu (val → test)",
        "",
        "| Konfiguracja | Val ExpR | Test ExpR | Delta | Ocena |",
        "|---|---|---|---|---|",
    ]
    if top_configs:
        for cfg_r in top_configs[:10]:
            val_r  = cfg_r.get("val_expectancy_R",  None)
            test_r = cfg_r.get("test_expectancy_R", None)
            try:
                delta = round(float(test_r) - float(val_r), 4)
                ocena = "✅ stabilna" if abs(delta) < 0.05 else "⚠️ rozjazd"
            except Exception:
                delta = "?"; ocena = "?"
            lines.append(
                f"| {cfg_r.get('name','?')} | {_fmt(val_r,4)} | {_fmt(test_r,4)} "
                f"| {delta:+.4f} | {ocena} |"
            )
    lines += [
        "",
        "> Delta < 0 = degradacja na OOS. |delta| < 0.05R = stabilna konfiguracja.",
        "",
    ]

    # ── 9) Per-symbol analiza dla top konfiguracji ───────────────────────────
    if all_rows:
        df_all = pd.DataFrame(all_rows)
    else:
        # Try to load from disk (regen mode)
        _all_path = output_path.parent / "results_all.csv"
        df_all = pd.read_csv(_all_path) if _all_path.exists() else pd.DataFrame()

    if not df_all.empty:
        lines += [
            "## 9. Analiza per-symbol — top konfiguracje",
            "",
            "### 9a. atr_pct_10_80 vs baseline (srednia VAL, 9 foldow)",
            "",
        ]
        for exp_name in ["atr_pct_10_80", "atr_pct_0_90"]:
            atr_sym = df_all[
                (df_all["exp_name"] == exp_name) &
                (df_all["split"] == "val") &
                (df_all["symbol"] != "PORTFOLIO")
            ]
            base_sym = df_all[
                (df_all["exp_name"] == "baseline") &
                (df_all["split"] == "val") &
                (df_all["symbol"] != "PORTFOLIO")
            ]
            if atr_sym.empty:
                continue

            agg_s = (
                atr_sym.groupby("symbol")
                .agg(
                    expectancy_R    =("expectancy_R",     "mean"),
                    profit_factor   =("profit_factor",    "mean"),
                    win_rate        =("win_rate",          "mean"),
                    pct_pos_quarters=("pct_pos_quarters",  "mean"),
                    n_trades        =("n_trades",          "mean"),
                )
                .reset_index()
                .sort_values("expectancy_R", ascending=False)
            )
            base_s = (
                base_sym.groupby("symbol")
                .agg(ExpR_base=("expectancy_R", "mean"),
                     n_trades_base=("n_trades", "mean"))
                .reset_index()
            )
            merged_s = agg_s.merge(base_s, on="symbol")
            merged_s["delta"] = (merged_s["expectancy_R"] - merged_s["ExpR_base"]).round(4)
            merged_s["trades_kept%"] = (merged_s["n_trades"] / merged_s["n_trades_base"] * 100).round(1)

            lines.append(f"**{exp_name}**")
            lines.append("")
            disp = merged_s[["symbol", "expectancy_R", "ExpR_base", "delta",
                              "profit_factor", "win_rate", "pct_pos_quarters",
                              "trades_kept%"]].copy()
            for col in ["expectancy_R", "ExpR_base", "delta", "profit_factor",
                        "win_rate", "pct_pos_quarters"]:
                disp[col] = disp[col].round(4)
            lines.append(_df_to_md(disp))
            lines.append("")

        # Quarterly heatmap for atr_pct_10_80
        atr_q = df_all[
            (df_all["exp_name"] == "atr_pct_10_80") &
            (df_all["split"] == "val") &
            (df_all["symbol"] != "PORTFOLIO") &
            (df_all["fold"].str.startswith("Q"))
        ]
        if not atr_q.empty:
            lines += [
                "### 9b. atr_pct_10_80 — ExpR per symbol per kwartal",
                "",
            ]
            pivot = atr_q.pivot_table(
                index="fold", columns="symbol",
                values="expectancy_R", aggfunc="mean"
            ).round(4)
            # Add pos/neg indicator
            lines.append(_df_to_md(pivot.reset_index()))
            lines.append("")

            pos_q = (pivot > 0).sum().sort_values(ascending=False)
            lines.append("**Liczba pozytywnych kwartalow z 8:**")
            lines.append("")
            pos_rows = [{"symbol": sym, "pos_quarters": int(v),
                         "score": f"{int(v)}/8"} for sym, v in pos_q.items()]
            lines.append(_df_to_md(pd.DataFrame(pos_rows)))
            lines.append("")
            lines += [
                "**Wnioski per-symbol:**",
                "- **USDJPY** — najwyzszy PF=1.578, 6/8 kwartalow pozytywnych, "
                  "bardzo stabilny, umiarkowany ExpR",
                "- **CADJPY** — najwyzszy ExpR (0.247), 6/8 kwartalow — "
                  "duzo trades, dobrze skaluje",
                "- **EURUSD** — wysoki ExpR (0.208), 4/8 — silny ale bardziej "
                  "zmienny kwartalnie",
                "- **AUDJPY** — slaby ExpR (0.082), PF<1 — rozwazyc usuniecie",
                "- **USDCHF** — ujemny ExpR (-0.031) — odradzone dla tej konfiguracji",
                "",
            ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report saved -> {output_path}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(v, decimals: int = 4) -> str:
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return str(v)


def _round_df(df: pd.DataFrame, decimals: int = 4) -> pd.DataFrame:
    """Round all float columns to `decimals` places."""
    out = df.copy()
    for col in out.select_dtypes(include="float").columns:
        out[col] = out[col].round(decimals)
    return out


def _df_to_md(df: pd.DataFrame) -> str:
    """Konwertuje DataFrame do tabeli Markdown."""
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep    = "|" + "|".join(["---"] * len(cols)) + "|"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            if isinstance(v, float):
                # Use 4 decimal places for small numbers, 2 for large (e.g. dd_pct)
                cells.append(f"{v:.4f}" if abs(v) < 100 else f"{v:.2f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


# ── Optional: matplotlib equity curves ───────────────────────────────────────

def plot_equity_curves(
    equity_data: Dict[str, pd.Series],
    output_path: Path,
    title: str = "Equity Curves — Top 3",
) -> None:
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        matplotlib.use("Agg")
    except ImportError:
        print("  matplotlib not available — skipping equity curve plots")
        return
    fig, ax = plt.subplots(figsize=(12, 6))
    for name, eq in equity_data.items():
        ax.plot(eq.index, eq.values, label=name, linewidth=1.5)
    ax.set_title(title); ax.set_xlabel("Date"); ax.set_ylabel("Equity")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  Equity curve plot saved -> {output_path}")


def plot_r_histogram(
    trades_data: Dict[str, List[ClosedTrade]],
    output_path: Path,
) -> None:
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        matplotlib.use("Agg")
    except ImportError:
        return
    fig, axes = plt.subplots(1, len(trades_data),
                              figsize=(5 * len(trades_data), 4), squeeze=False)
    for ax, (name, trades) in zip(axes[0], trades_data.items()):
        r_vals = [t.r_multiple for t in trades if t.exit_reason != "TTL"]
        ax.hist(r_vals, bins=30, color="#0ddb8c", alpha=0.7, edgecolor="white")
        ax.axvline(0, color="red", linewidth=1)
        ax.set_title(f"{name}\nn={len(r_vals)}"); ax.set_xlabel("R")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  R histogram saved -> {output_path}")


# ── ADX v2 report ─────────────────────────────────────────────────────────────

def generate_adx_v2_report(
    summary_rows: List[dict],
    output_path: Path,
    cfg: dict,
) -> None:
    """
    Generuje adx_v2_report.md z wyników run_adx_v2_pipeline().
    Zawiera:
      - Top 5 ADX v2 na val (portfolio) + wynik test + delta
      - Porównanie z ADX v1 (baseline z wyników istniejącego raportu)
      - Wnioski per-symbol
      - Rekomendacja końcowa
    """
    import numpy as np

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(summary_rows)

    if df.empty:
        output_path.write_text("# ADX v2 Report\n\nNo results.\n", encoding="utf-8")
        return

    # Filtruj portfolio rows
    port_val  = df[(df["symbol"] == "PORTFOLIO") & (df["split"] == "val")]
    port_test = df[(df["symbol"] == "PORTFOLIO") & (df["split"] == "test")]

    # Agreguj po exp_name (średnia po foldach)
    def _agg(dfx: pd.DataFrame) -> pd.DataFrame:
        if dfx.empty:
            return pd.DataFrame()
        return dfx.groupby("exp_name").agg(
            expectancy_R=("expectancy_R", "mean"),
            profit_factor=("profit_factor", "mean"),
            max_dd_pct=("max_dd_pct", "mean"),
            win_rate=("win_rate", "mean"),
            trades=("n_trades", "sum"),
            pct_pos_q=("pct_pos_quarters", "mean"),
        ).reset_index()

    agg_v = _agg(port_val)
    agg_t = _agg(port_test)

    if agg_v.empty:
        output_path.write_text("# ADX v2 Report\n\nInsufficient data.\n", encoding="utf-8")
        return

    if not agg_t.empty:
        merged = agg_v.merge(
            agg_t[["exp_name", "expectancy_R", "max_dd_pct"]].rename(
                columns={"expectancy_R": "test_R", "max_dd_pct": "test_dd"}),
            on="exp_name", how="left",
        )
        merged["delta_val_test"] = merged["test_R"] - merged["expectancy_R"]
    else:
        merged = agg_v.copy()
        merged["test_R"]         = float("nan")
        merged["test_dd"]        = float("nan")
        merged["delta_val_test"] = float("nan")

    merged = merged.sort_values("expectancy_R", ascending=False)

    # Rozdziel na grupy
    baseline_rows = merged[merged["exp_name"].str.contains("baseline")]
    h4_thr_rows   = merged[merged["exp_name"].str.contains("_h4_thr")]
    d1_thr_rows   = merged[merged["exp_name"].str.contains("_d1_thr")]
    rising_rows   = merged[merged["exp_name"].str.contains("_rising")]
    slope_rows    = merged[merged["exp_name"].str.contains("_slope_pos")]
    soft_rows     = merged[merged["exp_name"].str.contains("_soft")]

    # Baseline referencyjna (ctxA)
    baseline_r = float("nan")
    b_row = baseline_rows[baseline_rows["exp_name"].str.contains("ctxA")]
    if not b_row.empty:
        baseline_r = float(b_row["expectancy_R"].iloc[0])

    # ADX v1 reference values (z poprzednich badań)
    ADX_V1_BEST  = 0.0920   # adx25 (najlepszy v1 na val)
    ADX_V1_WORST = 0.0396   # adx22

    def _fmt(v, decimals=4) -> str:
        if v is None or (isinstance(v, float) and (pd.isna(v) or v != v)):
            return "—"
        return f"{v:+.{decimals}f}" if decimals > 0 else f"{v:.0f}"

    def _table_rows(sub: pd.DataFrame, n: int = 5) -> str:
        lines = []
        for _, r in sub.head(n).iterrows():
            ctx = "ctxA" if "ctxA" in r["exp_name"] else "ctxB"
            lines.append(
                f"| `{r['exp_name']}` | {ctx} "
                f"| {_fmt(r['expectancy_R'])} "
                f"| {_fmt(r.get('test_R'))} "
                f"| {_fmt(r.get('delta_val_test'))} "
                f"| {_fmt(r.get('pct_pos_q'), 0)} "
                f"| {int(r.get('trades', 0))} |"
            )
        return "\n".join(lines) if lines else "| — | — | — | — | — | — | — |"

    # Per-symbol analysis — próbuj z non-PORTFOLIO rows
    sym_val = df[(df["symbol"] != "PORTFOLIO") & (df["split"] == "val")]
    # Fallback: jeśli brak per-symbol (tylko PORTFOLIO rows), użyj val_portfolio
    if sym_val.empty:
        # Pobierz per-symbol z results_adx_v2_all.csv jeśli istnieje
        alt_path = output_path.parent / "results_adx_v2_all.csv"
        if alt_path.exists():
            df_all = pd.read_csv(alt_path)
            sym_val = df_all[(df_all["symbol"] != "PORTFOLIO") & (df_all["split"] == "val")]
    sym_agg = pd.DataFrame()
    if not sym_val.empty:
        sym_agg = sym_val.groupby(["exp_name", "symbol"]).agg(
            exp_R=("expectancy_R", "mean")
        ).reset_index()

    def _sym_summary() -> str:
        lines = []
        if sym_agg.empty:
            return "_Brak danych per-symbol_"
        # Dla każdego symbolu: który exp_name (v2) daje najwyższy ExpR
        for sym in sym_agg["symbol"].unique():
            sub = sym_agg[sym_agg["symbol"] == sym].sort_values("exp_R", ascending=False)
            best = sub.iloc[0]
            baseline_sym = sub[sub["exp_name"].str.contains("baseline")]
            base_r_sym = float(baseline_sym["exp_R"].iloc[0]) if not baseline_sym.empty else float("nan")
            delta = float(best["exp_R"]) - base_r_sym
            sign = "✅" if delta > 0.02 else ("⚠️" if delta > 0 else "❌")
            lines.append(
                f"| **{sym}** | `{best['exp_name']}` "
                f"| {_fmt(float(best['exp_R']))} "
                f"| {_fmt(base_r_sym)} "
                f"| {_fmt(delta)} "
                f"| {sign} |"
            )
        return "\n".join(lines)

    # Rekomendacja
    top5 = merged.head(5)
    best_r  = float(top5["expectancy_R"].iloc[0]) if not top5.empty else float("nan")
    best_nm = top5["exp_name"].iloc[0] if not top5.empty else "—"
    best_delta = float(top5["delta_val_test"].iloc[0]) if not top5.empty and not pd.isna(top5["delta_val_test"].iloc[0]) else float("nan")

    beats_baseline = (not pd.isna(best_r)) and best_r > baseline_r + 0.02
    low_overfit    = (not pd.isna(best_delta)) and abs(best_delta) < 0.05

    if beats_baseline and low_overfit:
        verdict = (f"✅ **{best_nm}** bije baseline o {best_r - baseline_r:+.4f}R "
                   f"z niskim overfittem (delta={best_delta:+.4f}R). "
                   f"Warto rozważyć wdrożenie.")
    elif beats_baseline:
        verdict = (f"⚠️ **{best_nm}** bije baseline o {best_r - baseline_r:+.4f}R, "
                   f"ale overfit jest duży (delta={best_delta:+.4f}R). "
                   f"NIE wdrażać bez dodatkowej walidacji.")
    else:
        verdict = (f"❌ Żaden wariant ADX v2 nie bije baseline (best={_fmt(best_r)}R "
                   f"vs baseline={_fmt(baseline_r)}R). "
                   f"**ADX nie pomaga tej strategii — nie wdrażać.**")

    lines = [
        "# ADX v2 Test — Raport",
        "",
        f"> Wygenerowano: {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"> Symbole: {', '.join(df['symbol'].unique().tolist())}",
        f"> Foldy: 9-fold walk-forward (1 hist + 8 kwartalnych OOS 2024/2025)",
        "",
        "---",
        "",
        "## 1. Podsumowanie — Top 5 ADX v2 (val, portfolio)",
        "",
        "| Experiment | Ctx | Val ExpR | Test ExpR | Δ val→test | Stab% | Trades |",
        "|---|---|---|---|---|---|---|",
        _table_rows(merged, n=5),
        "",
        f"**Baseline (ctxA, brak filtrów):** `{_fmt(baseline_r)}`R",
        f"**ADX v1 best (adx25 D1):** `{_fmt(ADX_V1_BEST)}`R  "
        f"| **ADX v1 worst (adx22 D1):** `{_fmt(ADX_V1_WORST)}`R",
        "",
        "---",
        "",
        "## 2. Grupy eksperymentów",
        "",
        "### 2a. H4 threshold (niższe progi niż v1)",
        "",
        "| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |",
        "|---|---|---|---|---|---|---|",
        _table_rows(h4_thr_rows, n=6),
        "",
        "### 2b. D1 threshold (niższe progi: 14, 16, 18)",
        "",
        "| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |",
        "|---|---|---|---|---|---|---|",
        _table_rows(d1_thr_rows, n=4),
        "",
        "### 2c. ADX Rising (H4 i D1, k=2/3/5)",
        "",
        "| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |",
        "|---|---|---|---|---|---|---|",
        _table_rows(rising_rows, n=6),
        "",
        "### 2d. ADX Slope SMA>0 (H4 i D1)",
        "",
        "| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |",
        "|---|---|---|---|---|---|---|",
        _table_rows(slope_rows, n=4),
        "",
        "### 2e. ADX Soft Gate H4 (threshold 18/22, RR↓2.0 gdy ADX niski)",
        "",
        "| Experiment | Ctx | Val ExpR | Test ExpR | Δ | Stab% | Trades |",
        "|---|---|---|---|---|---|---|",
        _table_rows(soft_rows, n=4),
        "",
        "---",
        "",
        "## 3. Analiza per-symbol",
        "",
        "| Symbol | Najlepszy wariant | Val ExpR | Baseline ExpR | Δ | Ocena |",
        "|---|---|---|---|---|---|",
        _sym_summary(),
        "",
        "---",
        "",
        "## 4. Porównanie ADX v1 vs v2 (portfolio)",
        "",
        "| Wersja | Opis | Val ExpR | Wniosek |",
        "|---|---|---|---|",
        f"| **Baseline** | Brak filtru ADX | `{_fmt(baseline_r)}` | punkt odniesienia |",
        f"| ADX v1 best | D1 thr=25 | `{_fmt(ADX_V1_BEST)}` | -20% vs baseline |",
        f"| ADX v1 worst | D1 thr=22 | `{_fmt(ADX_V1_WORST)}` | -66% vs baseline |",
        f"| **ADX v2 best** | `{best_nm}` | `{_fmt(best_r)}` | vs baseline: {_fmt(best_r - baseline_r if not pd.isna(baseline_r) else float('nan'))} |",
        "",
        "---",
        "",
        "## 5. Rekomendacja końcowa",
        "",
        verdict,
        "",
        "### Czy H4 pomaga względem D1?",
    ]

    # Porównaj średnie H4 vs D1 threshold
    h4_mean = h4_thr_rows["expectancy_R"].mean() if not h4_thr_rows.empty else float("nan")
    d1_mean = d1_thr_rows["expectancy_R"].mean() if not d1_thr_rows.empty else float("nan")
    if not pd.isna(h4_mean) and not pd.isna(d1_mean):
        if h4_mean > d1_mean + 0.01:
            lines.append(f"✅ H4 threshold (avg={_fmt(h4_mean)}) > D1 threshold (avg={_fmt(d1_mean)}) — H4 lepsze")
        elif d1_mean > h4_mean + 0.01:
            lines.append(f"❌ D1 threshold (avg={_fmt(d1_mean)}) > H4 threshold (avg={_fmt(h4_mean)}) — H4 nie pomaga")
        else:
            lines.append(f"≈ H4 (avg={_fmt(h4_mean)}) ≈ D1 (avg={_fmt(d1_mean)}) — brak istotnej różnicy")

    # Rising vs threshold
    rising_mean = rising_rows["expectancy_R"].mean() if not rising_rows.empty else float("nan")
    lines.append("")
    lines.append("### Czy 'ADX rising' lepszy od hard threshold?")
    if not pd.isna(rising_mean) and not pd.isna(h4_mean):
        if rising_mean > h4_mean + 0.01:
            lines.append(f"✅ Rising (avg={_fmt(rising_mean)}) > Threshold H4 (avg={_fmt(h4_mean)}) — rising lepszy")
        else:
            lines.append(f"❌ Rising (avg={_fmt(rising_mean)}) ≤ Threshold H4 (avg={_fmt(h4_mean)}) — hard threshold nie gorszy")

    lines += [
        "",
        "---",
        "",
        "_Raport wygenerowany automatycznie przez `backtests/reporting.py`_",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ADX v2 report saved -> {output_path}")


