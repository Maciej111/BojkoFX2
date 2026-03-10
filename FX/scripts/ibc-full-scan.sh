#!/usr/bin/env bash
mkdir -p /tmp/ibcex && cd /tmp/ibcex
unzip -q /opt/ibc/IBC.jar 2>/dev/null || true

echo "=== All strings from IBC classes ==="
find . -name '*.class' | xargs strings 2>/dev/null | sort -u > /tmp/all_ibc_strings.txt
wc -l /tmp/all_ibc_strings.txt

echo "=== write / access / allow strings ==="
grep -i 'write\|access\|allow\|grant\|confirm' /tmp/all_ibc_strings.txt | grep -v '^[a-z/.()*;]*$' | head -30

echo "=== AcceptIncoming handler strings ==="
strings /tmp/ibcex/ibcalpha/ibc/AcceptIncomingConnectionDialogHandler.class 2>/dev/null

echo "=== ALL class files ==="
find . -name '*.class' | sed 's|.*/||;s|\.class||' | sort

