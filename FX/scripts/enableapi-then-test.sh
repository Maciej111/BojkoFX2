#!/usr/bin/env bash
echo "=== ENABLEAPI status ==="
/opt/ibc/enableapi.sh
echo "EXIT: $?"

sleep 3

echo ""
echo "=== Order test ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

