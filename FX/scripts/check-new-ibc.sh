#!/usr/bin/env bash
echo "=== version ==="
cat /tmp/ibc-new/version

echo "=== classes with accept/write/allow ==="
unzip -l /tmp/ibc-new/IBC.jar | grep -i 'accept\|write\|allow\|incoming'

echo "=== all strings from new IBC.jar with write or allow ==="
unzip -p /tmp/ibc-new/IBC.jar 'ibcalpha/ibc/*.class' | strings 2>/dev/null | \
  grep -i 'allow\|write\|access\|grant\|deny' | \
  grep -v '^[a-z/]*$\|java\|ibcalpha\|javax\|sun\.\|Ljava\|void\|boolean' | \
  sort -u | head -30

echo "=== config.ini from new IBC ==="
cat /tmp/ibc-new/config.ini

