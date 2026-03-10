#!/usr/bin/env bash
# click-content-window.sh — klikamy na Content window dialogu, nie na ramkę
export DISPLAY=:99

pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1

# Trigger w tle
/home/macie/bojkofx/venv/bin/python - << 'PY' &
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
PYTHON_PID=$!

# Czekaj na dialog
for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && break
done

if [ -z "$WIN" ]; then
    echo "Dialog not found"
    kill "$PYTHON_PID" 2>/dev/null
    exit 1
fi

echo "Dialog WID=$WIN"

# Content window dla tego dialogu jest na Position: 210,279 Geometry: 604x210
# Przyciski są na dole Content window
# Okno: x=210 do x=814, y=279 do y=489
# Allow (lewy): około x=320, y=465
# Deny (prawy): około x=530, y=465

# Próbuj kliknąć Allow — lewy przycisk, dolna część okna
# Spróbuj kilka pozycji

for try_y in 465 455 445 470; do
    for try_x in 320 300 350 280 360; do
        echo "Clicking at ($try_x, $try_y)..."
        xdotool mousemove "$try_x" "$try_y"
        sleep 0.15
        xdotool click 1
        sleep 0.3
        STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
        if [ -z "$STILL" ]; then
            echo "SUCCESS! Dialog closed after click at ($try_x, $try_y)"
            kill "$PYTHON_PID" 2>/dev/null

            echo ""
            echo "=== TEST ZLECENIA ==="
            cd /home/macie/bojkofx/app
            IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
                /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py
            exit 0
        fi
    done
done

echo "All clicks failed — dialog still open"
kill "$PYTHON_PID" 2>/dev/null

