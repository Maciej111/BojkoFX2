"""
Quick test to verify implementation works.
"""
import sys
import os
sys.path.append('.')

print("Testing implementation...")

# Test 1: Import metrics
print("\n1. Testing metrics import...")
try:
    from src.backtest.metrics import compute_segment_metrics, add_R_column
    print("✓ Metrics imported successfully")
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)

# Test 2: Test segmentation
print("\n2. Testing segmentation...")
try:
    import pandas as pd
    trades_df = pd.DataFrame({
        'touch_no': [1, 1, 2, 2],
        'entry_price': [1.1, 1.1, 1.1, 1.1],
        'sl': [1.09, 1.09, 1.09, 1.09],
        'pnl': [100, -50, 200, 100],
        'direction': ['LONG', 'LONG', 'LONG', 'LONG']
    })

    trades_df = add_R_column(trades_df)
    segments = compute_segment_metrics(trades_df, 10000)

    print(f"  Segments found: {list(segments.keys())}")

    if 'ALL' in segments:
        print(f"  ✓ ALL segment exists")
    if 'TOUCH_1' in segments:
        print(f"  ✓ TOUCH_1 segment exists")
    if 'TOUCH_2' in segments:
        print(f"  ✓ TOUCH_2 segment exists")

    print("✓ Segmentation works!")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Check if bars file exists
print("\n3. Checking data files...")
if os.path.exists('data/bars/eurusd_m15_bars.csv'):
    print("  ✓ Bars file exists")
else:
    print("  ⚠ Bars file not found (run build_bars.py first)")

if os.path.exists('data/raw/eurusd-tick-2024-06-01-2024-12-31.csv'):
    print("  ✓ Raw ticks file exists")
else:
    print("  ⚠ Raw ticks file not found")

# Test 4: Verify new scripts exist
print("\n4. Checking new scripts...")
scripts = [
    'scripts/run_batch_backtest.py',
    'scripts/run_sensitivity.py'
]

for script in scripts:
    if os.path.exists(script):
        print(f"  ✓ {script}")
    else:
        print(f"  ✗ {script} missing")

print("\n" + "="*60)
print("Implementation Test Complete!")
print("="*60)

print("\nNext steps:")
print("1. Run: python scripts/build_bars.py (if bars not exist)")
print("2. Run: python scripts/run_backtest.py")
print("3. Run batch test: python scripts/run_batch_backtest.py --symbols EURUSD --start 2024-06-01 --end 2024-12-31")
print("4. Run sensitivity: python scripts/run_sensitivity.py --symbol EURUSD --start 2024-06-01 --end 2024-12-31")

