#!/usr/bin/env bash
# javap-probe.sh
echo "=== javap AcceptIncomingConnectionDialogHandler ==="
cd /opt/ibc
javap -c -p ibcalpha/ibc/AcceptIncomingConnectionDialogHandler.class 2>/dev/null || \
  (jar xf IBC.jar ibcalpha/ibc/AcceptIncomingConnectionDialogHandler.class 2>/dev/null && \
   javap -c -p ibcalpha/ibc/AcceptIncomingConnectionDialogHandler.class 2>/dev/null) | head -60

echo ""
echo "=== All IBC class names with 'connect' or 'write' ==="
jar tf /opt/ibc/IBC.jar | grep -i 'connect\|write\|Allow\|accept' | sort

echo ""
echo "=== strings in IBC.jar - dialog button labels ==="
jar xf /opt/ibc/IBC.jar 2>/dev/null
find /opt/ibc/ibcalpha -name '*.class' 2>/dev/null | xargs javap -c 2>/dev/null | \
  grep -i 'Allow\|write.*access\|grant\|deny\|ldc.*write\|ldc.*allow' | head -20

