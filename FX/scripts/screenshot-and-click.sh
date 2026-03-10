#!/usr/bin/env bash
# screenshot-and-click.sh
# Triggeruje dialog, robi screenshot i klika przycisk Allow po współrzędnych
export DISPLAY=:99
LOG=/tmp/sc-click.log

echo "[$(date)] START" > "$LOG"

# Install scrot if needed
sudo apt-get install -y scrot 2>/dev/null | tail -1

# Trigger connection
cat > /tmp/trigger2.py << 'PY'
import time, sys
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

IBKR_READONLY=false /home/macie/bojkofx/venv/bin/python /tmp/trigger2.py >> "$LOG" 2>&1 &
PYTHON_PID=$!

# Poczekaj na dialog
for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && break
done

if [ -z "$WIN" ]; then
    echo "[$(date)] Dialog not found" >> "$LOG"
    cat "$LOG"; exit 1
fi

echo "[$(date)] Found dialog WID=$WIN" >> "$LOG"
GEOM=$(xdotool getwindowgeometry "$WIN" 2>/dev/null)
echo "  $GEOM" >> "$LOG"

# Screenshot całego ekranu
scrot /tmp/dialog_screenshot.png -d 0 2>/dev/null && echo "  Screenshot saved" >> "$LOG"

# Aktywuj okno
xdotool windowactivate --sync "$WIN"
sleep 0.5

# Okno ma 604x210 — przyciski są zazwyczaj na dole
# "Allow" zazwyczaj jest po lewej, "Deny" po prawej LUB odwrotnie
# Kliknij w dolną lewą ćwiartkę (ok. 150,175) — typowy "Allow/OK"
xdotool mousemove --window "$WIN" 150 175
sleep 0.2
xdotool click 1
echo "[$(date)] Clicked at 150,175" >> "$LOG"
sleep 0.5

# Zrób screenshot po kliknięciu
scrot /tmp/after_click.png -d 0 2>/dev/null

kill "$PYTHON_PID" 2>/dev/null

cat "$LOG"
echo ""
echo "=== Sprawdzam czy dialog zniknął ==="
sleep 1
xdotool search --name "write access" 2>/dev/null && echo "Dialog still present" || echo "Dialog gone - click worked!"

echo ""
echo "=== TEST ZLECENIA ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

