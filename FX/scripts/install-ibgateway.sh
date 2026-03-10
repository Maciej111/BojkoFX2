#!/usr/bin/env bash
# =============================================================================
#  BojkoFx - IB Gateway Install + systemd Setup
#  Run as: sudo bash /tmp/install-ibgateway.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[OK] $1${NC}"; }
step() { echo -e "\n${CYAN}==> $1${NC}"; }
info() { echo -e "${YELLOW}[INFO] $1${NC}"; }

INSTALL_DIR="/home/macie/ibgateway"
BOJKOFX_DIR="/home/macie/bojkofx"
CONFIG_DIR="${BOJKOFX_DIR}/config"
LOGS_DIR="${BOJKOFX_DIR}/logs"
INSTALLER_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"
INSTALLER_PATH="/tmp/ibgateway-installer.sh"

# ---------------------------------------------------------------------------
# 1. Download installer
# ---------------------------------------------------------------------------
step "Downloading IB Gateway stable installer"
wget -q --show-progress -O "${INSTALLER_PATH}" "${INSTALLER_URL}"
chmod +x "${INSTALLER_PATH}"
ok "Installer saved to ${INSTALLER_PATH} and made executable"

# ---------------------------------------------------------------------------
# 2. Run installer unattended
# ---------------------------------------------------------------------------
step "Running IB Gateway installer (unattended) -> ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

# Create auto-response file for the installer
cat > /tmp/ibgateway-install.varfile << EOF
sys.programGroupDisabled$Boolean=true
sys.languageId=en
sys.installationDir=${INSTALL_DIR}
EOF

bash "${INSTALLER_PATH}" -q -varfile /tmp/ibgateway-install.varfile || {
    info "Varfile install failed, trying direct unattended flags..."
    bash "${INSTALLER_PATH}" -q -dir "${INSTALL_DIR}" -console 2>/dev/null || {
        info "Trying with install4j unattended mode..."
        bash "${INSTALLER_PATH}" -q \
            -Dinstall4j.detached=true \
            -dir "${INSTALL_DIR}" 2>/dev/null || true
    }
}

# Verify installation
if [ -f "${INSTALL_DIR}/ibgateway" ] || [ -f "${INSTALL_DIR}/Jts/ibgateway" ]; then
    ok "IB Gateway installed to ${INSTALL_DIR}"
else
    info "Checking all possible install locations..."
    find /home/macie -name "ibgateway" -type f 2>/dev/null || true
    find /home/macie -name "*.jar" -path "*/ibgateway*" 2>/dev/null | head -5 || true
    ok "Installer completed (verify binary location above)"
fi
ls -la "${INSTALL_DIR}/" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Create startup script
# ---------------------------------------------------------------------------
step "Creating startup script: ${BOJKOFX_DIR}/start-gateway.sh"

cat > "${BOJKOFX_DIR}/start-gateway.sh" << 'STARTSCRIPT'
#!/usr/bin/env bash
# IB Gateway startup script — headless mode

set -euo pipefail

INSTALL_DIR="/home/macie/ibgateway"
BOJKOFX_DIR="/home/macie/bojkofx"
LOG_FILE="${BOJKOFX_DIR}/logs/gateway.log"
PID_FILE="/tmp/ibgateway.pid"
ENV_FILE="${BOJKOFX_DIR}/config/ibkr.env"

# Load credentials
if [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a
fi

# Find gateway binary
if [ -f "${INSTALL_DIR}/ibgateway" ]; then
    GW_BIN="${INSTALL_DIR}/ibgateway"
elif [ -f "${INSTALL_DIR}/Jts/ibgateway" ]; then
    GW_BIN="${INSTALL_DIR}/Jts/ibgateway"
else
    GW_BIN=$(find "${INSTALL_DIR}" -name "ibgateway" -type f 2>/dev/null | head -1)
fi

if [ -z "${GW_BIN:-}" ]; then
    echo "[ERROR] ibgateway binary not found in ${INSTALL_DIR}" >> "${LOG_FILE}"
    exit 1
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting IB Gateway..." >> "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Binary: ${GW_BIN}" >> "${LOG_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Mode: paper, Port: 4002" >> "${LOG_FILE}"

# Start IB Gateway in headless mode (native, no Xvfb)
"${GW_BIN}" \
    --mode=paper \
    --port=4002 \
    -J-Djava.awt.headless=true \
    >> "${LOG_FILE}" 2>&1 &

echo $! > "${PID_FILE}"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gateway PID: $(cat ${PID_FILE})" >> "${LOG_FILE}"
STARTSCRIPT

chmod +x "${BOJKOFX_DIR}/start-gateway.sh"
ok "Startup script created: ${BOJKOFX_DIR}/start-gateway.sh"

# ---------------------------------------------------------------------------
# 4. ibgateway.service
# ---------------------------------------------------------------------------
step "Creating systemd service: /etc/systemd/system/ibgateway.service"

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
ExecStart=/home/macie/bojkofx/start-gateway.sh
PIDFile=/tmp/ibgateway.pid
Restart=on-failure
RestartSec=30s
StandardOutput=append:/home/macie/bojkofx/logs/gateway.log
StandardError=append:/home/macie/bojkofx/logs/gateway.log

[Install]
WantedBy=multi-user.target
EOF

ok "Created /etc/systemd/system/ibgateway.service"

# ---------------------------------------------------------------------------
# 5. bojkofx.service
# ---------------------------------------------------------------------------
step "Creating systemd service: /etc/systemd/system/bojkofx.service"

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

ok "Created /etc/systemd/system/bojkofx.service"

# ---------------------------------------------------------------------------
# 6. ibkr.env template
# ---------------------------------------------------------------------------
step "Creating config template: ${CONFIG_DIR}/ibkr.env"

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

# IB Gateway login (used by gateway auto-login if supported)
IB_USERNAME=
IB_PASSWORD=
EOF
    chmod 600 "${CONFIG_DIR}/ibkr.env"
    ok "Created ${CONFIG_DIR}/ibkr.env (permissions: 600)"
else
    info "${CONFIG_DIR}/ibkr.env already exists — skipping (not overwriting credentials)"
fi

# ---------------------------------------------------------------------------
# 7. Enable services
# ---------------------------------------------------------------------------
step "Reloading systemd and enabling services"

systemctl daemon-reload
ok "systemctl daemon-reload"

systemctl enable ibgateway
ok "systemctl enable ibgateway"

systemctl enable bojkofx
ok "systemctl enable bojkofx"

# ---------------------------------------------------------------------------
# 8. Fix ownership
# ---------------------------------------------------------------------------
step "Setting ownership"
chown -R macie:macie "${BOJKOFX_DIR}"
chown -R macie:macie "${INSTALL_DIR}" 2>/dev/null || true
ok "Ownership set: macie:macie"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  IB Gateway + systemd Setup Complete${NC}"
echo -e "${GREEN}============================================================${NC}"
echo -e "  Install dir  : ${INSTALL_DIR}"
echo -e "  Start script : ${BOJKOFX_DIR}/start-gateway.sh"
echo -e "  Config file  : ${CONFIG_DIR}/ibkr.env  (chmod 600)"
echo -e "  Services     : ibgateway.service  bojkofx.service"
echo ""
echo -e "${YELLOW}  Next steps:${NC}"
echo -e "  1. Edit credentials: nano ${CONFIG_DIR}/ibkr.env"
echo -e "  2. Start gateway:    sudo systemctl start ibgateway"
echo -e "  3. Check status:     sudo systemctl status ibgateway"
echo -e "  4. View logs:        tail -f ${LOGS_DIR}/gateway.log"
echo -e "  5. Start bot:        sudo systemctl start bojkofx"
echo -e "${GREEN}============================================================${NC}"

