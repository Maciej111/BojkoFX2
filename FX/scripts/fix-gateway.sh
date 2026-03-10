#!/usr/bin/env bash
# fix-gateway.sh — run as: sudo bash /tmp/fix-gateway.sh
set -euo pipefail

echo "[1/6] Stop ibgateway service"
systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 2
echo "  OK"

echo "[2/6] Create /root/Jts (gateway hardcodes this path)"
mkdir -p /root/Jts
chmod 777 /root/Jts
echo "  OK"

echo "[3/6] Write new start-gateway.sh with Xvfb"
cat > /home/macie/bojkofx/start-gateway.sh << 'SCRIPT'
#!/usr/bin/env bash
# IB Gateway startup — Xvfb virtual display

export HOME=/home/macie
INSTALL_DIR="/home/macie/ibgateway"
BOJKOFX_DIR="/home/macie/bojkofx"
LOG_FILE="${BOJKOFX_DIR}/logs/gateway.log"
PID_FILE="/tmp/ibgateway.pid"
XVFB_PID_FILE="/tmp/xvfb.pid"
ENV_FILE="${BOJKOFX_DIR}/config/ibkr.env"
DISPLAY_NUM=99

# Load credentials
if [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a
fi

mkdir -p "${BOJKOFX_DIR}/logs"
mkdir -p /root/Jts

# Kill stale Xvfb
pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

# Start virtual display
Xvfb :${DISPLAY_NUM} -screen 0 1024x768x24 -nolisten tcp &
XVFB_PID=$!
echo ${XVFB_PID} > "${XVFB_PID_FILE}"
export DISPLAY=:${DISPLAY_NUM}
sleep 3

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Xvfb PID: ${XVFB_PID}, DISPLAY=${DISPLAY}" >> "${LOG_FILE}"

# Find gateway binary
GW_BIN=$(find "${INSTALL_DIR}" -name "ibgateway" -type f 2>/dev/null | head -1)
if [ -z "${GW_BIN}" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: ibgateway binary not found in ${INSTALL_DIR}" >> "${LOG_FILE}"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting: ${GW_BIN} --mode=paper --port=4002" >> "${LOG_FILE}"

"${GW_BIN}" --mode=paper --port=4002 >> "${LOG_FILE}" 2>&1 &
GW_PID=$!
echo ${GW_PID} > "${PID_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gateway PID: ${GW_PID}" >> "${LOG_FILE}"
SCRIPT

chmod +x /home/macie/bojkofx/start-gateway.sh
chown macie:macie /home/macie/bojkofx/start-gateway.sh
echo "  OK"

echo "[4/6] Write new ibgateway.service"
cat > /etc/systemd/system/ibgateway.service << 'SVC'
[Unit]
Description=IB Gateway Paper Trading
After=network.target
Wants=network-online.target

[Service]
Type=forking
User=macie
Group=macie
WorkingDirectory=/home/macie/ibgateway
Environment=HOME=/home/macie
Environment=DISPLAY=:99
ExecStart=/home/macie/bojkofx/start-gateway.sh
PIDFile=/tmp/ibgateway.pid
Restart=on-failure
RestartSec=30s
StandardOutput=append:/home/macie/bojkofx/logs/gateway.log
StandardError=append:/home/macie/bojkofx/logs/gateway.log

[Install]
WantedBy=multi-user.target
SVC
echo "  OK"

echo "[5/6] daemon-reload + start"
systemctl daemon-reload
systemctl start ibgateway
echo "  OK — waiting 15s for gateway to initialize..."
sleep 15

echo "[6/6] Status + log"
systemctl status ibgateway --no-pager || true
echo ""
echo "=== /home/macie/bojkofx/logs/gateway.log (last 40 lines) ==="
tail -40 /home/macie/bojkofx/logs/gateway.log 2>/dev/null || echo "(log empty)"
echo ""
echo "=== Active processes ==="
ps aux | grep -E "(ibgateway|Xvfb)" | grep -v grep || echo "(none)"

