#!/usr/bin/env bash
echo "=== STEP 1: STATUS ==="
GW_ACTIVE=$(systemctl is-active ibgateway)
echo "ibgateway: $GW_ACTIVE"

PORT=$(ss -tlnp | grep 4002)
echo "port 4002: ${PORT:-NOT LISTENING}"

echo ""
echo "=== GATEWAY LOG (last 20) ==="
tail -20 /home/macie/bojkofx/logs/gateway.log

echo ""
echo "=== STEP 2/3: START IF NEEDED ==="
if [ "$GW_ACTIVE" != "active" ]; then
    echo "ibgateway not active — starting..."
    sudo systemctl start ibgateway
    echo "Waiting 90s for IBC login..."
    sleep 90
fi

echo ""
echo "=== PORT 4002 CHECK ==="
ss -tlnp | grep 4002 && echo "PORT 4002: LISTENING" || echo "PORT 4002: NOT LISTENING"

echo ""
echo "=== IBC LOGIN CHECK ==="
grep -i "Login has completed\|Login completed\|Configuration tasks completed" \
    /home/macie/bojkofx/logs/gateway.log | tail -3

echo ""
echo "=== STEP 4: START BOT ==="
BOT_ACTIVE=$(systemctl is-active bojkofx)
echo "bojkofx current: $BOT_ACTIVE"
sudo systemctl start bojkofx
sleep 10
BOT_AFTER=$(systemctl is-active bojkofx)
echo "bojkofx after start: $BOT_AFTER"

echo ""
echo "=== STEP 5: BOT LOG (60s tail) ==="
timeout 65 tail -f /home/macie/bojkofx/logs/bojkofx.log &
TAIL_PID=$!
sleep 65
kill $TAIL_PID 2>/dev/null
wait $TAIL_PID 2>/dev/null

echo ""
echo "=== STEP 6: FINAL SUMMARY ==="
echo "ibgateway service : $(systemctl is-active ibgateway)"
echo "port 4002         : $(ss -tlnp | grep -c 4002 && echo LISTENING || echo NOT LISTENING)"
echo "bojkofx service   : $(systemctl is-active bojkofx)"
echo ""
echo "--- Last 5 lines bojkofx.log ---"
tail -5 /home/macie/bojkofx/logs/bojkofx.log
echo ""
echo "--- Errors in bojkofx.log ---"
ERRORS=$(grep -c "ERROR" /home/macie/bojkofx/logs/bojkofx.log 2>/dev/null || echo 0)
echo "ERROR count: $ERRORS"
grep "ERROR" /home/macie/bojkofx/logs/bojkofx.log | tail -3

