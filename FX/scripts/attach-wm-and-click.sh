#!/usr/bin/env bash
# attach-wm-and-click.sh
# Dołącza openbox do ISTNIEJĄCEGO Xvfb:99, nie uruchamia nowego
export DISPLAY=:99

pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
pkill -f openbox 2>/dev/null || true
sleep 1

echo "[1] Attach openbox to existing :99"
DISPLAY=:99 openbox &
OPENBOX_PID=$!
sleep 2
echo "  openbox PID=$OPENBOX_PID, running: $(kill -0 $OPENBOX_PID 2>/dev/null && echo YES || echo NO)"

echo "[2] Trigger connection"
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

echo "[3] Wait for dialog and click"
for i in $(seq 1 15); do
    sleep 1
    WIN=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "  Dialog WID=$WIN at i=$i"
        # Z openbox windowactivate powinno teraz działać
        DISPLAY=:99 xdotool windowactivate --sync "$WIN" 2>/dev/null && echo "  Activated OK" || echo "  Activate failed"
        sleep 0.5
        # Kliknij Enter
        DISPLAY=:99 xdotool key --clearmodifiers Return
        sleep 0.3
        STILL=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
        if [ -z "$STILL" ]; then
            echo "  SUCCESS - dialog closed by Return!"
        else
            echo "  Still open — trying mouse click at (320,465)"
            DISPLAY=:99 xdotool mousemove 320 465
            sleep 0.2
            DISPLAY=:99 xdotool click 1
            sleep 0.3
            STILL2=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
            echo "  After click: $([ -z "$STILL2" ] && echo CLOSED || echo STILL OPEN)"
        fi
        break
    fi
done

kill "$PYTHON_PID" 2>/dev/null
sleep 1

echo ""
echo "[4] TEST ZLECENIA"
cd /home/macie/bojkofx/app
DISPLAY=:99 IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

pkill -f openbox 2>/dev/null || true

