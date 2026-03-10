import pandas as pd
import numpy as np
from pathlib import Path

base = Path(r'C:\dev\projects\BojkoFx\data\raw_dl')

# Sprawdzamy gęstość barów — ile % slotów M30 jest wypełnionych
# 4 lata = 2021-01-01 do 2024-12-31 = ~1461 dni * 48 barów/dzień = 70128 M30 slotów (max 24h)

TOTAL_SLOTS_24H = 70080  # ~4 lata × 365.25 × 48 barów M30

symbols = ['eurusd', 'usdjpy', 'gbpjpy', 'eurjpy', 'eurgbp', 'audjpy', 'cadjpy', 'eurchf', 'gbpchf', 'usdchf', 'gbpusd']

print(f"{'Symbol':10s} {'Raw rows':>10} {'Density':>8}  Diagnoza")
print("-" * 65)
for sym in symbols:
    f = base / f'{sym}_m30_bid_2021_2024.csv'
    if not f.exists():
        print(f'{sym:10s}  FILE NOT FOUND')
        continue
    n = sum(1 for _ in open(f)) - 1
    density = n / TOTAL_SLOTS_24H * 100

    if density > 80:
        diag = "✅ Pełne dane — aktywna para"
    elif density > 40:
        diag = "🟡 Normalne — sesyjna para (nie 24h)"
    elif density > 20:
        diag = "⚠️  Niski wolumen — mało aktywna"
    else:
        diag = "❌ Bardzo mało danych — egzotyczna / SNB/interwencje"

    print(f'{sym:10s} {n:>10,}  {density:>7.1f}%  {diag}')

