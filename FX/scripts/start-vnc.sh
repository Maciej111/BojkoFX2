#!/usr/bin/env bash
# start-vnc.sh — startuje VNC na Xvfb:99
pkill x11vnc 2>/dev/null || true
sleep 1
DISPLAY=:99 x11vnc -display :99 -nopw -listen 0.0.0.0 -port 5901 -shared -forever &
sleep 2
ss -tlnp | grep 5901 && echo "VNC running on :5901" || echo "VNC failed"

