#!/usr/bin/env bash
set -e

BOJKOFX_DIR="/home/macie/bojkofx"
JTS_DIR="/home/macie/Jts"

echo "[1] Stop gateway + kill all related processes"
sudo systemctl stop ibgateway 2>/dev/null || true
pkill -f ibgateway 2>/dev/null || true
pkill -f "Xvfb :99" 2>/dev/null || true
pkill -f ibcstart 2>/dev/null || true
sleep 3
echo "  OK"

echo "[2] Clear IB session cache (forces fresh login)"
# Remove encrypted session state — IBC will do fresh login
rm -rf "${JTS_DIR}/jfdomhmhibimkahpinbekgajoahcfpbpokdhbkfi" 2>/dev/null || true
rm -f "${JTS_DIR}/launcher.log" 2>/dev/null || true
echo "  Cleared session cache"

echo "[3] Write clean jts.ini with ReadOnlyApi=false"
cat > "${JTS_DIR}/jts.ini" << 'INI'
[IBGateway]
WriteDebug=false
TrustedIPs=127.0.0.1
RemoteHostOrderRouting=ndc1.ibllc.com
RemotePortOrderRouting=4001
ApiOnly=true
LocalServerPort=4000
ReadOnlyApi=false
AllowApiWriteAccess=yes

[Logon]
useRemoteSettings=false
TimeZone=Etc/UTC
tradingMode=p
colorPalletName=dark
Steps=9
Locale=en
UseSSL=true
s3store=true
displayedproxymsg=1
ibkrBranding=pro
INI
chown macie:macie "${JTS_DIR}/jts.ini"
echo "  Written OK:"
cat "${JTS_DIR}/jts.ini"

echo ""
echo "[4] Start gateway (fresh session)"
sudo systemctl start ibgateway
echo "  Waiting 90s for IBC auto-login..."
sleep 90

echo ""
echo "[5] Checks"
ss -tlnp | grep 4002 && echo "  PORT 4002 OPEN" || echo "  PORT 4002 NOT OPEN"
echo ""
echo "  jts.ini AFTER login:"
cat "${JTS_DIR}/jts.ini"

echo ""
echo "[6] Run order test"
cd /home/macie/bojkofx/app
IBKR_HOST=127.0.0.1 IBKR_PORT=4002 IBKR_READONLY=false ALLOW_LIVE_ORDERS=true \
    /home/macie/bojkofx/venv/bin/python /tmp/test_order_roundtrip.py

