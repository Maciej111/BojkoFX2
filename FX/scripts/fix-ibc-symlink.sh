#!/usr/bin/env bash
# fix-ibc-symlink.sh — run as: sudo bash /tmp/fix-ibc-symlink.sh
set -euo pipefail

BOJKOFX_DIR="/home/macie/bojkofx"
IBC_DIR="/opt/ibc"

# IBC builds: gateway_program_path = tws_path + "/ibgateway/" + version
# With tws_path=/home/macie, version=1037:
# gateway_program_path = /home/macie/ibgateway/1037
# We need /home/macie/ibgateway/1037/jars to exist
# Solution: symlink /home/macie/ibgateway/1037 -> /home/macie/ibgateway

echo "[1] Remove old wrong symlink structure"
rm -rf /home/macie/ibgateway/ibgateway 2>/dev/null || true

echo "[2] Create correct symlink: /home/macie/ibgateway/1037 -> /home/macie/ibgateway"
# But /home/macie/ibgateway/1037 pointing to its own parent would create a loop
# Better: make a flat dir /home/macie/ibgateway/1037 with symlinks inside
mkdir -p /home/macie/ibgateway/1037
for item in jars .install4j ibgateway ibgateway.vmoptions data; do
    if [ -e "/home/macie/ibgateway/${item}" ]; then
        ln -sfn "/home/macie/ibgateway/${item}" "/home/macie/ibgateway/1037/${item}"
        echo "  linked: 1037/${item} -> /home/macie/ibgateway/${item}"
    fi
done
chown -R macie:macie /home/macie/ibgateway/1037

echo ""
echo "[3] Verify jars via new path"
ls /home/macie/ibgateway/1037/jars/jts4launch* && echo "  OK: jts4launch found"

echo ""
echo "[4] Update gatewaystart.sh — tws_path=/home/macie"
source "${BOJKOFX_DIR}/config/ibkr.env"
cat > "${IBC_DIR}/gatewaystart.sh" << GWSTART
#!/bin/bash
exec "/opt/ibc/scripts/ibcstart.sh" "1037" -g \
    --tws-path="/home/macie" \
    --tws-settings-path="/home/macie/Jts" \
    --ibc-path="/opt/ibc" \
    --ibc-ini="/opt/ibc/config.ini" \
    --user="${IB_USERNAME}" \
    --pw="${IB_PASSWORD}" \
    --mode="paper" \
    --on2fatimeout="exit"
GWSTART
chmod 700 "${IBC_DIR}/gatewaystart.sh"
chown macie:macie "${IBC_DIR}/gatewaystart.sh"
echo "  Written OK"

echo ""
echo "[5] Restart and wait 90s"
systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 3
systemctl start ibgateway
echo "  Waiting 90s for IBC auto-login..."
sleep 90

echo ""
echo "=== STATUS ==="
systemctl status ibgateway --no-pager || true
echo ""
echo "=== PORT 4002 ==="
ss -tlnp | grep 4002 && echo "SUCCESS: PORT 4002 OPEN!" || echo "port 4002 not open"
echo ""
echo "=== LOG LAST 60 ==="
tail -60 "${BOJKOFX_DIR}/logs/gateway.log" 2>/dev/null

