#!/usr/bin/env bash
# atspi-click-allow.sh — używa AT-SPI do kliknięcia przycisku Allow
export DISPLAY=:99
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus

echo "=== Install AT-SPI ==="
sudo apt-get install -y python3-pyatspi at-spi2-core 2>&1 | tail -3

# Uruchom AT-SPI daemon
/usr/lib/at-spi2-core/at-spi-bus-launcher --launch-immediately &
sleep 2

# Trigger połączenie
pkill -9 -f "python.*trigger\|python.*test_order\|python.*roundtrip" 2>/dev/null || true
sleep 1

/home/macie/bojkofx/venv/bin/python - << 'PY' &
import time
from ib_insync import IB
ib = IB()
try:
    ib.connect("127.0.0.1", 4002, clientId=88, timeout=15)
    print(f"connected: {ib.isConnected()}", flush=True)
except Exception as e:
    print(f"error: {e}", flush=True)
time.sleep(40)
ib.disconnect()
PY
PYTHON_PID=$!

sleep 3

# Kliknij przycisk Allow przez AT-SPI
cat > /tmp/atspi_click.py << 'PY'
import sys, time
import subprocess

# Check if dialog is there first
try:
    import pyatspi
    desktop = pyatspi.Registry.getDesktop(0)
    print(f"AT-SPI desktop: {desktop}")

    def find_button(name_pattern):
        for app in desktop:
            if app is None:
                continue
            try:
                app_name = app.name
                print(f"  App: {app_name}")
                for i in range(app.childCount):
                    win = app.getChildAtIndex(i)
                    if win is None:
                        continue
                    print(f"    Window: {win.name}")
                    # Search recursively
                    def search(node, depth=0):
                        if node is None:
                            return None
                        try:
                            role = node.getRoleName()
                            name = node.name
                            if depth < 5:
                                print(f"{'  '*depth}  [{role}] {name}")
                            if role == 'push button' and name_pattern.lower() in name.lower():
                                return node
                            for j in range(node.childCount):
                                result = search(node.getChildAtIndex(j), depth+1)
                                if result:
                                    return result
                        except Exception as e:
                            pass
                        return None
                    btn = search(win)
                    if btn:
                        return btn
            except Exception as e:
                print(f"  Error: {e}")
        return None

    # Try to find Allow button
    for pattern in ['allow', 'Allow', 'yes', 'Yes', 'ok', 'OK']:
        btn = find_button(pattern)
        if btn:
            print(f"\nFound button: {btn.name}")
            btn.queryAction().doAction(0)
            print("Clicked!")
            sys.exit(0)

    print("Button not found via AT-SPI")
    sys.exit(1)

except Exception as e:
    print(f"AT-SPI error: {e}")
    sys.exit(1)
PY

DISPLAY=:99 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
    python3 /tmp/atspi_click.py

kill "$PYTHON_PID" 2>/dev/null

