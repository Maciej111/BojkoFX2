#!/usr/bin/env bash
# xlib-click.sh — wysyłamy ButtonPress przez python3-xlib bezpośrednio do okna Java
export DISPLAY=:99
LOG=/tmp/xlib-click.log

sudo apt-get install -y python3-xlib 2>/dev/null | tail -1

pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1

# Trigger
/home/macie/bojkofx/venv/bin/python - << 'PY' > /tmp/trigger.log 2>&1 &
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
    [ -n "$WIN" ] && { echo "Dialog WID=$WIN"; break; }
done

if [ -z "$WIN" ]; then
    echo "No dialog found"
    kill "$PYTHON_PID" 2>/dev/null
    exit 1
fi

# Użyj python3-xlib do wysłania ButtonPress/ButtonRelease bezpośrednio
python3 - "$WIN" << 'PY'
import sys, time
from Xlib import display, X, protocol

WIN_ID = int(sys.argv[1])
d = display.Display()
root = d.screen().root
win = d.create_resource_object('window', WIN_ID)

# Dialog: pos=210,279  size=604x210
# Próbujemy różne pozycje Y dla przycisku (dolna część okna)
# Allow button: szukamy lewy dolny kwadrant
# Okno ma 210px wysokości, przyciski ~30px od dołu = y=175-185 relative
# W absolutnych coords: 279+175=454 do 279+185=464

clicks = [
    # (abs_x, abs_y, label)
    (320, 456, "Allow-left-1"),
    (340, 456, "Allow-left-2"),
    (300, 456, "Allow-left-3"),
    (280, 456, "Allow-left-4"),
    (350, 456, "Allow-left-5"),
    (320, 462, "Allow-y462"),
    (320, 468, "Allow-y468"),
    (320, 472, "Allow-y472"),
    (400, 456, "mid-1"),
    (450, 456, "mid-2"),
]

def send_click(d, win, abs_x, abs_y):
    """Send ButtonPress + ButtonRelease to window at absolute screen coords"""
    # Convert absolute to relative coords
    geom = win.get_geometry()
    # get window absolute position
    coords = win.translate_coords(d.screen().root, 0, 0)
    win_abs_x = -coords.x
    win_abs_y = -coords.y
    rel_x = abs_x - win_abs_x
    rel_y = abs_y - win_abs_y

    print(f"  Window abs pos: ({win_abs_x},{win_abs_y}), rel click: ({rel_x},{rel_y})")

    # Send motion + press + release
    ev_press = protocol.event.ButtonPress(
        time=X.CurrentTime,
        root=d.screen().root,
        window=win,
        same_screen=1,
        child=X.NONE,
        root_x=abs_x,
        root_y=abs_y,
        event_x=rel_x,
        event_y=rel_y,
        state=0,
        detail=1,
    )
    ev_release = protocol.event.ButtonRelease(
        time=X.CurrentTime,
        root=d.screen().root,
        window=win,
        same_screen=1,
        child=X.NONE,
        root_x=abs_x,
        root_y=abs_y,
        event_x=rel_x,
        event_y=rel_y,
        state=256,
        detail=1,
    )
    win.send_event(ev_press, event_mask=X.ButtonPressMask)
    d.flush()
    time.sleep(0.05)
    win.send_event(ev_release, event_mask=X.ButtonReleaseMask)
    d.flush()
    time.sleep(0.1)

# Znajdź Content window (child okna dialogowego)
# Content window WID to WIN_ID + 8 typowo (WID=2097484, content=2097492)
try:
    tree = win.query_tree()
    print(f"Win children: {[hex(c.id) for c in tree.children]}")
except:
    pass

# Kliknij na sam dialog
for abs_x, abs_y, label in clicks:
    print(f"\nClicking at ({abs_x},{abs_y}) [{label}]")
    try:
        send_click(d, win, abs_x, abs_y)
    except Exception as e:
        print(f"  Error: {e}")
    time.sleep(0.2)

d.close()
print("\nDone sending clicks")
PY

kill "$PYTHON_PID" 2>/dev/null
sleep 1

echo ""
echo "=== TEST ZLECENIA ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

