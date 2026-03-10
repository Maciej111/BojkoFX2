#!/usr/bin/env bash
pkill -9 -f 'python.*test_order' 2>/dev/null || true
sleep 1
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py
echo "EXIT: $?"

