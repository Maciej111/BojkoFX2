"""
Download M60/H1 OHLC data for all FX pairs from Dukascopy.
Output: data/raw_dl_fx/download/m60/
Naming convention: {symbol}_m60_{side}_2021_2024.csv  (mirrors m30 style)
"""
import subprocess
import os
import shutil
from pathlib import Path

# ── config ────────────────────────────────────────────────────────────────────
START  = "2021-01-01"
END    = "2024-12-31"
TF     = "h1"               # dukascopy timeframe flag
OUT    = Path(r"C:\dev\projects\BojkoFx\data\raw_dl_fx\download\m60")

SYMBOLS = [
    "eurusd", "gbpusd", "usdjpy", "usdchf",
    "eurjpy", "gbpjpy",
    "audusd", "nzdusd", "usdcad",
    "eurgbp", "eurchf",
    "gbpchf", "audjpy", "cadjpy",
]
SIDES = ["bid", "ask"]
# ─────────────────────────────────────────────────────────────────────────────

OUT.mkdir(parents=True, exist_ok=True)
TMP = OUT / "_tmp"
TMP.mkdir(exist_ok=True)


def download(symbol: str, side: str) -> bool:
    final_name = f"{symbol}_m60_{side}_2021_2024.csv"
    out_file   = OUT / final_name

    if out_file.exists() and out_file.stat().st_size > 1000:
        print(f"  [SKIP already exists]  {final_name}")
        return True

    # dukascopy writes: {symbol}-h1-{side}-{from}-{to}.csv inside the dir
    expected_dl = TMP / f"{symbol}-h1-{side}-{START}-{END}.csv"
    if expected_dl.exists():
        expected_dl.unlink()

    cmd = [
        "npx.cmd", "dukascopy-node",
        "-i",     symbol,
        "-from",  START,
        "-to",    END,
        "-t",     TF,
        "-p",     side,
        "-f",     "csv",
        "-dir",   str(TMP),
        "--silent",
        "-r",     "3",
    ]

    print(f"  Downloading {symbol.upper()} {side.upper()} h1 ...", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        # Find produced CSV
        csv_files = sorted(TMP.glob("*.csv"), key=lambda f: f.stat().st_mtime)
        if csv_files:
            src = csv_files[-1]
            shutil.move(str(src), str(out_file))
            size_kb = out_file.stat().st_size // 1024
            print(f"  [OK]  {final_name}  ({size_kb} KB)")
            return True
        else:
            print(f"  [FAIL] No CSV for {symbol} {side}")
            if stdout: print("  stdout:", stdout[-300:])
            if stderr: print("  stderr:", stderr[-300:])
            return False

    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] {symbol} {side}")
        return False
    except Exception as e:
        print(f"  [ERROR] {symbol} {side}: {e}")
        return False


ok, fail = [], []

for sym in SYMBOLS:
    print(f"\n[{sym.upper()}]")
    for side in SIDES:
        if download(sym, side):
            ok.append(f"{sym}_{side}")
        else:
            fail.append(f"{sym}_{side}")

# cleanup tmp
shutil.rmtree(TMP, ignore_errors=True)

print()
print(f"=== DONE: {len(ok)} OK, {len(fail)} FAILED ===")
if fail:
    print("Failed:")
    for f in fail:
        print(f"  {f}")

print()
print("Files in m60/:")
for f in sorted(OUT.glob("*.csv")):
    print(f"  {f.name}  ({f.stat().st_size // 1024} KB)")

