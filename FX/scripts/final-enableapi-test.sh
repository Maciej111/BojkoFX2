#!/usr/bin/env bash
# final-enableapi-test.sh
set -euo pipefail

BOJKOFX_DIR="/home/macie/bojkofx"
IBC_DIR="/opt/ibc"

echo "[1] Deploy config.ini z CommandServerPort=7462"
sudo cp /tmp/ibc-config-final.ini "${IBC_DIR}/config.ini"
sudo chown macie:macie "${IBC_DIR}/config.ini"
sudo chmod 600 "${IBC_DIR}/config.ini"
grep "CommandServer\|AllowApi\|ReadOnly" "${IBC_DIR}/config.ini"
echo "  OK"

echo ""
echo "[2] Stop gateway + clean session"
sudo systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
pkill -f openbox 2>/dev/null || true
sleep 3

echo ""
echo "[3] Patch jts.ini"
sed -i '/^ReadOnlyApi=/d; /^AllowApiWriteAccess=/d' /home/macie/Jts/jts.ini
sed -i '/^\[IBGateway\]/a ReadOnlyApi=false\nAllowApiWriteAccess=yes' /home/macie/Jts/jts.ini
echo "  jts.ini OK"

echo ""
echo "[4] Start gateway"
sudo systemctl start ibgateway
echo "  Waiting 80s for IBC auto-login..."
sleep 80

echo ""
echo "[5] Checks"
ss -tlnp | grep 4002 && echo "PORT 4002 OPEN" || echo "PORT 4002 NOT OPEN"
ss -tlnp | grep 7462 && echo "IBC CommandServer PORT 7462 OPEN" || echo "CommandServer port 7462 not open"

echo ""
echo "[6] Send ENABLEAPI command"
"${IBC_DIR}/enableapi.sh" && echo "  ENABLEAPI sent OK" || echo "  ENABLEAPI failed"
sleep 3

echo ""
echo "[7] Run order round-trip test"
cd "${BOJKOFX_DIR}/app"
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

