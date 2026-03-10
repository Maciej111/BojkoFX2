#!/usr/bin/env bash
# final-ibc-fix.sh — run as: sudo bash /tmp/final-ibc-fix.sh
set -euo pipefail

BOJKOFX_DIR="/home/macie/bojkofx"
IBC_DIR="/opt/ibc"
IBGW_DIR="/home/macie/ibgateway"

echo "[1] Ensure /root/Jts exists and is writable by all"
mkdir -p /root/Jts
chmod 1777 /root/Jts
echo "  OK: $(ls -ld /root/Jts)"

echo "[2] Create /home/macie/Jts (IBC default settings path)"
mkdir -p /home/macie/Jts
chown macie:macie /home/macie/Jts
echo "  OK"

echo "[3] Load credentials from ibkr.env"
source "${BOJKOFX_DIR}/config/ibkr.env"
echo "  IB_USERNAME=${IB_USERNAME}, ACCOUNT=${IBKR_ACCOUNT}"

echo "[4] Write gatewaystart.sh with correct credentials"
cat > "${IBC_DIR}/gatewaystart.sh" << GWSTART
#!/bin/bash
# IBC Gateway start — auto-configured for BojkoFx

TWS_MAJOR_VRSN=1037
IBC_INI=${IBC_DIR}/config.ini
TRADING_MODE=paper
TWOFA_TIMEOUT_ACTION=exit
IBC_PATH=${IBC_DIR}
TWS_PATH=${IBGW_DIR}
TWS_SETTINGS_PATH=/home/macie/Jts
LOG_PATH=${BOJKOFX_DIR}/logs
TWSUSERID=${IB_USERNAME}
TWSPASSWORD=${IB_PASSWORD}
FIXUSERID=
FIXPASSWORD=
JAVA_PATH=

# IBC internal launcher — do not modify below
source "\${IBC_PATH}/scripts/ibcstart.sh" "\${TWS_MAJOR_VRSN}" -g \\
    --tws-path="\${TWS_PATH}" \\
    --tws-settings-path="\${TWS_SETTINGS_PATH}" \\
    --ibc-path="\${IBC_PATH}" \\
    --ibc-ini="\${IBC_INI}" \\
    --user="\${TWSUSERID}" \\
    --pw="\${TWSPASSWORD}" \\
    --mode="\${TRADING_MODE}" \\
    --on2fatimeout="\${TWOFA_TIMEOUT_ACTION}" \\
    \${LOG_PATH:+--log-path="\${LOG_PATH}"}
GWSTART

chmod 700 "${IBC_DIR}/gatewaystart.sh"
chown macie:macie "${IBC_DIR}/gatewaystart.sh"
echo "  OK"

echo "[5] Write new start-gateway-ibc.sh using gatewaystart.sh"
cat > "${BOJKOFX_DIR}/start-gateway-ibc.sh" << 'SCRIPT'
#!/usr/bin/env bash
export HOME=/home/macie
IBC_DIR="/opt/ibc"
BOJKOFX_DIR="/home/macie/bojkofx"
LOG_FILE="${BOJKOFX_DIR}/logs/gateway.log"
XVFB_PID_FILE="/tmp/xvfb.pid"
IBC_PID_FILE="/tmp/ibgateway.pid"
DISPLAY_NUM=99

mkdir -p "${BOJKOFX_DIR}/logs"
mkdir -p /home/macie/Jts

# Kill stale processes
pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

# Start virtual display
Xvfb :${DISPLAY_NUM} -screen 0 1024x768x24 -nolisten tcp &
XVFB_PID=$!
echo ${XVFB_PID} > "${XVFB_PID_FILE}"
export DISPLAY=:${DISPLAY_NUM}
sleep 2

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Xvfb PID=${XVFB_PID} DISPLAY=${DISPLAY}" >> "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting IBC gateway auto-login..." >> "${LOG_FILE}"

# Start IBC via gatewaystart.sh
"${IBC_DIR}/gatewaystart.sh" >> "${LOG_FILE}" 2>&1 &
IBC_PID=$!
echo ${IBC_PID} > "${IBC_PID_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] IBC PID=${IBC_PID}" >> "${LOG_FILE}"
SCRIPT

chmod +x "${BOJKOFX_DIR}/start-gateway-ibc.sh"
chown macie:macie "${BOJKOFX_DIR}/start-gateway-ibc.sh"
echo "  OK"

echo "[6] Update ibgateway.service"
cat > /etc/systemd/system/ibgateway.service << 'SVC'
[Unit]
Description=IB Gateway Paper Trading (IBC auto-login)
After=network.target
Wants=network-online.target

[Service]
Type=forking
User=macie
Group=macie
WorkingDirectory=/home/macie/ibgateway
Environment=HOME=/home/macie
Environment=DISPLAY=:99
ExecStart=/home/macie/bojkofx/start-gateway-ibc.sh
PIDFile=/tmp/ibgateway.pid
TimeoutStartSec=120
Restart=on-failure
RestartSec=60s
StandardOutput=append:/home/macie/bojkofx/logs/gateway.log
StandardError=append:/home/macie/bojkofx/logs/gateway.log

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
echo "  OK"

echo "[7] Restart ibgateway"
systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 3
systemctl start ibgateway
echo "  Waiting 60s for IBC to auto-login..."
sleep 60

echo ""
echo "=== STATUS ==="
systemctl status ibgateway --no-pager || true
echo ""
echo "=== PORT 4002 ==="
ss -tlnp | grep 4002 && echo "SUCCESS: PORT 4002 OPEN" || echo "port 4002 not yet open"
echo ""
echo "=== LOG LAST 30 ==="
tail -30 "${BOJKOFX_DIR}/logs/gateway.log" 2>/dev/null || echo "(no log)"

