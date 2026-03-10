import pandas as pd
from pathlib import Path

base = Path(r'C:\dev\projects\BojkoFx\data\raw_dl')

symbols = ['audjpy', 'eurchf', 'eurusd', 'usdjpy', 'gbpjpy', 'cadjpy', 'eurjpy', 'eurgbp']
for sym in symbols:
    f = base / f'{sym}_m30_bid_2021_2024.csv'
    if not f.exists():
        print(f'{sym}: FILE NOT FOUND')
        continue
    df = pd.read_csv(f)
    df.columns = [c.lower().strip() for c in df.columns]
    tcol = next((c for c in df.columns if any(x in c for x in ['time','date','gmt','timestamp'])), df.columns[0])
    n = len(df)
    # expected M30 bars for 4 years = ~70080 (trading 24h) or ~48000 (session only)
    print(f'{sym:10s}: {n:>7,} rows  |  {df[tcol].iloc[0]}  ->  {df[tcol].iloc[-1]}')

