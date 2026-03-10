#!/usr/bin/env bash
# fix-gatewaystart.sh — run as: sudo bash /tmp/fix-gatewaystart.sh
set -euo pipefail

BOJKOFX_DIR="/home/macie/bojkofx"
IBC_DIR="/opt/ibc"
IBGW_DIR="/home/macie/ibgateway"

source "${BOJKOFX_DIR}/config/ibkr.env"
echo "Credentials loaded: user=${IB_USERNAME}"

echo "[1] Write corrected gatewaystart.sh (no --log-path)"
cat > "${IBC_DIR}/gatewaystart.sh" << GWSTART
#!/bin/bash
# IBC Gateway start — auto-configured for BojkoFx (no --log-path)

exec "${IBC_DIR}/scripts/ibcstart.sh" "1037" -g \
    --tws-path="${IBGW_DIR}" \
    --tws-settings-path="/home/macie/Jts" \
    --ibc-path="${IBC_DIR}" \
    --ibc-ini="${IBC_DIR}/config.ini" \
    --user="${IB_USERNAME}" \
    --pw="${IB_PASSWORD}" \
    --mode="paper" \
    --on2fatimeout="exit"
GWSTART

chmod 700 "${IBC_DIR}/gatewaystart.sh"
chown macie:macie "${IBC_DIR}/gatewaystart.sh"
echo "  Written OK"
echo ""
echo "Content:"
cat "${IBC_DIR}/gatewaystart.sh"

echo ""
echo "[2] Test run ibcstart.sh --help only"
"${IBC_DIR}/scripts/ibcstart.sh" --help 2>&1 | head -20 || true

echo ""
echo "[3] Restart service"
systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 3
systemctl start ibgateway
echo "  Waiting 60s..."
sleep 60

echo ""
echo "=== STATUS ==="
systemctl status ibgateway --no-pager || true
echo ""
echo "=== PORT 4002 ==="
ss -tlnp | grep 4002 && echo "SUCCESS: PORT 4002 OPEN - GATEWAY READY!" || echo "port 4002 not yet open"
echo ""
echo "=== LOG LAST 40 ==="
tail -40 "${BOJKOFX_DIR}/logs/gateway.log" 2>/dev/null

