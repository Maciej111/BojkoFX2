#!/bin/bash
# Diagnozuje dlaczego bot nie zamyka barow H1
# Sprawdza: czy ticki przychodza, czy ibkr_marketdata widzi dane
cd /home/macie/bojkofx/app

/home/macie/bojkofx/venv/bin/python << 'PYEOF'
import sys
sys.path.insert(0, '.')
from ib_insync import IB, Forex
import time

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=99, timeout=15)
print(f"Connected: {ib.isConnected()}")

# Sprawdz aktualne kwotowania
for sym in ['EURUSD', 'GBPUSD', 'USDJPY']:
    contract = Forex(sym)
    ticker = ib.reqMktData(contract, '', False, False)
    ib.sleep(2)
    print(f"{sym}: bid={ticker.bid}  ask={ticker.ask}  last={ticker.last}  halted={ticker.halted}")

# Sprawdz czy rynek otwarty
import datetime
now = datetime.datetime.utcnow()
print(f"\nUTC now: {now}")
print(f"Weekday: {now.strftime('%A')}  (0=Mon, 6=Sun = {now.weekday()})")
print(f"Forex weekend: Fri 22:00 UTC - Sun 22:00 UTC")
is_weekend = (now.weekday() == 4 and now.hour >= 22) or \
             (now.weekday() == 5) or \
             (now.weekday() == 6 and now.hour < 22)
print(f"Rynek zamkniety (weekend): {is_weekend}")

ib.disconnect()
PYEOF

