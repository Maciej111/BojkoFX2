#!/usr/bin/env bash
# run-test-with-watcher.sh
set -e

export DISPLAY=:99

echo "[1] Start write-access auto-clicker in background"
bash /tmp/auto-allow-writeaccess.sh &
WATCHER_PID=$!
echo "  Watcher PID=$WATCHER_PID"

echo "[2] Wait 2s then run order test"
sleep 2

cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

TEST_EXIT=$?
echo ""
echo "Test exit: $TEST_EXIT"
echo ""
echo "=== Watcher log ==="
cat /tmp/xdotool-watcher.log 2>/dev/null || echo "(no watcher log)"

