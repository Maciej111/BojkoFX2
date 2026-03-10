#!/usr/bin/env bash
# capture-dialog.sh — triggeruj dialog i zrób screenshot natychmiast
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
time.sleep(30)
ib.disconnect()
PY
PYTHON_PID=$!

# Czekaj na dialog
for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "Dialog found: WID=$WIN at i=$i"
        # Screenshot natychmiast gdy dialog jest otwarty
        sleep 0.2
        scrot -u /tmp/dialog_open.png 2>/dev/null || scrot /tmp/dialog_open.png 2>/dev/null
        echo "Screenshot saved: /tmp/dialog_open.png"

        # Dump wszystkich child windows
        echo "=== Child windows ==="
        xdotool search --name "" 2>/dev/null | while read wid; do
            n=$(xdotool getwindowname "$wid" 2>/dev/null)
            g=$(xdotool getwindowgeometry "$wid" 2>/dev/null | grep -E "Position|Geometry" | tr '\n' ' ')
            echo "  WID=$wid NAME='$n' $g"
        done
        break
    fi
done

kill "$PYTHON_PID" 2>/dev/null
echo "Done"

