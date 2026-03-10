#!/bin/bash
# Full IBKR dashboard deploy v2
set -e
cd /home/macie/bojkofx/app

echo "=== git pull ==="
git pull origin master

echo "=== restart dashboard ==="
sudo systemctl restart bojkofx-dashboard
sleep 5

echo "=== status ==="
sudo systemctl is-active bojkofx-dashboard

echo "=== last log lines ==="
tail -6 /home/macie/bojkofx/logs/dashboard.log 2>/dev/null || echo no_log

echo "=== endpoint tests ==="
KEY=$(grep DASHBOARD_API_KEY /home/macie/bojkofx/config/ibkr.env | cut -d= -f2)
for ep in health status "candles/EURUSD" "candles/USDJPY" log_tail "trades/EURUSD" equity_history; do
    code=$(curl -s -o /tmp/ep_out.txt -w "%{http_code}" -H "X-API-Key: $KEY" "http://localhost:8080/api/$ep")
    body=$(head -c 80 /tmp/ep_out.txt)
    echo "  $ep => $code | $body"
done

echo "=== restart bot (apply live bars export) ==="
sudo systemctl restart bojkofx
sleep 5
sudo systemctl is-active bojkofx

echo "=== DEPLOY_DONE ==="

