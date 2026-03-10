import pandas as pd

# Quick check of bars
try:
    df = pd.read_csv('data/bars/eurusd_1h_bars.csv', nrows=10)
    print("First 10 rows of H1 bars:")
    print(df[['timestamp']])
    print()

    # Count total
    df_full = pd.read_csv('data/bars/eurusd_1h_bars.csv')
    print(f"Total H1 bars: {len(df_full)}")
    print(f"First: {df_full['timestamp'].iloc[0]}")
    print(f"Last: {df_full['timestamp'].iloc[-1]}")

    # Check 2024
    df_full['timestamp'] = pd.to_datetime(df_full['timestamp'])
    df_2024 = df_full[df_full['timestamp'].dt.year == 2024]
    print(f"\n2024 bars: {len(df_2024)}")
    if len(df_2024) > 0:
        print(f"2024 first: {df_2024['timestamp'].min()}")
        print(f"2024 last: {df_2024['timestamp'].max()}")

except Exception as e:
    print(f"Error: {e}")

