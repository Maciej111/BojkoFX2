#!/bin/bash
cd /home/macie/bojkofx/app
echo "=== BOM check ==="
for f in src/runners/run_paper_ibkr_gateway.py src/execution/ibkr_exec.py; do
    first=$(head -c 3 "$f" | xxd -p)
    echo "  $f -> first bytes: $first"
done
echo "=== Python syntax check ==="
/home/macie/bojkofx/venv/bin/python -m py_compile src/runners/run_paper_ibkr_gateway.py 2>&1
/home/macie/bojkofx/venv/bin/python -m py_compile src/execution/ibkr_exec.py 2>&1
echo "=== Import check ==="
/home/macie/bojkofx/venv/bin/python -c "import src.runners.run_paper_ibkr_gateway" 2>&1
echo "=== Done ==="
