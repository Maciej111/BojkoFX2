#!/usr/bin/env bash
# xdo-check.sh — sprawdz co widzi xdotool i kliknij dialog jesli jest
export DISPLAY=:99

echo "=== xdotool version ==="
xdotool version 2>/dev/null || echo "xdotool not found"

echo ""
echo "=== Watcher log ==="
cat /tmp/xdotool-watcher.log 2>/dev/null || echo "(brak)"

echo ""
echo "=== Wszystkie okna na DISPLAY=:99 ==="
xdotool search --name "" 2>/dev/null | while read wid; do
    name=$(xdotool getwindowname "$wid" 2>/dev/null)
    echo "  WID=$wid  NAME='$name'"
done

echo ""
echo "=== Szukam 'write access' ==="
xdotool search --name "write" 2>/dev/null || echo "  (not found)"

echo ""
echo "=== Szukam 'API' ==="
xdotool search --name "API" 2>/dev/null || echo "  (not found)"

