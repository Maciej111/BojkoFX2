#!/usr/bin/env bash
set -euo pipefail

echo "[1] Deploy new IBC config (ReadOnlyApi=no)"
sudo cp /tmp/ibc-config-readonlyno.ini /opt/ibc/config.ini
sudo chown macie:macie /opt/ibc/config.ini
sudo chmod 600 /opt/ibc/config.ini
echo "  Deployed:"
grep -E "ReadOnly|AllowApi|Command" /opt/ibc/config.ini

echo ""
echo "[2] Stop gateway"
sudo systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
sleep 3

echo ""
echo "[3] Patch jts.ini"
sed -i '/^ReadOnlyApi=/d; /^AllowApiWriteAccess=/d' /home/macie/Jts/jts.ini
sed -i '/^\[IBGateway\]/a ReadOnlyApi=false\nAllowApiWriteAccess=yes' /home/macie/Jts/jts.ini

echo ""
echo "[4] Start gateway"
sudo systemctl start ibgateway
echo "  Waiting 90s for IBC to login AND configure ReadOnlyApi..."
sleep 90

echo ""
echo "[5] Checks"
ss -tlnp | grep 4002 && echo "PORT 4002 OPEN" || echo "PORT NOT OPEN"
echo ""
echo "  Gateway log tail (last 20 lines):"
tail -20 /home/macie/bojkofx/logs/gateway.log

echo ""
echo "[6] Run order test"
pkill -9 -f "python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

