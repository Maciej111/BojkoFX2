#!/usr/bin/env bash
# xtest-click.sh — używa XTEST extension (prawdziwe eventy, Java je odbiera)
export DISPLAY=:99

pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1

/home/macie/bojkofx/venv/bin/python - << 'PY' > /tmp/trigger.log 2>&1 &
import time
from ib_insync import IB
ib = IB()
try:
    ib.connect("127.0.0.1", 4002, clientId=88, timeout=15)
    print(f"connected", flush=True)
except Exception as e:
    print(f"error: {e}", flush=True)
time.sleep(50)
ib.disconnect()
PY
PYTHON_PID=$!

for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && { echo "Dialog WID=$WIN"; break; }
done

[ -z "$WIN" ] && { echo "No dialog"; kill "$PYTHON_PID" 2>/dev/null; exit 1; }

# Użyj XTEST przez python3-xlib
python3 << 'PY'
import time
from Xlib import display, ext, X
from Xlib.ext import xtest

d = display.Display()

# Dialog position: x=210, y=279, size=604x210
# Allow button (lewy-dolny): szacujemy x=320, y=460
# Zakres testowania

def xtest_click(x, y):
    """Symuluj kliknięcie przez XTEST — Java to widzi"""
    # Move mouse
    xtest.fake_input(d, X.MotionNotify, x=x, y=y)
    d.flush()
    time.sleep(0.05)
    # Press
    xtest.fake_input(d, X.ButtonPress, detail=1)
    d.flush()
    time.sleep(0.05)
    # Release
    xtest.fake_input(d, X.ButtonRelease, detail=1)
    d.flush()
    time.sleep(0.1)

print("Testing XTEST clicks on dialog buttons...")
print("Dialog: pos=(210,279) size=604x210")
print()

# Allow button coordinates to try
# Bottom of dialog: y = 279+210 = 489
# Buttons typically 30-40px from bottom: y = 450-460
# Allow (left button): x = 210 + 100-200 = 310-410

candidates = []
for y in range(450, 480, 5):
    for x in range(290, 430, 20):
        candidates.append((x, y))

for x, y in candidates:
    print(f"XTEST click at ({x}, {y})")
    xtest_click(x, y)
    time.sleep(0.15)

d.close()
print("Done")
PY

echo ""
sleep 1
STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
echo "Dialog: $([ -z "$STILL" ] && echo 'CLOSED - SUCCESS!' || echo "STILL OPEN WID=$STILL")"

kill "$PYTHON_PID" 2>/dev/null
sleep 1

echo ""
echo "=== TEST ZLECENIA ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

