from __future__ import annotations

import argparse
import subprocess
import sys
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


def run_command(cmd: list[str]) -> int:
    cmd_str = subprocess.list2cmdline(cmd) if sys.platform.startswith("win") else shlex.join(cmd)
    return subprocess.run(cmd_str, check=False, shell=True).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Dukascopy M1 data year by year")
    parser.add_argument("--symbol", default="usatechidxusd", help="Dukascopy instrument symbol, e.g. usatechidxusd")
    parser.add_argument("--years", nargs="+", type=int, required=True, help="Years to download, e.g. 2021 2022 2023")
    parser.add_argument(
        "--output-dir",
        default=str(Path("data") / "1M"),
        help="Directory where CSV files will be saved",
    )
    args = parser.parse_args()

    years = sorted(set(args.years))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    failures: list[int] = []
    for year in years:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        cmd = build_command(args.symbol, start_date, end_date, output_dir)
        print(f"\n=== Downloading {args.symbol} for {year} ===")
        print("Running:", " ".join(cmd))
        rc = run_command(cmd)
        if rc != 0:
            failures.append(year)

    if failures:
        print(f"\nDownload failures for years: {failures}")
        return 1

    print("\nAll requested yearly downloads completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

