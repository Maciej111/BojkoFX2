"""Print comparison table from saved CSV files (no re-run needed)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pandas as pd

RESEARCH_DIR = Path(__file__).resolve().parents[3] / "data" / "research"

df_2324 = pd.read_csv(RESEARCH_DIR / "regime_grid_search.csv")
df_2025 = pd.read_csv(RESEARCH_DIR / "regime_grid_search_oos2025.csv")

key_cols = ["trend_enter", "chop_enter", "high_vol_threshold"]

df_m = pd.merge(
    df_2324[key_cols + ["trades_allowed", "trades_filtered_pct",
                        "win_rate", "expectancy_R", "profit_factor",
                        "max_dd_pct", "filter_precision"]],
    df_2025[key_cols + ["trades_allowed", "trades_filtered_pct",
                        "win_rate", "expectancy_R", "profit_factor",
                        "max_dd_pct", "filter_precision"]],
    on=key_cols, suffixes=("_2324", "_2025"),
)
df_m["expR_delta"] = df_m["expectancy_R_2025"] - df_m["expectancy_R_2324"]
df_m = df_m.sort_values("expectancy_R_2324", ascending=False)

print("\nCOMPARISON: 2023-2024 (IS) vs 2025 (OOS) — EURUSD")
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
t4 = df_m[(df_m.trend_enter == 0.6) & (df_m.chop_enter == 0.7) & (df_m.high_vol_threshold == 80)].iloc[0]

print()
print("=" * 60)
print("TARGET CONFIG: te=0.6, ce=0.7, hvt=80")
print("=" * 60)
rows = [
    ("Trades allowed",   t4.trades_allowed_2324,    t4.trades_allowed_2025),
    ("Filtered %",       t4.trades_filtered_pct_2324, t4.trades_filtered_pct_2025),
    ("Win Rate",         t4.win_rate_2324,           t4.win_rate_2025),
    ("Expectancy R",     t4.expectancy_R_2324,       t4.expectancy_R_2025),
    ("Profit Factor",    t4.profit_factor_2324,      t4.profit_factor_2025),
    ("Max DD %",         t4.max_dd_pct_2324,         t4.max_dd_pct_2025),
    ("Filter precision", t4.filter_precision_2324,   t4.filter_precision_2025),
]
print(f"\n{'Metric':<20} {'2023-2024':>12} {'2025 OOS':>12} {'Delta':>12}")
print("-" * 60)
for label, v1, v2 in rows:
    delta = v2 - v1
    print(f"{label:<20} {v1:>12.4f} {v2:>12.4f} {delta:>+12.4f}")

print()
expR_2324 = t4.expectancy_R_2324
expR_2025 = t4.expectancy_R_2025
if expR_2025 > 0.1:
    verdict = "✅ HOLDS"
elif expR_2025 > 0:
    verdict = "⚠️  MARGINAL"
else:
    verdict = "❌ FAILS OOS"
print(f"VERDICT: {verdict}")
print(f"  ExpR IS 2023-2024 : {expR_2324:+.4f}")
print(f"  ExpR OOS 2025     : {expR_2025:+.4f}  (Δ={expR_2025-expR_2324:+.4f})")

# ── Best config in 2025 ───────────────────────────────────────────────────────
best = df_2025.loc[df_2025["expectancy_R"].idxmax()]
print()
print(f"Best config IN 2025:  te={best.trend_enter} ce={best.chop_enter} hvt={best.high_vol_threshold:.0f}")
print(f"  ExpR={best.expectancy_R:+.4f}  WR={best.win_rate:.1%}  filtered={best.trades_filtered_pct:.0f}%  PF={best.profit_factor:.3f}")

# ── Save combined ─────────────────────────────────────────────────────────────
df_2324c = df_2324.copy(); df_2324c["period"] = "2023-2024"
df_2025c = df_2025.copy(); df_2025c["period"] = "2025-OOS"
pd.concat([df_2324c, df_2025c]).to_csv(
    RESEARCH_DIR / "regime_grid_search_combined.csv", index=False)
print(f"\nCombined CSV: data/research/regime_grid_search_combined.csv")

