#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_idx.sh — Deploy BojkoIDX to bojkofx-vm (34.31.64.224)
#
# Run this script LOCALLY from the repo root:
#   bash deploy/deploy_idx.sh
#
# Prerequisites:
#   - SSH key set up for macie@34.31.64.224
#   - Git remote "origin" pointing to the BojkoIDX repo
#   - IBKR Gateway already running (managed by ibgateway.service)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

VM_HOST="macie@34.31.64.224"
VM_APP_DIR="/home/macie/bojkoidx/app"
VM_VENV_DIR="/home/macie/bojkoidx/venv"
VM_CONFIG_DIR="/home/macie/bojkoidx/config"
VM_LOGS_DIR="/home/macie/bojkoidx/logs"
VM_DATA_DIR="/home/macie/bojkoidx/data"
SERVICE_NAME="bojkoidx"

echo "═══════════════════════════════════════════════════════════"
echo "  BojkoIDX Deployment → ${VM_HOST}"
echo "═══════════════════════════════════════════════════════════"

# ── Step 1: Push latest code ───────────────────────────────────────────────
echo ""
echo "[1/7] Pushing local changes to git origin..."
git push origin main

# ── Step 2: Create directory structure on VM ──────────────────────────────
echo ""
echo "[2/7] Creating VM directory structure..."
ssh "${VM_HOST}" "
  mkdir -p ${VM_APP_DIR} ${VM_CONFIG_DIR} ${VM_LOGS_DIR} ${VM_DATA_DIR}/bars_idx
"

# ── Step 3: Clone / update repo on VM ─────────────────────────────────────
echo ""
echo "[3/7] Cloning/updating repo on VM..."
REPO_URL=$(git remote get-url origin)
ssh "${VM_HOST}" "
  if [ -d '${VM_APP_DIR}/.git' ]; then
    echo 'Pulling latest...'
    cd ${VM_APP_DIR} && git pull origin main
  else
    echo 'Cloning fresh...'
    git clone ${REPO_URL} ${VM_APP_DIR}
  fi
"

# ── Step 4: Upload pre-built CSV bars (5m, needed for CSV fallback) ────────
echo ""
echo "[4/7] Uploading 5m bars CSV fallback..."
if [ -f "data/bars_idx/usatechidxusd_5m_bars.csv" ]; then
  rsync -avz --progress \
    data/bars_idx/usatechidxusd_5m_bars.csv \
    "${VM_HOST}:${VM_DATA_DIR}/bars_idx/"
  echo "  Uploaded usatechidxusd_5m_bars.csv"
else
  echo "  WARNING: data/bars_idx/usatechidxusd_5m_bars.csv not found locally."
  echo "  The bot will use IBKR historical data at startup (no CSV fallback)."
fi

# ── Step 5: Create Python venv + install dependencies ─────────────────────
echo ""
echo "[5/7] Setting up Python venv on VM..."
ssh "${VM_HOST}" "
  if [ ! -d '${VM_VENV_DIR}' ]; then
    echo 'Creating venv...'
    python3 -m venv ${VM_VENV_DIR}
  fi
  echo 'Installing/upgrading dependencies...'
  ${VM_VENV_DIR}/bin/pip install --upgrade pip
  ${VM_VENV_DIR}/bin/pip install -r ${VM_APP_DIR}/requirements.txt
"

# ── Step 6: Deploy config file (only if not already present) ──────────────
echo ""
echo "[6/7] Deploying config (will NOT overwrite existing ibkr.env)..."
ssh "${VM_HOST}" "
  if [ ! -f '${VM_CONFIG_DIR}/ibkr.env' ]; then
    cp ${VM_APP_DIR}/deploy/bojkoidx.env ${VM_CONFIG_DIR}/ibkr.env
    chmod 600 ${VM_CONFIG_DIR}/ibkr.env
    echo 'Created ${VM_CONFIG_DIR}/ibkr.env'
  else
    echo 'Existing ${VM_CONFIG_DIR}/ibkr.env unchanged.'
  fi
"

# ── Step 7: Install / update systemd service ──────────────────────────────
echo ""
echo "[7/7] Installing systemd service..."
ssh "${VM_HOST}" "
  sudo cp ${VM_APP_DIR}/deploy/bojkoidx.service /etc/systemd/system/bojkoidx.service
  sudo systemctl daemon-reload
  sudo systemctl enable ${SERVICE_NAME}
  echo 'Service installed and enabled. To start:'
  echo '  ssh ${VM_HOST} sudo systemctl start ${SERVICE_NAME}'
"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Deployment complete!"
echo ""
echo "  Next steps on VM (ssh ${VM_HOST}):"
echo ""
echo "  # Review config before first start:"
echo "  nano ${VM_CONFIG_DIR}/ibkr.env"
echo ""
echo "  # Start bot:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo ""
echo "  # Watch logs:"
echo "  tail -f ${VM_LOGS_DIR}/bojkoidx.log"
echo ""
echo "  # First run dry-test (no orders, 5 min):"
echo "  cd ${VM_APP_DIR}"
echo "  ${VM_VENV_DIR}/bin/python -m src.runners.run_live_idx --minutes 5"
echo "═══════════════════════════════════════════════════════════"
