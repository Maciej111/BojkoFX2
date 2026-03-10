#!/usr/bin/env bash
# upgrade-ibc.sh — upgrade IBC to latest version which handles write-access dialog
set -euo pipefail

echo "[1] Check current IBC version"
grep -i 'version\|IBC' /opt/ibc/IBC.jar_manifest 2>/dev/null || \
  unzip -p /opt/ibc/IBC.jar META-INF/MANIFEST.MF 2>/dev/null || echo "unknown"

# IBC 3.18.0+ handles the write-access dialog via AcceptIncomingConnectionWithWriteAccessAction
IBC_VERSION="3.18.0"
IBC_URL="https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCLinux-${IBC_VERSION}.zip"

echo ""
echo "[2] Download IBC ${IBC_VERSION}"
wget -q --show-progress -O /tmp/ibc-new.zip "$IBC_URL" 2>&1 || {
    echo "Download failed, trying latest..."
    # Try to get latest release
    LATEST=$(curl -s https://api.github.com/repos/IbcAlpha/IBC/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    echo "Latest version: $LATEST"
    wget -q -O /tmp/ibc-new.zip "https://github.com/IbcAlpha/IBC/releases/download/${LATEST}/IBCLinux-${LATEST}.zip" 2>&1
}

echo ""
echo "[3] Backup current IBC"
sudo cp -r /opt/ibc /opt/ibc.backup

echo ""
echo "[4] Install new IBC"
mkdir -p /tmp/ibc-new
unzip -q /tmp/ibc-new.zip -d /tmp/ibc-new
ls /tmp/ibc-new/

sudo cp /tmp/ibc-new/*.jar /opt/ibc/ 2>/dev/null || true
sudo cp /tmp/ibc-new/scripts/*.sh /opt/ibc/scripts/ 2>/dev/null || true
sudo chmod +x /opt/ibc/scripts/*.sh

echo ""
echo "[5] Check new version"
unzip -p /opt/ibc/IBC.jar META-INF/MANIFEST.MF 2>/dev/null | grep -i version

echo "Done"

