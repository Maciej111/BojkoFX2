#!/bin/bash
KEY=$(grep DASHBOARD_API_KEY /home/macie/bojkofx/config/ibkr.env | cut -d= -f2)
echo "Using key: ${KEY:0:8}..."
BASE="http://localhost:8080/api"

for ep in health "candles/EURUSD" "candles/USDJPY" "log_tail" "trades/EURUSD" "equity_history" "status"; do
    code=$(curl -s -o /tmp/ep_out.txt -w "%{http_code}" -H "X-API-Key: $KEY" "$BASE/$ep")
    body=$(cat /tmp/ep_out.txt | head -c 120)
    echo "$ep => HTTP $code | $body"
done
echo "ALL_DONE"

