#!/usr/bin/env bash
# fix-ibc-path.sh — run as: sudo bash /tmp/fix-ibc-path.sh
# IBC buduje program_path jako: tws_path/ibgateway/VERSION
# Gateway zainstalowany jest w /home/macie/ibgateway (flat, bez wersji)
# Rozwiązanie: symlink /home/macie/ibgateway/ibgateway/1037 -> /home/macie/ibgateway
set -euo pipefail

BOJKOFX_DIR="/home/macie/bojkofx"
IBC_DIR="/opt/ibc"

echo "[1] Tworzenie symlinku dla IBC path resolution"
# IBC szuka: tws_path/ibgateway/VERSION/jars
# tws_path = /home/macie  (nadrzędny)
# Potrzebujemy: /home/macie/ibgateway/1037/jars -> wskazuje na /home/macie/ibgateway
rm -rf /home/macie/ibgateway/ibgateway 2>/dev/null || true
mkdir -p /home/macie/ibgateway/ibgateway
ln -sfn /home/macie/ibgateway /home/macie/ibgateway/ibgateway/1037
chown -h macie:macie /home/macie/ibgateway/ibgateway/1037
echo "  Symlink: $(ls -la /home/macie/ibgateway/ibgateway/1037)"

echo ""
echo "[2] Weryfikacja: czy IBC znajdzie jars?"
ls /home/macie/ibgateway/ibgateway/1037/jars/jts4launch* && echo "  OK: jts4launch*.jar found via symlink"

echo ""
echo "[3] Aktualizacja gatewaystart.sh — tws-path=/home/macie"
source "${BOJKOFX_DIR}/config/ibkr.env"

cat > "${IBC_DIR}/gatewaystart.sh" << GWSTART
#!/bin/bash
# IBC Gateway start — tws-path=/home/macie so IBC resolves ibgateway/1037
exec "/opt/ibc/scripts/ibcstart.sh" "1037" -g \\
    --tws-path="/home/macie" \\
    --tws-settings-path="/home/macie/Jts" \\
    --ibc-path="/opt/ibc" \\
    --ibc-ini="/opt/ibc/config.ini" \\
    --user="${IB_USERNAME}" \\
    --pw="${IB_PASSWORD}" \\
    --mode="paper" \\
    --on2fatimeout="exit"
GWSTART

chmod 700 "${IBC_DIR}/gatewaystart.sh"
chown macie:macie "${IBC_DIR}/gatewaystart.sh"
echo "  Written OK"

echo ""
echo "[4] Restart ibgateway service"
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
ss -tlnp | grep 4002 && echo "SUCCESS: PORT 4002 OPEN - GATEWAY READY!" || echo "port 4002 not yet open"

echo ""
echo "=== LOG LAST 50 ==="
tail -50 "${BOJKOFX_DIR}/logs/gateway.log" 2>/dev/null


