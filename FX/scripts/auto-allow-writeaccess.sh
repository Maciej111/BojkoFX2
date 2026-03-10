#!/usr/bin/env bash
# auto-allow-writeaccess.sh
# Watchdog: auto-click "Allow" on IB Gateway write-access dialog
# Run in background before test: bash /tmp/auto-allow-writeaccess.sh &

export DISPLAY=:99
LOGFILE="/tmp/xdotool-watcher.log"

echo "[$(date)] Write-access watcher started (DISPLAY=$DISPLAY)" > "$LOGFILE"

# Wait for the dialog and click Allow button
for i in $(seq 1 30); do
    sleep 2
    # Find the write-access confirmation window
    WIN=$(xdotool search --name "API client needs write access" 2>/dev/null | head -1)
    if [ -n "$WIN" ]; then
        echo "[$(date)] Found write-access dialog: WID=$WIN" >> "$LOGFILE"
        # Get window geometry
        xdotool windowactivate --sync "$WIN" 2>/dev/null
        sleep 0.5
        # Click "Allow" button (try multiple positions for the Allow/Yes button)
        xdotool key --window "$WIN" Return 2>/dev/null
        echo "[$(date)] Sent Enter key to dialog" >> "$LOGFILE"
        sleep 0.5
        # Also try clicking OK/Allow button directly
        xdotool click --window "$WIN" 1 2>/dev/null || true
        echo "[$(date)] Clicked window" >> "$LOGFILE"
        exit 0
    fi
done

echo "[$(date)] Write-access dialog not found within 60s" >> "$LOGFILE"

