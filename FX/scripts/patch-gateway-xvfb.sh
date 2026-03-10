#!/usr/bin/env bash
# Patch: update start-gateway.sh with Xvfb and fix service HOME
set -e

cat > /home/macie/bojkofx/start-gateway.sh << 'SCRIPT'
#!/usr/bin/env bash
export HOME=/home/macie
INSTALL_DIR="/home/macie/ibgateway"
BOJKOFX_DIR="/home/macie/bojkofx"
LOG_FILE="${BOJKOFX_DIR}/logs/gateway.log"
PID_FILE="/tmp/ibgateway.pid"
XVFB_PID_FILE="/tmp/xvfb.pid"
ENV_FILE="${BOJKOFX_DIR}/config/ibkr.env"
DISPLAY_NUM=99

if [ -f "${ENV_FILE}" ]; then
    set -a; source "${ENV_FILE}"; set +a
fi

mkdir -p "${BOJKOFX_DIR}/logs"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting Xvfb on :${DISPLAY_NUM}" >> "${LOG_FILE}"
pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
Xvfb :${DISPLAY_NUM} -screen 0 1024x768x24 -nolisten tcp &
echo $! > "${XVFB_PID_FILE}"
export DISPLAY=:${DISPLAY_NUM}
sleep 2

GW_BIN=$(find "${INSTALL_DIR}" -name "ibgateway" -type f 2>/dev/null | head -1)
if [ -z "${GW_BIN}" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: ibgateway binary not found" >> "${LOG_FILE}"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting IB Gateway: ${GW_BIN}" >> "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DISPLAY=${DISPLAY}, HOME=${HOME}" >> "${LOG_FILE}"

"${GW_BIN}" --mode=paper --port=4002 >> "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gateway PID: $(cat ${PID_FILE})" >> "${LOG_FILE}"
SCRIPT

chmod +x /home/macie/bojkofx/start-gateway.sh
chown macie:macie /home/macie/bojkofx/start-gateway.sh
echo "[OK] start-gateway.sh updated"

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

echo "[OK] ibgateway.service updated"

systemctl daemon-reload
echo "[OK] daemon-reload"

systemctl stop ibgateway 2>/dev/null || true
sleep 2
systemctl start ibgateway
echo "[OK] ibgateway started"
sleep 10
systemctl status ibgateway --no-pager
echo "=== GATEWAY LOG ==="
tail -30 /home/macie/bojkofx/logs/gateway.log

