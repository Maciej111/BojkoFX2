#!/usr/bin/env bash
# precise-click.sh — klikamy precyzyjnie przez AT-SPI / xdotool type
export DISPLAY=:99
LOG=/tmp/precise.log
echo "[$(date)] START" > "$LOG"

# Trigger
IBKR_READONLY=false /home/macie/bojkofx/venv/bin/python - << 'PY' >> "$LOG" 2>&1 &
import time
from ib_insync import IB
ib = IB()
try:
    ib.connect("127.0.0.1", 4002, clientId=88, timeout=15)
    print(f"connected: {ib.isConnected()}", flush=True)
except Exception as e:
    print(f"error: {e}", flush=True)
time.sleep(50)
ib.disconnect()
PY
PYTHON_PID=$!

# Czekaj na dialog
for i in $(seq 1 15); do
    sleep 1
    WIN=$(xdotool search --name "write access" 2>/dev/null | head -1)
    [ -n "$WIN" ] && break
done

[ -z "$WIN" ] && { echo "Dialog not found" >> "$LOG"; kill $PYTHON_PID 2>/dev/null; cat "$LOG"; exit 1; }

echo "[$(date)] Dialog WID=$WIN" >> "$LOG"

# Pobierz listę przycisków przez xprop
echo "=== xprop ===" >> "$LOG"
xprop -id "$WIN" 2>/dev/null >> "$LOG" || echo "xprop failed" >> "$LOG"

# Użyj xdotool key space (aktywuje fokusowany przycisk)
xdotool windowfocus "$WIN" 2>/dev/null || true
sleep 0.3
xdotool key space
echo "[$(date)] Sent space" >> "$LOG"
sleep 0.3

# Sprawdź
STILL=$(xdotool search --name "write access" 2>/dev/null | head -1)
echo "[$(date)] Dialog present: $([ -n "$STILL" ] && echo YES || echo NO)" >> "$LOG"

# Jeśli nadal jest — spróbuj Tab żeby zmienić fokus na Allow i space
if [ -n "$STILL" ]; then
    xdotool key Tab
    sleep 0.2
    xdotool key space
    echo "[$(date)] Sent Tab+Space" >> "$LOG"
    sleep 0.3
fi

# Spróbuj też alt+a (typowy skrót "Allow")
WIN2=$(xdotool search --name "write access" 2>/dev/null | head -1)
if [ -n "$WIN2" ]; then
    xdotool windowfocus "$WIN2" 2>/dev/null || true
    sleep 0.2
    xdotool key alt+a
    echo "[$(date)] Sent alt+a" >> "$LOG"
fi

kill "$PYTHON_PID" 2>/dev/null
sleep 1

cat "$LOG"
echo ""
FINAL=$(xdotool search --name "write access" 2>/dev/null | head -1)
echo "Dialog final state: $([ -z "$FINAL" ] && echo 'CLOSED - SUCCESS' || echo 'STILL OPEN')"

echo ""
echo "=== TEST ZLECENIA ==="
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

