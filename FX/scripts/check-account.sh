#!/usr/bin/env bash
cd /home/macie/bojkofx/app
/home/macie/bojkofx/venv/bin/python << 'EOF'
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 4002, clientId=88, timeout=15)
print('Konto:', ib.managedAccounts())
print()
print('=== Wartosci konta ===')
for av in ib.accountValues():
    if av.tag in ('TotalCashValue','NetLiquidation','AvailableFunds',
                  'BuyingPower','GrossPositionValue','CashBalance'):
        print(f'  {av.tag:30s} {av.currency:5s} {av.value}')
print()
print('=== Pozycje ===')
for p in ib.positions():
    print(f'  {p.contract.symbol:10s} {p.position:10.0f} @ {p.avgCost:.5f}')
if not ib.positions():
    print('  (brak pozycji)')
ib.disconnect()
EOF

