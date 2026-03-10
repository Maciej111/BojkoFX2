from pathlib import Path
dirs = ['data/bars_validated','data/raw_dl_fx','data/raw_dl_fx/download',
        'data/raw_dl_fx/download/m60','data/raw_dl_fx/download/m30','data/live_bars']
for d in dirs:
    p = Path(d)
    if p.exists():
        files = [f.name for f in sorted(p.glob('*.csv'))][:10]
        print(f"{d}/  -> {files}")
    else:
        print(f"{d}/  MISSING")

# Also check first few rows of any found CSV
import pandas as pd
for d in ['data/raw_dl_fx/download/m60','data/bars_validated','data/live_bars']:
    p = Path(d)
    if p.exists():
        csvs = list(p.glob('*.csv'))
        if csvs:
            print(f"\n--- {csvs[0]} (head 3) ---")
            try:
                df = pd.read_csv(csvs[0], nrows=3)
                print(df.to_string())
                print("Columns:", list(df.columns))
                print("Shape:", df.shape)
            except Exception as e:
                print("Error:", e)

