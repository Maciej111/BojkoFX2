#!/usr/bin/env bash
# probe-ibc-strings.sh
echo "=== Extract IBC.jar with unzip ==="
mkdir -p /tmp/ibcex && cd /tmp/ibcex
unzip -q /opt/ibc/IBC.jar 2>/dev/null
echo "Extracted: $(find . -name '*.class' | wc -l) classes"

echo ""
echo "=== Class list: connect/write/allow/accept ==="
find . -name '*.class' | sed 's|.*/||;s|\.class||' | sort | grep -i 'connect\|write\|Allow\|accept\|incoming' | head -20

echo ""
echo "=== strings from all classes: write/allow/grant ==="
find . -name '*.class' -exec strings {} \; 2>/dev/null | \
  grep -i 'allow\|grant\|write.*access\|write access\|write-access' | \
  grep -v 'copyright\|author\|import\|class ' | sort -u | head -30

echo ""
echo "=== strings from AcceptIncoming class ==="
find . -name '*Accept*' -o -name '*Incoming*' | while read f; do
  echo "--- $f ---"
  strings "$f" 2>/dev/null | grep -v '^[a-z]*$' | head -20
done

echo ""
echo "=== ALL strings about 'write' from all classes ==="
find . -name '*.class' -exec strings {} \; 2>/dev/null | grep -i 'write' | sort -u | head -20

