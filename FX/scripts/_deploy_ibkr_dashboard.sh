#!/bin/bash
# Deploy IBKR-adapted dashboard to VM
set -e

echo "=== Pulling latest code ==="
cd /home/macie/bojkofx/app
git pull origin master

echo "=== Restarting dashboard service ==="
sudo systemctl restart bojkofx-dashboard
sleep 4

echo "=== Service status ==="
sudo systemctl is-active bojkofx-dashboard

echo "=== Last 10 log lines ==="
tail -10 /home/macie/bojkofx/logs/dashboard.log 2>/dev/null || echo "(no log yet)"

echo "=== Health check ==="
curl -s http://localhost:8080/api/health

echo ""
echo "=== Status check (no trades yet is OK) ==="
curl -s -H "X-API-Key: $(grep DASHBOARD_API_KEY /home/macie/bojkofx/config/ibkr.env | cut -d= -f2)" \
     http://localhost:8080/api/status | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    p=d.get('portfolio',{})
    print(f'  bot_alive    : {d.get(\"bot_alive\")}')
    print(f'  equity       : {p.get(\"equity\")}')
    print(f'  open_positions: {p.get(\"open_positions\")}')
    print(f'  trades_total : {p.get(\"trades_closed_total\")}')
    syms=d.get('symbols',{})
    for sym,s in syms.items():
        print(f'  {sym}: pos={s.get(\"pos\")} trades={s.get(\"trades_closed_total\")}')
except Exception as e:
    print('Parse error:', e)
    print(sys.stdin.read()[:200])
" 2>/dev/null

echo ""
echo "=== Candles check (EURUSD) ==="
curl -s -o /dev/null -w "EURUSD candles HTTP: %{http_code}\n" \
     -H "X-API-Key: $(grep DASHBOARD_API_KEY /home/macie/bojkofx/config/ibkr.env | cut -d= -f2)" \
     http://localhost:8080/api/candles/EURUSD

echo "=== Log tail check ==="
curl -s -o /dev/null -w "log_tail HTTP: %{http_code}\n" \
     -H "X-API-Key: $(grep DASHBOARD_API_KEY /home/macie/bojkofx/config/ibkr.env | cut -d= -f2)" \
     http://localhost:8080/api/log_tail

echo ""
echo "=== IBKR Dashboard deploy DONE ==="

