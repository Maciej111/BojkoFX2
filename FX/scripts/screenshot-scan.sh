#!/usr/bin/env bash
# screenshot-scan.sh — robi screenshot po każdym kliknięciu i szuka zamknięcia dialogu
export DISPLAY=:99

pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1

/home/macie/bojkofx/venv/bin/python - << 'PY' > /tmp/trigger.log 2>&1 &
import time
from ib_insync import IB
ib = IB()
try:
    ib.connect("127.0.0.1", 4002, clientId=88, timeout=15)
    print("connected", flush=True)
except Exception as e:
    print(f"error: {e}", flush=True)
time.sleep(60)
ib.disconnect()
PY
PYTHON_PID=$!

for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && break
done

[ -z "$WIN" ] && { kill "$PYTHON_PID" 2>/dev/null; echo "No dialog"; exit 1; }
echo "Dialog WID=$WIN"

# Zrób screenshot gdy dialog jest widoczny
scrot /tmp/shot_open.png 2>/dev/null
echo "Screenshot of open dialog saved"

# Pełne skanowanie CAŁEGO dolnego paska okna
# Dialog: x=210-814, y=279-489
# Dolne 80px: y=409-489
# Skanuj z krokiem 3px

python3 - "$WIN" << 'PYEOF'
import sys, time
from Xlib import display, X
from Xlib.ext import xtest

WIN_ID = int(sys.argv[1])
d = display.Display()

def click(x, y):
    xtest.fake_input(d, X.MotionNotify, x=x, y=y)
    d.sync()
    time.sleep(0.03)
    xtest.fake_input(d, X.ButtonPress, detail=1)
    d.sync()
    time.sleep(0.03)
    xtest.fake_input(d, X.ButtonRelease, detail=1)
    d.sync()
    time.sleep(0.05)

# Skanuj całe dolne 80px dialogu, krok 5px
print("Scanning entire bottom 80px of dialog...")
for y in range(409, 490, 3):
    for x in range(215, 810, 8):
        click(x, y)

print("Done scanning")
d.close()
PYEOF

sleep 0.5
scrot /tmp/shot_after.png 2>/dev/null

STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
echo "Dialog after full scan: $([ -z "$STILL" ] && echo 'CLOSED!' || echo "STILL OPEN")"

kill "$PYTHON_PID" 2>/dev/null

