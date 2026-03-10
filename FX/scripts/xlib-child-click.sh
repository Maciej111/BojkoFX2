#!/usr/bin/env bash
# xlib-child-click.sh — klikamy child windows dialogu
export DISPLAY=:99

pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1

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

for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && { echo "Dialog WID=$WIN"; break; }
done

[ -z "$WIN" ] && { echo "No dialog"; kill "$PYTHON_PID" 2>/dev/null; exit 1; }

python3 - "$WIN" << 'PY'
import sys, time
from Xlib import display, X, protocol

WIN_ID = int(sys.argv[1])
d = display.Display()
win = d.create_resource_object('window', WIN_ID)

# Get children
tree = win.query_tree()
children = tree.children
print(f"Children ({len(children)}): {[hex(c.id) for c in children]}")

def get_abs_pos(w):
    coords = w.translate_coords(d.screen().root, 0, 0)
    return -coords.x, -coords.y

def get_size(w):
    g = w.get_geometry()
    return g.width, g.height

def send_click(target_win, abs_x, abs_y):
    tx, ty = get_abs_pos(target_win)
    rel_x = abs_x - tx
    rel_y = abs_y - ty
    w, h = get_size(target_win)
    print(f"  Target: abs=({tx},{ty}) size={w}x{h} rel_click=({rel_x},{rel_y})")
    if rel_x < 0 or rel_y < 0 or rel_x > w or rel_y > h:
        print(f"  WARNING: click outside window bounds!")

    for ev_class, mask in [
        (protocol.event.ButtonPress, X.ButtonPressMask),
        (protocol.event.ButtonRelease, X.ButtonReleaseMask),
    ]:
        ev = ev_class(
            time=X.CurrentTime,
            root=d.screen().root,
            window=target_win,
            same_screen=1,
            child=X.NONE,
            root_x=abs_x,
            root_y=abs_y,
            event_x=rel_x,
            event_y=rel_y,
            state=0 if ev_class == protocol.event.ButtonPress else 256,
            detail=1,
        )
        target_win.send_event(ev, event_mask=mask)
        d.flush()
        time.sleep(0.05)

# Describe all children
print("\n=== Children details ===")
for child in children:
    try:
        ax, ay = get_abs_pos(child)
        w, h = get_size(child)
        print(f"  WID={hex(child.id)} abs=({ax},{ay}) size={w}x{h}")
    except Exception as e:
        print(f"  WID={hex(child.id)} error: {e}")

# Dialog abs pos: 210,279  size: 604x210
# Przyciski w dolnej cześci — y absolute: 279+170=449 do 279+195=474
# Allow button: lewy ~ x=320-360, y=460
# Spróbuj na każdym child window

print("\n=== Clicking on parent and children ===")
targets = [win] + list(children)
for target in targets:
    try:
        ax, ay = get_abs_pos(target)
        w, h = get_size(target)
        print(f"\n--- Target WID={hex(target.id)} abs=({ax},{ay}) size={w}x{h} ---")
        # Kliknij w kilka miejsc w dolnej cześci
        for click_abs_y in [ay+h-35, ay+h-40, ay+h-30, ay+h-25]:
            for click_abs_x in [ax+int(w*0.25), ax+int(w*0.3), ax+int(w*0.2)]:
                print(f"  Click abs=({click_abs_x},{click_abs_y})")
                send_click(target, click_abs_x, click_abs_y)
    except Exception as e:
        print(f"  Error: {e}")
    time.sleep(0.2)

d.close()
print("\nAll clicks sent")
PY

echo ""
echo "=== Check if dialog closed ==="
sleep 1
STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
echo "Dialog: $([ -z "$STILL" ] && echo 'CLOSED - SUCCESS' || echo "STILL OPEN WID=$STILL")"

kill "$PYTHON_PID" 2>/dev/null
sleep 1

echo ""
echo "=== TEST ZLECENIA ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

