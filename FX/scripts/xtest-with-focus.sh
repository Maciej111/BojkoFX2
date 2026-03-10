#!/usr/bin/env bash
# xtest-with-focus.sh — ustaw focus na dialog PRZED wysłaniem XTEST clicks
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

python3 - "$WIN" << 'PY'
import sys, time
from Xlib import display, X
from Xlib.ext import xtest

WIN_ID = int(sys.argv[1])
d = display.Display()
win = d.create_resource_object('window', WIN_ID)

# Dialog: pos=(210,279) size=604x210
# Allow button — lewy dolny: ~x=320, y=460

def set_focus_and_click(x, y):
    """Set input focus to dialog, then XTEST click"""
    # Set input focus to dialog window
    win.set_input_focus(X.RevertToParent, X.CurrentTime)
    d.flush()
    time.sleep(0.1)

    # Raise window
    win.raise_window()
    d.flush()
    time.sleep(0.05)

    # Move mouse via XTEST
    xtest.fake_input(d, X.MotionNotify, x=x, y=y)
    d.flush()
    time.sleep(0.1)

    # Click
    xtest.fake_input(d, X.ButtonPress, detail=1)
    d.flush()
    time.sleep(0.05)
    xtest.fake_input(d, X.ButtonRelease, detail=1)
    d.flush()
    time.sleep(0.15)

# First check current focus
focus = d.get_input_focus()
print(f"Current focus: win={hex(focus.focus.id if focus.focus != X.NONE and focus.focus != 1 else 0)}")
print(f"Dialog WID: {hex(WIN_ID)}")

# Set focus to dialog
win.set_input_focus(X.RevertToParent, X.CurrentTime)
d.flush()
time.sleep(0.2)

focus_after = d.get_input_focus()
print(f"Focus after set: {hex(focus_after.focus.id if hasattr(focus_after.focus, 'id') else 0)}")

# Systematically scan all positions in bottom 60px of dialog
# Dialog: y=279 to y=489, bottom 60px: y=429 to y=489
# Allow button typically at about 75% height = y=279+158=437 to 279+185=464
print("\nScanning button area...")
for y in range(437, 480, 4):
    for x in range(270, 460, 15):
        set_focus_and_click(x, y)

d.close()
print("Done all clicks")
PY

echo ""
sleep 1
STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
echo "Dialog: $([ -z "$STILL" ] && echo 'CLOSED - SUCCESS!' || echo "STILL OPEN WID=$STILL")"

kill "$PYTHON_PID" 2>/dev/null
sleep 1

if [ -z "$STILL" ]; then
    echo ""
    echo "=== TEST ZLECENIA ==="
    cd /home/macie/bojkofx/app
    IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
        /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py
fi

