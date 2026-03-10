#!/usr/bin/env bash
# click-allow-absolute.sh — klikanie absolutnymi współrzędnymi ekranu
export DISPLAY=:99
LOG=/tmp/click-abs.log
echo "[$(date)] START" > "$LOG"

# Trigger connection
cat > /tmp/trigger3.py << 'PY'
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

IBKR_READONLY=false /home/macie/bojkofx/venv/bin/python /tmp/trigger3.py >> "$LOG" 2>&1 &
PYTHON_PID=$!

# Czekaj na dialog
for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && break
done

if [ -z "$WIN" ]; then
    echo "[$(date)] Dialog NOT found" >> "$LOG"
    kill "$PYTHON_PID" 2>/dev/null; exit 1
fi

GEOM=$(xdotool getwindowgeometry "$WIN" 2>/dev/null)
echo "[$(date)] Dialog: $GEOM" >> "$LOG"

# Parsuj pozycję
POS_X=$(echo "$GEOM" | grep Position | sed 's/.*Position: \([0-9]*\),.*/\1/')
POS_Y=$(echo "$GEOM" | grep Position | sed 's/.*Position: [0-9]*,\([0-9]*\).*/\1/')
W=$(echo "$GEOM" | grep Geometry | sed 's/.*Geometry: \([0-9]*\)x.*/\1/')
H=$(echo "$GEOM" | grep Geometry | sed 's/.*Geometry: [0-9]*x\([0-9]*\).*/\1/')
echo "[$(date)] pos=($POS_X,$POS_Y) size=${W}x${H}" >> "$LOG"

# Przyciski na dole okna (~30px od dołu = y + H - 30)
BTN_Y=$((POS_Y + H - 30))
# Lewy przycisk (Allow) ~25% od lewej
BTN_ALLOW_X=$((POS_X + W * 25 / 100))
# Prawy przycisk (Deny) ~75% od lewej
BTN_DENY_X=$((POS_X + W * 75 / 100))

echo "[$(date)] Allow button estimated at: ($BTN_ALLOW_X, $BTN_Y)" >> "$LOG"
echo "[$(date)] Deny button estimated at:  ($BTN_DENY_X, $BTN_Y)" >> "$LOG"

# Screenshot przed kliknięciem
scrot /tmp/before_click.png 2>/dev/null

# Kliknij Allow (lewy przycisk)
xdotool mousemove "$BTN_ALLOW_X" "$BTN_Y"
sleep 0.3
xdotool click 1
echo "[$(date)] Clicked Allow at ($BTN_ALLOW_X, $BTN_Y)" >> "$LOG"
sleep 0.5

# Screenshot po kliknięciu
scrot /tmp/after_click2.png 2>/dev/null

# Sprawdź czy dialog zniknął
sleep 1
STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
if [ -z "$STILL" ]; then
    echo "[$(date)] SUCCESS: Dialog closed after click!" >> "$LOG"
else
    echo "[$(date)] Dialog still present WID=$STILL — trying middle button" >> "$LOG"
    # Środek okna
    MID_X=$((POS_X + W / 2))
    MID_Y=$((POS_Y + H - 30))
    xdotool mousemove "$MID_X" "$MID_Y"
    sleep 0.2
    xdotool click 1
    echo "[$(date)] Clicked middle at ($MID_X, $MID_Y)" >> "$LOG"
fi

kill "$PYTHON_PID" 2>/dev/null

cat "$LOG"
echo ""
echo "=== TEST ZLECENIA ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

