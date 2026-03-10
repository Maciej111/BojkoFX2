#!/usr/bin/env bash
echo "=== /home/macie/Jts/ ==="
ls -la /home/macie/Jts/

echo ""
echo "=== find xml/api files ==="
find /home/macie/Jts /home/macie/ibgateway -type f 2>/dev/null | grep -v ".install4j" | head -30

echo ""
echo "=== jts.ini full ==="
cat /home/macie/Jts/jts.ini

echo ""
echo "=== grep ReadOnly w Jts ==="
grep -ri "readonly\|read.only\|ApiReadOnly" /home/macie/Jts/ 2>/dev/null || echo "NOT FOUND"

