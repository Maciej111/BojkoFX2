"""Seed live_bars from validated historical data."""
import pandas as pd, pathlib

BASE = pathlib.Path('/home/macie/bojkofx/app/data')
SYMS = ['EURUSD','USDJPY','USDCHF','AUDJPY','CADJPY']

(BASE / 'live_bars').mkdir(parents=True, exist_ok=True)

for sym in SYMS:
    src = BASE / 'bars_validated' / f'{sym.lower()}_1h_validated.csv'
    dst = BASE / 'live_bars' / f'{sym}.csv'
    if not src.exists() or src.stat().st_size < 10:
        print(f'SKIP {sym} - missing or empty: {src}')
        continue
    df = pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    ts_col = next((c for c in df.columns if 'time' in c or 'date' in c or c == 'datetime'), df.columns[0])
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors='coerce')
    df = df.dropna(subset=[ts_col]).sort_values(ts_col).tail(200)
    if 'open' not in df.columns and 'open_bid' in df.columns:
        df['open']  = (df['open_bid']  + df['open_ask'])  / 2
        df['high']  = (df['high_bid']  + df['high_ask'])  / 2
        df['low']   = (df['low_bid']   + df['low_ask'])   / 2
        df['close'] = (df['close_bid'] + df['close_ask']) / 2
    if 'volume' not in df.columns:
        df['volume'] = 0
    df = df.rename(columns={ts_col: 'datetime'}).set_index('datetime')
    df[['open','high','low','close','volume']].to_csv(dst)
    print(f'OK {sym}: {len(df)} bars -> {dst.name}')

print('SEED_DONE')


