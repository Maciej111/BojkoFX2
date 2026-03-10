#!/usr/bin/env bash
echo "=== Restart bota ==="
sudo systemctl restart bojkofx
sleep 15

echo "=== Status ==="
systemctl is-active bojkofx
systemctl is-active ibgateway

echo ""
echo "=== Bot log (ostatnie 30 linii) ==="
tail -30 /home/macie/bojkofx/logs/bojkofx.log

echo ""
echo "=== Port 4002 ==="
ss -tlnp | grep 4002

echo ""
echo "=== Bledy w logu bota ==="
grep -i "ERROR\|WARN\|Exception\|Traceback" /home/macie/bojkofx/logs/bojkofx.log | tail -10

