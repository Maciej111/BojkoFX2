#!/usr/bin/env bash
# ibc-jar-probe.sh
echo "=== IBC.jar contents ==="
mkdir -p /tmp/ibcjar && cd /tmp/ibcjar
jar xf /opt/ibc/IBC.jar 2>/dev/null
echo "Classes count: $(find . -name '*.class' | wc -l)"
echo ""
echo "=== Classes with accept/write/allow/api ==="
find . -name '*.class' | sed 's|.*/||' | sort | grep -i 'api\|accept\|write\|allow\|connection' | head -30
echo ""
echo "=== javap ApiSettings or similar ==="
find . -name '*Api*' -o -name '*Accept*' -o -name '*Allow*' | head -10
echo ""
echo "=== strings from IBC.jar matching write/allow/accept ==="
strings /opt/ibc/IBC.jar | grep -i 'writeAccess\|write.access\|Allow.*write\|acceptIncoming\|write.*access' | sort -u | head -20
echo ""
echo "=== Check IBC version ==="
cat /opt/ibc/scripts/ibcstart.sh | grep -i 'IBC_VRSN\|version' | head -5

