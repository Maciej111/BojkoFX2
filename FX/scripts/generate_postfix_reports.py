"""
Generate POST-FIX Reports
"""
import pandas as pd

print("Generating POST-FIX reports...")

# Load results
try:
    grid_results = pd.read_csv('data/outputs/postfix_grid_results.csv')
    print(f"[OK] Grid results: {len(grid_results)} configs")
except:
    print("[ERROR] Grid results not found")
    grid_results = None

try:
    oos_results = pd.read_csv('data/outputs/postfix_oos2024_results.csv')
    print(f"[OK] OOS 2024 results: {len(oos_results)} configs")
except:
    print("[ERROR] OOS results not found")
    oos_results = None

try:
    wf_results = pd.read_csv('data/outputs/postfix_walkforward_results.csv')
    print(f"[OK] Walk-forward results: {len(wf_results)} windows")
except:
    print("[ERROR] WF results not found")
    wf_results = None

print()

# GRID REPORT
if grid_results is not None:
    with open('reports/POSTFIX_GRID_REPORT.md', 'w', encoding='utf-8') as f:
        f.write("# POST-FIX GRID SEARCH REPORT\\n\\n")
        f.write("**Date:** 2026-02-18\\n")
        f.write("**Engine:** FIX2 (0 impossible exits)\\n")
        f.write("**Train:** 2021-2022\\n")
        f.write("**Validate:** 2023\\n\\n")
        f.write("---\\n\\n")
        
        f.write("## Summary\\n\\n")
        f.write(f"- Total configurations tested: {len(grid_results)}\\n")
        
        if 'val_exp' in grid_results.columns:
            positive = (grid_results['val_exp'] > 0).sum()
            f.write(f"- Positive validate expectancy: {positive}/{len(grid_results)}\\n")
            f.write(f"- Best validate expectancy: {grid_results['val_exp'].max():.4f}R\\n")
            f.write(f"- Mean validate expectancy: {grid_results['val_exp'].mean():.4f}R\\n\\n")
        
        f.write("## TOP 10 Configurations\\n\\n")
        
        if 'val_exp' in grid_results.columns:
            top10 = grid_results.nlargest(10, 'val_exp')
            f.write(top10.to_markdown(index=False))
        
        f.write("\\n\\n---\\n")
        f.write("*Report generated: 2026-02-18*\\n")
    
    print("[OK] Saved: reports/POSTFIX_GRID_REPORT.md")

# OOS REPORT
if oos_results is not None:
    with open('reports/POSTFIX_OOS_2024_REPORT.md', 'w', encoding='utf-8') as f:
        f.write("# POST-FIX OOS TEST 2024\\n\\n")
        f.write("**Test Period:** 2024 (Out-of-Sample)\\n")
        f.write("**Configurations:** TOP3 from grid search\\n\\n")
        f.write("---\\n\\n")
        
        f.write("## Results\\n\\n")
        f.write(oos_results.to_markdown(index=False))
        
        f.write("\\n\\n## Analysis\\n\\n")
        if 'test_expectancy' in oos_results.columns:
            f.write(f"- Best OOS expectancy: {oos_results['test_expectancy'].max():.4f}R\\n")
            f.write(f"- Mean OOS expectancy: {oos_results['test_expectancy'].mean():.4f}R\\n")
            positive = (oos_results['test_expectancy'] > 0).sum()
            f.write(f"- Positive configs: {positive}/{len(oos_results)}\\n")
        
        f.write("\\n\\n---\\n")
        f.write("*Report generated: 2026-02-18*\\n")
    
    print("[OK] Saved: reports/POSTFIX_OOS_2024_REPORT.md")

# WF REPORT
if wf_results is not None:
    with open('reports/POSTFIX_WALKFORWARD_REPORT.md', 'w', encoding='utf-8') as f:
        f.write("# POST-FIX WALK-FORWARD REPORT\\n\\n")
        f.write("**Method:** Rolling 2-year train, 1-year test\\n\\n")
        f.write("---\\n\\n")
        
        f.write("## Results\\n\\n")
        f.write(wf_results.to_markdown(index=False))
        
        f.write("\\n\\n## Summary\\n\\n")
        if 'test_expectancy' in wf_results.columns:
            f.write(f"- Average test expectancy: {wf_results['test_expectancy'].mean():.4f}R\\n")
            positive = (wf_results['test_expectancy'] > 0).sum()
            f.write(f"- Positive test periods: {positive}/{len(wf_results)}\\n")
        
        f.write("\\n\\n---\\n")
        f.write("*Report generated: 2026-02-18*\\n")
    
    print("[OK] Saved: reports/POSTFIX_WALKFORWARD_REPORT.md")

print()
print("Report generation complete!")

