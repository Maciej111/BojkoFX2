from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
import shlex


def build_command(symbol: str, start_date: str, end_date: str, output_dir: Path) -> list[str]:
    return [
        "npx",
        "dukascopy-node",
        "-i",
        symbol.lower(),
        "-from",
        start_date,
        "-to",
        end_date,
        "-t",
        "m1",
        "-f",
        "csv",
        "-dir",
        str(output_dir),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a small Dukascopy M1 sample")
    parser.add_argument("--symbol", default="usatechidxusd", help="Dukascopy instrument symbol, e.g. usatechidxusd")
    parser.add_argument("--days", type=int, default=3, help="How many recent days to download")
    parser.add_argument(
        "--output-dir",
        default=str(Path("data") / "1M"),
        help="Directory where CSV files will be saved",
    )
    args = parser.parse_args()

    if args.days <= 0:
        raise SystemExit("--days must be > 0")

    end_day = date.today()
    start_day = end_day - timedelta(days=args.days)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_command(args.symbol, start_day.isoformat(), end_day.isoformat(), output_dir)

    print("Running:", " ".join(cmd))
    cmd_str = subprocess.list2cmdline(cmd) if sys.platform.startswith("win") else shlex.join(cmd)
    result = subprocess.run(cmd_str, check=False, shell=True)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
