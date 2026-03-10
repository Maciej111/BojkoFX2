#!/usr/bin/env bash
# install-ibc.sh — instaluje IBC (IB Controller) do auto-logowania IB Gateway
# run as: sudo bash /tmp/install-ibc.sh
set -euo pipefail

IBC_DIR="/opt/ibc"
BOJKOFX_DIR="/home/macie/bojkofx"
CONFIG_DIR="${BOJKOFX_DIR}/config"
LOG_DIR="${BOJKOFX_DIR}/logs"

echo "[1/5] Pobieranie najnowszego IBC (auto-detect version)"
mkdir -p "${IBC_DIR}"

# Pobierz URL do najnowszego IBCLinux zip z GitHub API
IBC_URL=$(curl -s https://api.github.com/repos/IbcAlpha/IBC/releases/latest \
    | grep browser_download_url \
    | grep IBCLinux \
    | cut -d'"' -f4)

if [ -z "${IBC_URL}" ]; then
    echo "  GitHub API failed, trying hardcoded 3.19.0..."
    IBC_URL="https://github.com/IbcAlpha/IBC/releases/download/3.19.0/IBCLinux-3.19.0.zip"
fi

IBC_VERSION=$(echo "${IBC_URL}" | grep -oP '[\d]+\.[\d]+\.[\d]+' | head -1)
echo "  Version: ${IBC_VERSION}"
echo "  URL: ${IBC_URL}"

curl -fsSL "${IBC_URL}" -o /tmp/ibc.zip
echo "  OK"

echo "[2/5] Rozpakowywanie do ${IBC_DIR}"
unzip -o /tmp/ibc.zip -d "${IBC_DIR}"
chmod +x "${IBC_DIR}"/*.sh 2>/dev/null || true
chmod +x "${IBC_DIR}/scripts"/*.sh 2>/dev/null || true
echo "  OK"

echo "[3/5] Tworzenie konfiguracji IBC"
# Pobierz credentials z ibkr.env
source "${CONFIG_DIR}/ibkr.env"

cat > "${IBC_DIR}/config.ini" << EOF
# IBC Configuration
LogToConsole=yes
FIX=no
IbLoginId=${IB_USERNAME}
IbPassword=${IB_PASSWORD}
TradingMode=paper
IbDir=/home/macie/Jts
ReadonlyLogin=no
AcceptEula=yes
AcceptBidAskLastSizeExemption=yes
SaveTwsSettingsAt=
MinimizeMainWindow=yes
MaximizeMainWindow=no
ExistingSessionDetectedAction=primary
AcceptIncomingConnectionAction=accept
ShowAllTrades=no
EOF
chmod 600 "${IBC_DIR}/config.ini"
chown -R macie:macie "${IBC_DIR}"
echo "  OK"

echo "[4/5] Tworzenie start-gateway-ibc.sh"
cat > "${BOJKOFX_DIR}/start-gateway-ibc.sh" << 'SCRIPT'
#!/usr/bin/env bash
export HOME=/home/macie
IBC_DIR="/opt/ibc"
IBGW_DIR="/home/macie/ibgateway"
BOJKOFX_DIR="/home/macie/bojkofx"
LOG_FILE="${BOJKOFX_DIR}/logs/gateway.log"
XVFB_PID_FILE="/tmp/xvfb.pid"
DISPLAY_NUM=99

mkdir -p "${BOJKOFX_DIR}/logs"
mkdir -p /home/macie/Jts

# Load credentials
source "${BOJKOFX_DIR}/config/ibkr.env"

# Kill stale Xvfb
pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
sleep 1

# Start virtual display
Xvfb :${DISPLAY_NUM} -screen 0 1024x768x24 -nolisten tcp &
echo $! > "${XVFB_PID_FILE}"
export DISPLAY=:${DISPLAY_NUM}
sleep 2
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Xvfb started DISPLAY=${DISPLAY}" >> "${LOG_FILE}"

# Start IBC (which starts IB Gateway and auto-logs in)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting IBC auto-login..." >> "${LOG_FILE}"

# IBC ibcstart.sh args: TWS_MAJOR_VNUM IBC_INI TRADING_MODE [TWS_PATH IBC_PATH LOG_PATH]
"${IBC_DIR}/scripts/ibcstart.sh" \
    "1037" \
    "${IBC_DIR}/config.ini" \
    "paper" \
    "${IBGW_DIR}" \
    "${IBC_DIR}" \
    "${BOJKOFX_DIR}/logs" \
    >> "${LOG_FILE}" 2>&1 &

echo $! > /tmp/ibgateway.pid
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] IBC PID: $(cat /tmp/ibgateway.pid)" >> "${LOG_FILE}"
SCRIPT

chmod +x "${BOJKOFX_DIR}/start-gateway-ibc.sh"
chown macie:macie "${BOJKOFX_DIR}/start-gateway-ibc.sh"
echo "  OK"

echo "[5/5] Aktualizacja ibgateway.service"
cat > /etc/systemd/system/ibgateway.service << 'SVC'
[Unit]
Description=IB Gateway Paper Trading (IBC)
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
Restart=on-failure
RestartSec=30s
StandardOutput=append:/home/macie/bojkofx/logs/gateway.log
StandardError=append:/home/macie/bojkofx/logs/gateway.log

[Install]
WantedBy=multi-user.target
SVC

systemctl daemon-reload
systemctl stop ibgateway 2>/dev/null || true
sleep 3
systemctl start ibgateway
echo "  OK — czekam 45s na auto-login..."
sleep 45

echo ""
echo "=== STATUS ==="
systemctl status ibgateway --no-pager || true

echo ""
echo "=== PORT 4002 ==="
ss -tlnp | grep 4002 && echo "✓ PORT 4002 OPEN - GATEWAY READY" || echo "port 4002 nie otwarty (gateway może jeszcze logować)"

echo ""
echo "=== LOG TAIL ==="
tail -20 "${LOG_DIR}/gateway.log" 2>/dev/null || echo "(brak logu)"

echo ""
echo "=== IBC dir ==="
ls -la "${IBC_DIR}/"



