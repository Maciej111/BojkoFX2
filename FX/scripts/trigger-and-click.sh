#!/usr/bin/env bash
# trigger-and-click.sh
# 1. Triggeruje połączenie Python w tle (co wywołuje dialog)
# 2. Jednocześnie szuka okna dialogowego i klika Allow
export DISPLAY=:99

LOG=/tmp/trigger-click.log
echo "[$(date)] START" > "$LOG"

# Uruchom minimalny Python który tylko sie laczy (nie sklada zlecen - ale triggeruje dialog)
cat > /tmp/trigger_conn.py << 'PY'
import time
from ib_insync import IB
ib = IB()
ib.connect("127.0.0.1", 4002, clientId=88, timeout=15)
print(f"connected: {ib.isConnected()}")
time.sleep(25)  # trzymaj polaczenie 25s
ib.disconnect()
PY

echo "[$(date)] Launching trigger connection in background..." >> "$LOG"
IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/trigger_conn.py >> "$LOG" 2>&1 &
PYTHON_PID=$!
echo "[$(date)] Python PID=$PYTHON_PID" >> "$LOG"

# Szukaj okna przez 20 sekund
echo "[$(date)] Searching for write-access dialog..." >> "$LOG"
FOUND=0
for i in $(seq 1 20); do
    sleep 1
    # Lista wszystkich okien
    WINS=$(xdotool search --name "" 2>/dev/null)
    for WID in $WINS; do
        NAME=$(xdotool getwindowname "$WID" 2>/dev/null)
        echo "  i=$i WID=$WID NAME='$NAME'" >> "$LOG"
        if echo "$NAME" | grep -qi "write access\|write.access\|confirmation\|allow"; then
            echo "[$(date)] FOUND DIALOG: WID=$WID NAME='$NAME'" >> "$LOG"
            # Aktywuj okno
            xdotool windowactivate --sync "$WID" 2>/dev/null
            sleep 0.3
            # Pobierz geometrię
            GEOM=$(xdotool getwindowgeometry "$WID" 2>/dev/null)
            echo "  GEOM: $GEOM" >> "$LOG"
            # Kliknij Enter (akceptuje domyślny przycisk)
            xdotool key --window "$WID" Return 2>/dev/null
            echo "[$(date)] Sent Enter" >> "$LOG"
            sleep 0.3
            # Kliknij Tab+Enter (druga opcja)
            xdotool key --window "$WID" Tab Return 2>/dev/null
            echo "[$(date)] Sent Tab+Enter" >> "$LOG"
            FOUND=1
            break 2
        fi
    done
done

if [ "$FOUND" -eq 0 ]; then
    echo "[$(date)] Dialog NOT found in 20s" >> "$LOG"
fi

# Poczekaj na Python
wait "$PYTHON_PID" 2>/dev/null || true
echo "[$(date)] Python finished" >> "$LOG"

echo ""
echo "=== LOG ==="
cat "$LOG"

echo ""
echo "=== Teraz test zlecenia ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

