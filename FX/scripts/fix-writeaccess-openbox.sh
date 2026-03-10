#!/usr/bin/env bash
# fix-writeaccess-openbox.sh
# Instaluje openbox jako WM na Xvfb, restartuje gateway i uruchamia test

export DISPLAY=:99

echo "[1] Instalacja openbox"
sudo apt-get install -y openbox 2>&1 | tail -3

echo "[2] Stop gateway"
sudo systemctl stop ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 2

echo "[3] Start Xvfb z openbox"
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp &
sleep 2
DISPLAY=:99 openbox --replace &
sleep 2
echo "  WM running: $(pgrep openbox && echo YES || echo NO)"

echo "[4] Start IBC gateway"
sudo systemctl start ibgateway
echo "  Waiting 80s for auto-login..."
sleep 80

echo "[5] Port check"
ss -tlnp | grep 4002 && echo "PORT 4002 OPEN" || echo "PORT 4002 NOT OPEN"

echo "[6] Run trigger + click test"
# Trigger connection (wywołuje dialog)
cat > /tmp/trigger_final.py << 'PY'
import time
from ib_insync import IB
ib = IB()
try:
    ib.connect("127.0.0.1", 4002, clientId=88, timeout=15)
    print(f"connected: {ib.isConnected()}", flush=True)
except Exception as e:
    print(f"error: {e}", flush=True)
time.sleep(40)
ib.disconnect()
PY

DISPLAY=:99 IBKR_READONLY=false /home/macie/bojkofx/venv/bin/python /tmp/trigger_final.py &
PYTHON_PID=$!

# Czekaj na dialog i kliknij
for i in $(seq 1 20); do
    sleep 1
    WIN=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "  Found dialog WID=$WIN at iteration $i"
        # Z openbox windowactivate powinno działać
        DISPLAY=:99 xdotool windowactivate --sync "$WIN" 2>/dev/null || true
        sleep 0.5
        # Kliknij Enter (domyślny przycisk = Allow)
        DISPLAY=:99 xdotool key --clearmodifiers --window "$WIN" Return
        sleep 0.3
        # Sprawdź
        STILL=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
        echo "  After Return: dialog=$([ -z "$STILL" ] && echo CLOSED || echo OPEN)"
        break
    fi
done

kill "$PYTHON_PID" 2>/dev/null
sleep 1

echo ""
echo "[7] TEST ZLECENIA"
cd /home/macie/bojkofx/app
DISPLAY=:99 IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

