#!/usr/bin/env bash
# full-test.sh - ENABLEAPI + dialog watcher + order test
export DISPLAY=:99
set -euo pipefail

echo "[1] Kill stale Python processes"
pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 2

echo "[2] Send ENABLEAPI to IBC Command Server"
/opt/ibc/enableapi.sh && echo "  ENABLEAPI sent OK" || echo "  ENABLEAPI failed (continuing anyway)"
sleep 2

echo "[3] Check jts.ini ReadOnlyApi"
grep -E "ReadOnly|AllowApi" /home/macie/Jts/jts.ini || echo "  (not found)"

echo ""
echo "[4] Start dialog watcher in background"
(
  for i in $(seq 1 30); do
    sleep 1
    WIN=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
      echo "[WATCHER] Found dialog WID=$WIN at i=$i"
      # Klikaj absolutną pozycją — dialog jest zawsze na 210,279, rozmiar 604x210
      # Allow button typowo w lewym-dolnym rogu: x=210+150=360, y=279+180=459
      DISPLAY=:99 xdotool mousemove 360 459
      sleep 0.2
      DISPLAY=:99 xdotool click 1
      echo "[WATCHER] Clicked at 360,459"
      sleep 0.3
      # Sprawdź czy zamknięte
      STILL=$(DISPLAY=:99 xdotool search --name "write access" 2>/dev/null | head -1)
      if [ -z "$STILL" ]; then
        echo "[WATCHER] SUCCESS - dialog closed"
        exit 0
      fi
      # Drugi przycisk (trochę wyżej)
      DISPLAY=:99 xdotool mousemove 360 445
      sleep 0.1
      DISPLAY=:99 xdotool click 1
      echo "[WATCHER] Clicked at 360,445"
      sleep 0.3
      # Trzecia próba — środek dolnej połowy
      DISPLAY=:99 xdotool mousemove 512 459
      sleep 0.1
      DISPLAY=:99 xdotool click 1
      echo "[WATCHER] Clicked at 512,459"
      exit 0
    fi
  done
  echo "[WATCHER] No dialog found in 30s"
) &
WATCHER_PID=$!
echo "  Watcher PID=$WATCHER_PID"

echo ""
echo "[5] Run order round-trip test"
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

wait "$WATCHER_PID" 2>/dev/null || true

