#!/bin/bash
sudo systemctl restart bojkofx-dashboard
sleep 5
echo "STATUS:$(systemctl is-active bojkofx-dashboard)"
tail -5 /home/macie/bojkofx/logs/dashboard.log 2>/dev/null
KEY=$(grep DASHBOARD_API_KEY /home/macie/bojkofx/config/ibkr.env | cut -d= -f2)
for ep in health "candles/EURUSD" "candles/USDJPY" log_tail status; do
    code=$(curl -s -o /tmp/t.txt -w "%{http_code}" -H "X-API-Key: $KEY" "http://localhost:8080/api/$ep")
    body=$(head -c 60 /tmp/t.txt)
    echo "$ep => $code | $body"
done
echo RESTART_DONE

