#!/usr/bin/env bash
# diagnostics — run as macie
{
echo "=== DATE ==="
date -u

echo "=== SYSTEMCTL STATUS ==="
sudo systemctl status ibgateway --no-pager -l 2>&1 || true

echo "=== PORT 4002 ==="
ss -tlnp 2>/dev/null | grep 4002 || echo "port 4002 not open yet"

echo "=== PROCESSES ==="
ps aux | grep -E "(ibgateway|Xvfb|java)" | grep -v grep || echo "none"

echo "=== GATEWAY LOG TAIL ==="
tail -30 /home/macie/bojkofx/logs/gateway.log 2>/dev/null || echo "no log"

echo "=== ROOT/JTS ==="
ls -la /root/Jts/ 2>/dev/null || echo "/root/Jts missing"

} > /tmp/diag.txt 2>&1
echo "DIAG_DONE"
cat /tmp/diag.txt

