"""
Quick test to see what current_time is
"""
import pandas as pd

# Load bars
df = pd.read_csv('data/bars/gbpusd_1h_bars.csv', parse_dates=['timestamp'])
df.set_index('timestamp', inplace=True)

print(f"Index type: {type(df.index)}")
print(f"Index dtype: {df.index.dtype}")
print(f"\nFirst 3 index values:")
for i in range(3):
    idx_val = df.index[i]
    print(f"  [{i}] Type: {type(idx_val)}, Value: {idx_val}")
    print(f"       .isoformat(): {idx_val.isoformat()}")
    print(f"       str(): {str(idx_val)}")

