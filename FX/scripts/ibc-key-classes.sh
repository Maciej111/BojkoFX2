#!/usr/bin/env bash
mkdir -p /tmp/ibcex && cd /tmp/ibcex
unzip -q /opt/ibc/IBC.jar 2>/dev/null || true

echo "=== ConfigureReadOnlyApiTask ==="
strings ibcalpha/ibc/ConfigureReadOnlyApiTask.class 2>/dev/null

echo ""
echo "=== EnableApiTask ==="
strings ibcalpha/ibc/EnableApiTask.class 2>/dev/null

echo ""
echo "=== SwingUtils ==="
strings ibcalpha/ibc/SwingUtils.class 2>/dev/null | head -40

echo ""
echo "=== GatewayDialogHandler ==="
strings ibcalpha/ibc/GatewayDialogHandler.class 2>/dev/null

echo ""
echo "=== GlobalConfigurationDialogHandler ==="
strings ibcalpha/ibc/GlobalConfigurationDialogHandler.class 2>/dev/null | head -60

