import pandas as pd, sys

for fn in ['eurusd_m30_bid_2021_2024', 'eurusd_m30_ask_2021_2024']:
    path = f'C:/dev/projects/BojkoFx/data/raw_dl/{fn}.csv'
    df = pd.read_csv(path)
    print(f"{fn}: cols={list(df.columns)}, rows={len(df)}, ts_sample={df.iloc[0,0]}")
    df.columns = [c.strip().lower() for c in df.columns]
    df['ts'] = pd.to_datetime(df['timestamp'], unit='ms')
    print(f"  Range: {df['ts'].min()} -> {df['ts'].max()}")
    print(f"  Head:\n{df.head(2).to_string()}")
    print()

