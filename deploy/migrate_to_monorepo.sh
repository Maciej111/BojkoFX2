#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# migrate_to_monorepo.sh — Migracja serwera FX z BojkoFx.git → BojkoFX2 monorepo
#
# Uruchom LOKALNIE:
#   bash deploy/migrate_to_monorepo.sh
#
# Co robi:
#   1. Zatrzymuje usługi bojkofx i bojkofx-dashboard
#   2. Tworzy backup /home/macie/bojkofx/app/ → app_backup_YYYYMMDD/
#   3. Klonuje nowe monorepo BojkoFX2 do /home/macie/bojkofx/app/
#   4. Kopiuje dane runtime (state DB, config) do nowej struktury
#   5. Aktualizuje zależności venv (dodaje flask-cors)
#   6. Instaluje nowe pliki usług systemd
#   7. Uruchamia usługi i weryfikuje
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

VM_HOST="macie@34.31.64.224"
VM_BASE="/home/macie/bojkofx"
REPO_URL="https://github.com/Maciej111/BojkoFX2.git"
VENV="${VM_BASE}/venv"
DATE=$(date +%Y%m%d_%H%M)

echo "═══════════════════════════════════════════════════════════"
echo "  BojkoFX2 Monorepo Migration → ${VM_HOST}"
echo "  $(date)"
echo "═══════════════════════════════════════════════════════════"

# ── Krok 1: Zatrzymaj usługi ──────────────────────────────────────────────────
echo ""
echo "[1/7] Zatrzymuję usługi..."
ssh "${VM_HOST}" "
  sudo systemctl stop bojkofx-dashboard || true
  sudo systemctl stop bojkofx || true
  echo '  bojkofx:           '$(sudo systemctl is-active bojkofx || echo stopped)
  echo '  bojkofx-dashboard: '$(sudo systemctl is-active bojkofx-dashboard || echo stopped)
"

# ── Krok 2: Backup ────────────────────────────────────────────────────────────
echo ""
echo "[2/7] Backup starego app/..."
ssh "${VM_HOST}" "
  cp -a ${VM_BASE}/app ${VM_BASE}/app_backup_${DATE}
  echo '  Backup w: ${VM_BASE}/app_backup_${DATE}'
  du -sh ${VM_BASE}/app_backup_${DATE} | awk '{print \"  Rozmiar: \"\$1}'
"

# ── Krok 3: Klonuj nowe monorepo ──────────────────────────────────────────────
echo ""
echo "[3/7] Klonam nowe monorepo BojkoFX2..."
ssh "${VM_HOST}" "
  # Przesuń stary app/ w bok tymczasowo
  mv ${VM_BASE}/app ${VM_BASE}/app_old_${DATE}

  # Klonuj monorepo
  git clone ${REPO_URL} ${VM_BASE}/app
  echo '  Sklonowano BojkoFX2 → ${VM_BASE}/app'
  ls ${VM_BASE}/app/
"

# ── Krok 4: Przywróć dane runtime ────────────────────────────────────────────
echo ""
echo "[4/7] Kopiuję dane runtime (state DB, config, logi)..."
ssh "${VM_HOST}" "
  OLD=${VM_BASE}/app_old_${DATE}
  NEW=${VM_BASE}/app

  # Skrypt start-bot.sh (poza repo, w katalogu nadrzędnym)
  cp -v \${OLD}/../start-bot.sh ${VM_BASE}/start-bot.sh 2>/dev/null || \\
    echo '  Brak start-bot.sh — sprawdź ręcznie'

  # Dane runtime FX — kopiuj do FX/data/state/
  echo '  Kopiuję state DB...'
  mkdir -p \${NEW}/FX/data/state
  cp -rv \${OLD}/data/state/. \${NEW}/FX/data/state/ 2>/dev/null || echo '  brak data/state (OK przy pierwszym uruchomieniu)'

  # Live bars jeśli istnieją
  if [ -d \"\${OLD}/data/live_bars_local\" ]; then
    mkdir -p \${NEW}/FX/data/live_bars_local
    cp -rv \${OLD}/data/live_bars_local/. \${NEW}/FX/data/live_bars_local/ 2>/dev/null || true
  fi

  # Validated bars
  if [ -d \"\${OLD}/data/bars_validated\" ]; then
    mkdir -p \${NEW}/FX/data/bars_validated
    cp -rv \${OLD}/data/bars_validated/. \${NEW}/FX/data/bars_validated/ 2>/dev/null || true
  fi

  # Credentials
  if [ -d \"\${OLD}/credentials\" ]; then
    mkdir -p \${NEW}/FX/credentials
    cp -v \${OLD}/credentials/ib.cre \${NEW}/FX/credentials/ 2>/dev/null || true
  fi

  # Logs
  mkdir -p ${VM_BASE}/logs
  cp -v \${OLD}/../logs/paper_trading_ibkr.csv ${VM_BASE}/logs/ 2>/dev/null || true
  cp -v \${OLD}/../logs/paper_trading.csv       ${VM_BASE}/logs/ 2>/dev/null || true

  echo '  Dane runtime skopiowane.'
"

# ── Krok 5: Aktualizuj venv ───────────────────────────────────────────────────
echo ""
echo "[5/7] Aktualizuję zależności venv..."
ssh "${VM_HOST}" "
  # Zainstaluj brakujące zależności dashboardu
  ${VENV}/bin/pip install --quiet flask-cors>=4.0.0

  # Zainstaluj zależności FX
  ${VENV}/bin/pip install --quiet -r ${VM_BASE}/app/FX/requirements.txt

  echo '  venv OK'
  ${VENV}/bin/python -c 'import flask_cors; print(\"  flask-cors OK\")'
"

# ── Krok 6: Zainstaluj nowe pliki systemd ────────────────────────────────────
echo ""
echo "[6/7] Instaluję nowe pliki usług systemd..."
ssh "${VM_HOST}" "
  sudo cp ${VM_BASE}/app/deploy/bojkofx.service           /etc/systemd/system/bojkofx.service
  sudo cp ${VM_BASE}/app/deploy/bojkofx-dashboard.service /etc/systemd/system/bojkofx-dashboard.service
  sudo systemctl daemon-reload
  echo '  Pliki usług zainstalowane i przeładowane.'
"

# ── Krok 7: Uruchom i zweryfikuj ─────────────────────────────────────────────
echo ""
echo "[7/7] Uruchamiam usługi i weryfikuję..."
ssh "${VM_HOST}" "
  # Sprawdź import Python przed uruchomieniem bota
  echo '--- Test importów FX ---'
  cd ${VM_BASE}/app/FX
  ${VENV}/bin/python -c '
import sys
sys.path.insert(0, \".\")
from src.core.models import Side
from src.core.state_store import SQLiteStateStore, get_default_db_path
from src.structure.bias import determine_htf_bias
from src.indicators.atr import calculate_atr
from src.reporting.logger import TradingLogger
print(\"  Importy FX: OK\")
'

  # Sprawdź dashboard
  echo '--- Test importów dashboard ---'
  cd ${VM_BASE}/app
  ${VENV}/bin/python -c '
import sys
sys.path.insert(0, \"dashboard\")
from app import app, _PROJECTS
print(\"  Dashboard: OK —\", list(_PROJECTS.keys()))
'

  # Uruchom usługi
  sudo systemctl start bojkofx-dashboard
  sleep 3
  sudo systemctl start bojkofx
  sleep 5

  echo ''
  echo '--- Status usług ---'
  echo -n '  bojkofx:           '; sudo systemctl is-active bojkofx
  echo -n '  bojkofx-dashboard: '; sudo systemctl is-active bojkofx-dashboard

  echo ''
  echo '--- Health check dashboard ---'
  sleep 2
  curl -sf http://localhost:8080/api/health || echo '  dashboard jeszcze nie odpowiada (czekaj ~10s)'
"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Migracja zakończona!"
echo ""
echo "  Monitoring:"
echo "    ssh ${VM_HOST} 'tail -f ${VM_BASE}/logs/bojkofx.log'"
echo "    ssh ${VM_HOST} 'tail -f ${VM_BASE}/logs/dashboard.log'"
echo ""
echo "  W razie problemu — rollback:"
echo "    ssh ${VM_HOST} 'sudo systemctl stop bojkofx bojkofx-dashboard'"
echo "    ssh ${VM_HOST} 'mv ${VM_BASE}/app ${VM_BASE}/app_failed; mv ${VM_BASE}/app_old_${DATE} ${VM_BASE}/app'"
echo "    ssh ${VM_HOST} 'sudo systemctl start bojkofx bojkofx-dashboard'"
echo "═══════════════════════════════════════════════════════════"
