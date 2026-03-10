#!/usr/bin/env bash
echo "=== Check fix on VM ==="
grep -n "isatty\|non-interactive\|stdin" /home/macie/bojkofx/app/src/runners/run_paper_ibkr_gateway.py

echo ""
echo "=== Clear pyc ==="
find /home/macie/bojkofx/app -name "*.pyc" -delete
echo "pyc cleared"

echo ""
echo "=== Restart bot ==="
sudo systemctl restart bojkofx
sleep 20

echo ""
echo "=== Status ==="
systemctl is-active ibgateway
systemctl is-active bojkofx

echo ""
echo "=== Bot log last 25 ==="
tail -25 /home/macie/bojkofx/logs/bojkofx.log

