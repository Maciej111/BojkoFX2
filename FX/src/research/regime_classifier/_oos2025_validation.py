"""
Detailed OOS 2025 validation for EURUSD.
Reads both 2023-2024 and 2025 results and prints a full comparison.
Also restores the 2023-2024 CSV as the canonical grid search file.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
from src.research.regime_classifier.grid_search import run_grid_search

ROOT = Path(__file__).resolve().parents[3]
RESEARCH_DIR = ROOT / "data" / "research"

# ── Run 2023-2024 (restore canonical) ────────────────────────────────────────
print("=" * 60)
print("Running 2023-2024 (IS validation / canonical)")
print("=" * 60)
df_2324 = run_grid_search(
    symbols=["EURUSD"],
    start="2023-01-01",
    end="2024-12-31",
    output_path=str(RESEARCH_DIR / "regime_grid_search.csv"),
    verbose=True,
)

# ── Run 2025 (OOS) ────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("Running 2025 OOS validation")
print("=" * 60)
df_2025 = run_grid_search(
    symbols=["EURUSD"],
    start="2025-01-01",
    end="2025-12-31",
    output_path=str(RESEARCH_DIR / "regime_grid_search_oos2025.csv"),
    verbose=True,
)

# ── Compare all 18 configs: 2023-2024 vs 2025 ────────────────────────────────
print()
print("=" * 60)
print("COMPARISON: 2023-2024 (in-sample) vs 2025 (OOS)")
print("=" * 60)

key_cols  = ["trend_enter", "chop_enter", "high_vol_threshold"]
merge_key = key_cols

df_m = pd.merge(
    df_2324[key_cols + ["trades_allowed", "trades_filtered_pct",
                         "win_rate", "expectancy_R", "profit_factor",
                         "max_dd_pct", "filter_precision"]],
    df_2025[key_cols + ["trades_allowed", "trades_filtered_pct",
                         "win_rate", "expectancy_R", "profit_factor",
                         "max_dd_pct", "filter_precision"]],
    on=merge_key,
    suffixes=("_2324", "_2025"),
)

df_m["expR_delta"] = df_m["expectancy_R_2025"] - df_m["expectancy_R_2324"]
df_m = df_m.sort_values("expectancy_R_2324", ascending=False)

print(f"\n{'te':>4} {'ce':>4} {'hvt':>5} | "
      f"{'n_2324':>7} {'ExpR_2324':>10} {'WR_2324':>8} | "
      f"{'n_2025':>7} {'ExpR_2025':>10} {'WR_2025':>8} | "
      f"{'Δ ExpR':>8}")
print("-" * 95)
for _, r in df_m.iterrows():
    print(f"{r.trend_enter:>4.1f} {r.chop_enter:>4.1f} {r.high_vol_threshold:>5.0f} | "
          f"{r.trades_allowed_2324:>7.0f} {r.expectancy_R_2324:>+10.4f} {r.win_rate_2324:>7.1%} | "
          f"{r.trades_allowed_2025:>7.0f} {r.expectancy_R_2025:>+10.4f} {r.win_rate_2025:>7.1%} | "
          f"{r.expR_delta:>+8.4f}")

# ── Target config ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("TARGET CONFIG: te=0.6, ce=0.7, hvt=80")
print("=" * 60)
target_2324 = df_2324[
    (df_2324.trend_enter == 0.6) &
    (df_2324.chop_enter  == 0.7) &
    (df_2324.high_vol_threshold == 80.0)
].iloc[0]
target_2025 = df_2025[
    (df_2025.trend_enter == 0.6) &
    (df_2025.chop_enter  == 0.7) &
    (df_2025.high_vol_threshold == 80.0)
].iloc[0]

metrics = [
    ("Trades allowed",    "trades_allowed",       "7.0f"),
    ("Filtered %",        "trades_filtered_pct",  "6.1f"),
    ("Win Rate",          "win_rate",             "6.1%"),
    ("Expectancy R",      "expectancy_R",         "7.4f"),
    ("Profit Factor",     "profit_factor",        "7.3f"),
    ("Max DD %",          "max_dd_pct",           "7.2f"),
    ("Filter precision",  "filter_precision",     "6.1%"),
]
print(f"\n{'Metric':<20} {'2023-2024':>12} {'2025 OOS':>12} {'Delta':>10}")
print("-" * 58)
for label, col, fmt in metrics:
    v1 = target_2324[col]
    v2 = target_2025[col]
    try:
        delta = f"{v2 - v1:+.4f}"
    except Exception:
        delta = "—"
    print(f"{label:<20} {v1:>12{fmt}} {v2:>12{fmt}} {delta:>10}")

print()
print("VERDICT:")
expR_2324 = float(target_2324["expectancy_R"])
expR_2025 = float(target_2025["expectancy_R"])
if expR_2025 > 0.1:
    v = "✅ HOLDS — konfiguracja działa również w 2025"
elif expR_2025 > 0:
    v = "⚠️  MARGINAL — lekko pozytywna w 2025, ale wyraźna regresja vs 2023-2024"
else:
    v = "❌ FAILS OOS — konfiguracja nie działa w danych 2025 (prawdopodobny overfitting)"
print(f"  {v}")
print(f"  ExpR 2023-2024: {expR_2324:+.4f}  →  2025 OOS: {expR_2025:+.4f}  (Δ={expR_2025-expR_2324:+.4f})")

# ── Best config in 2025 ───────────────────────────────────────────────────────
best_2025 = df_2025.loc[df_2025["expectancy_R"].idxmax()]
print()
print("Best config IN 2025:")
print(f"  te={best_2025.trend_enter} ce={best_2025.chop_enter} hvt={best_2025.high_vol_threshold:.0f} "
      f"→ ExpR={best_2025.expectancy_R:+.4f}  WR={best_2025.win_rate:.1%}  "
      f"filtered={best_2025.trades_filtered_pct:.0f}%")

# ── Save combined results ─────────────────────────────────────────────────────
df_2324["period"] = "2023-2024"
df_2025["period"] = "2025-OOS"
combined = pd.concat([df_2324, df_2025], ignore_index=True)
out_path = RESEARCH_DIR / "regime_grid_search_combined.csv"
combined.to_csv(out_path, index=False)
print(f"\nCombined results saved: {out_path}")


