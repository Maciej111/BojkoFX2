#!/usr/bin/env bash
# fix2 — run as sudo bash /tmp/fix2.sh
set -e

echo "[1] Fix /root/Jts"
mkdir -p /root/Jts
chmod 777 /root/Jts
ls -la /root/Jts
echo "  OK"

echo "[2] Restart ibgateway with fixed /root/Jts"
systemctl restart ibgateway
echo "  Waiting 30s for gateway to boot..."
sleep 30

echo "[3] Port check"
ss -tlnp | grep 4002 && echo "PORT 4002 OPEN" || echo "port 4002 not open yet"

echo "[4] Process list"
ps aux | grep -E "(ibgateway|Xvfb|java)" | grep -v grep

echo "[5] Status"
systemctl status ibgateway --no-pager -l

echo "[6] Log tail (last 20)"
tail -20 /home/macie/bojkofx/logs/gateway.log

