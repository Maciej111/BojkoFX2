#!/usr/bin/env bash
# =============================================================================
#  BojkoFx - IB Gateway post-install: systemd services, scripts, config
#  Run as: sudo bash /tmp/setup-ibgateway-post.sh
# =============================================================================
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
ok()   { echo -e "${GREEN}[OK] $1${NC}"; }
step() { echo -e "\n${CYAN}==> $1${NC}"; }

INSTALL_DIR="/home/macie/ibgateway"
BOJKOFX_DIR="/home/macie/bojkofx"
CONFIG_DIR="${BOJKOFX_DIR}/config"
LOGS_DIR="${BOJKOFX_DIR}/logs"
INSTALLER="/tmp/ibgateway-installer.sh"

# ---------------------------------------------------------------------------
# 1. Install IB Gateway (installer already downloaded)
# ---------------------------------------------------------------------------
step "Installing IB Gateway to ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

# install4j unattended — use console mode with auto-accept
echo -e "\n\n\n\n\n" | bash "${INSTALLER}" -q -dir "${INSTALL_DIR}" -console 2>/tmp/ibgw-real-install.log || true

# If binary not found, try extract method
if [ ! -f "${INSTALL_DIR}/ibgateway" ] && [ ! -f "${INSTALL_DIR}/Jts/ibgateway" ]; then
    echo "[INFO] Trying alternative install..."
    INSTALL4J_JAVA_HOME=/usr bash "${INSTALLER}" -q -dir "${INSTALL_DIR}" 2>>/tmp/ibgw-real-install.log || true
fi

echo "--- install log ---"
cat /tmp/ibgw-real-install.log 2>/dev/null || true
echo "--- dir listing ---"
ls -la "${INSTALL_DIR}/" 2>/dev/null || echo "(empty)"
ok "Installation attempted — see above for result"

# ---------------------------------------------------------------------------
# 2. Create startup script
# ---------------------------------------------------------------------------
step "Creating ${BOJKOFX_DIR}/start-gateway.sh"
mkdir -p "${LOGS_DIR}"

cat > "${BOJKOFX_DIR}/start-gateway.sh" << 'STARTSCRIPT'
#!/usr/bin/env bash
# IB Gateway startup script — virtual display (Xvfb)

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

# Start Xvfb virtual display
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting Xvfb on :${DISPLAY_NUM}" >> "${LOG_FILE}"
Xvfb :${DISPLAY_NUM} -screen 0 1024x768x24 -nolisten tcp &
echo $! > "${XVFB_PID_FILE}"
export DISPLAY=:${DISPLAY_NUM}
sleep 2

# Find gateway binary
GW_BIN=""
for candidate in \
    "${INSTALL_DIR}/ibgateway" \
    "${INSTALL_DIR}/Jts/ibgateway" \
    "${INSTALL_DIR}/jts/ibgateway"; do
    [ -f "$candidate" ] && GW_BIN="$candidate" && break
done

if [ -z "${GW_BIN}" ]; then
    GW_BIN=$(find "${INSTALL_DIR}" -name "ibgateway" -type f 2>/dev/null | head -1)
fi

if [ -z "${GW_BIN}" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: ibgateway binary not found in ${INSTALL_DIR}" >> "${LOG_FILE}"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting IB Gateway..." >> "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Binary: ${GW_BIN}" >> "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Mode: paper, Port: 4002, DISPLAY=${DISPLAY}" >> "${LOG_FILE}"

"${GW_BIN}" \
    --mode=paper \
    --port=4002 \
    >> "${LOG_FILE}" 2>&1 &

echo $! > "${PID_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gateway PID: $(cat ${PID_FILE})" >> "${LOG_FILE}"
STARTSCRIPT

chmod +x "${BOJKOFX_DIR}/start-gateway.sh"
ok "Created ${BOJKOFX_DIR}/start-gateway.sh"

# ---------------------------------------------------------------------------
# 3. ibkr.env template
# ---------------------------------------------------------------------------
step "Creating ${CONFIG_DIR}/ibkr.env"
mkdir -p "${CONFIG_DIR}"

if [ ! -f "${CONFIG_DIR}/ibkr.env" ]; then
cat > "${CONFIG_DIR}/ibkr.env" << 'EOF'
# IB Gateway connection
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
IBKR_CLIENT_ID=7
IBKR_ACCOUNT=
IBKR_READONLY=true
ALLOW_LIVE_ORDERS=false
KILL_SWITCH=false

# IB Gateway login
IB_USERNAME=
IB_PASSWORD=
EOF
    chmod 600 "${CONFIG_DIR}/ibkr.env"
    ok "Created ${CONFIG_DIR}/ibkr.env (chmod 600)"
else
    ok "${CONFIG_DIR}/ibkr.env already exists — skipped"
fi

# ---------------------------------------------------------------------------
# 4. ibgateway.service
# ---------------------------------------------------------------------------
step "Creating /etc/systemd/system/ibgateway.service"
cat > /etc/systemd/system/ibgateway.service << EOF
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
EOF
ok "Created ibgateway.service"

# ---------------------------------------------------------------------------
# 5. bojkofx.service
# ---------------------------------------------------------------------------
step "Creating /etc/systemd/system/bojkofx.service"
cat > /etc/systemd/system/bojkofx.service << EOF
[Unit]
Description=BojkoFx Trading Bot
After=ibgateway.service network.target
Requires=ibgateway.service

[Service]
Type=simple
User=macie
Group=macie
WorkingDirectory=/home/macie/bojkofx/app
EnvironmentFile=/home/macie/bojkofx/config/ibkr.env
ExecStartPre=/bin/sleep 30
ExecStart=/home/macie/bojkofx/venv/bin/python -m src.runners.run_paper_ibkr_gateway --symbol EURUSD,GBPUSD,USDJPY
Restart=on-failure
RestartSec=60s
StandardOutput=append:/home/macie/bojkofx/logs/bojkofx.log
StandardError=append:/home/macie/bojkofx/logs/bojkofx.log

[Install]
WantedBy=multi-user.target
EOF
ok "Created bojkofx.service"

# ---------------------------------------------------------------------------
# 6. Enable services
# ---------------------------------------------------------------------------
step "Enabling systemd services"
systemctl daemon-reload
ok "daemon-reload"
systemctl enable ibgateway
ok "ibgateway enabled"
systemctl enable bojkofx
ok "bojkofx enabled"

# ---------------------------------------------------------------------------
# 7. Fix ownership
# ---------------------------------------------------------------------------
step "Setting ownership macie:macie"
chown -R macie:macie "${BOJKOFX_DIR}"
chown -R macie:macie "${INSTALL_DIR}" 2>/dev/null || true
ok "Ownership set"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Setup Complete${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e "  start-gateway.sh : ${BOJKOFX_DIR}/start-gateway.sh"
echo -e "  ibkr.env         : ${CONFIG_DIR}/ibkr.env"
echo -e "  ibgateway.service: $(systemctl is-enabled ibgateway)"
echo -e "  bojkofx.service  : $(systemctl is-enabled bojkofx)"
echo ""
echo -e "${YELLOW}  IB Gateway dir listing:${NC}"
ls -la "${INSTALL_DIR}/" 2>/dev/null || echo "  (empty — installer may have failed, see /tmp/ibgw-real-install.log)"
echo ""
echo -e "${YELLOW}  Next steps:${NC}"
echo -e "  1. Fill credentials: nano ${CONFIG_DIR}/ibkr.env"
echo -e "  2. Start:  sudo systemctl start ibgateway"
echo -e "  3. Status: sudo systemctl status ibgateway"
echo -e "  4. Logs:   tail -f ${LOGS_DIR}/gateway.log"
echo -e "${GREEN}============================================================${NC}"

