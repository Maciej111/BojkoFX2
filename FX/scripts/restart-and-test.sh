#!/usr/bin/env bash
set -e

echo "[1] Stop gateway"
sudo systemctl stop ibgateway
sleep 2

echo "[2] Deploy new IBC config (AllowApiWriteAccess=yes)"
sudo cp /tmp/ibc-config-new.ini /opt/ibc/config.ini
sudo chown macie:macie /opt/ibc/config.ini
sudo chmod 600 /opt/ibc/config.ini
grep "AllowApi\|ReadOnly" /opt/ibc/config.ini
echo "  OK"

echo "[3] Patch jts.ini — ensure ReadOnlyApi=false + AllowApiWriteAccess"
# Remove stale entries first, then add fresh ones
sed -i '/^ReadOnlyApi=/d' /home/macie/Jts/jts.ini
sed -i '/^AllowApiWriteAccess=/d' /home/macie/Jts/jts.ini
sed -i '/^\[IBGateway\]/a ReadOnlyApi=false\nAllowApiWriteAccess=yes' /home/macie/Jts/jts.ini
echo "  jts.ini:"
cat /home/macie/Jts/jts.ini

echo "[4] Start gateway"
sudo systemctl start ibgateway
echo "  Waiting 80s for IBC auto-login..."
sleep 80

echo "[5] Port check"
ss -tlnp | grep 4002 && echo "PORT 4002 OPEN" || echo "PORT 4002 NOT OPEN"

echo "[6] jts.ini after login (IBC may overwrite)"
cat /home/macie/Jts/jts.ini

echo "[7] Run order round-trip test"
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

