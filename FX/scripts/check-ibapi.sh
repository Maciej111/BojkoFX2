#!/usr/bin/env bash
echo "=== pip list | grep ib ==="
/home/macie/bojkofx/venv/bin/pip list 2>/dev/null | grep -i "ib\|ibapi\|interac"

echo ""
echo "=== find ibapi ==="
find /home/macie/bojkofx /home/macie -name "ibapi" -type d 2>/dev/null | head -10

echo ""
echo "=== PYTHONPATH check ==="
/home/macie/bojkofx/venv/bin/python -c "import sys; print('\n'.join(sys.path))"

