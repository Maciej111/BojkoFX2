#!/usr/bin/env python3
"""Remove UTF-8 BOM from Python source files if present."""
import sys

files = [
    "src/execution/ibkr_exec.py",
    "src/runners/run_paper_ibkr_gateway.py",
]

for path in files:
    with open(path, "rb") as f:
        content = f.read()
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
        with open(path, "wb") as f:
            f.write(content)
        print(f"BOM removed: {path}")
    else:
        print(f"No BOM:      {path}")

    # verify
    with open(path, "rb") as f:
        first = f.read(4)
    print(f"  First bytes: {first.hex()}")

