#!/usr/bin/env bash
# probe-ibgw.sh — check ibgateway structure and IBC jars detection
echo "=== ibgateway dir ==="
ls -la /home/macie/ibgateway/

echo ""
echo "=== jars/ ==="
ls /home/macie/ibgateway/jars/ | head -10

echo ""
echo "=== IBC jars detection logic ==="
# IBC looks for jars/jts4launch-*.jar to detect version
ls /home/macie/ibgateway/jars/jts4launch* 2>/dev/null || echo "NOT FOUND: jts4launch*.jar"

echo ""
echo "=== .install4j dir ==="
ls /home/macie/ibgateway/.install4j/ 2>/dev/null || echo "no .install4j"

echo ""
echo "=== IBC ibcstart.sh version check lines ==="
grep -n "jars\|offline\|jts4launch\|TWS_VRSN\|tws-path\|TWS_PATH" /opt/ibc/scripts/ibcstart.sh | head -40

