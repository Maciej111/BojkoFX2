#!/usr/bin/env python3
"""
scripts/changelog.py — helper do zarządzania CHANGELOG.md i VERSION.

Użycie:
  python scripts/changelog.py add fixed "Opis zmiany"
  python scripts/changelog.py add added "Nowa funkcja"
  python scripts/changelog.py bump minor          # 0.4.0 → 0.5.0
  python scripts/changelog.py bump patch          # 0.4.0 → 0.4.1
  python scripts/changelog.py bump major          # 0.4.0 → 1.0.0
  python scripts/changelog.py release            # taguje bieżącą wersję w pliku
  python scripts/changelog.py version            # wypisuje bieżącą wersję

Sekcja "Unreleased" jest automatycznie uzupełniana.
Przy `release` sekcja Unreleased staje się nową wersjonowaną sekcją.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
VERSION_FILE = ROOT / "VERSION"

VALID_TYPES = {"added", "changed", "fixed", "removed", "security"}


# ── helpers ──────────────────────────────────────────────────────────────────

def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def write_version(v: str) -> None:
    VERSION_FILE.write_text(v + "\n", encoding="utf-8")
    print(f"VERSION → {v}")


def bump(part: str) -> str:
    """Return new version string after bumping major/minor/patch."""
    v = read_version()
    parts = v.split(".")
    if len(parts) != 3:
        sys.exit(f"VERSION '{v}' nie jest w formacie MAJOR.MINOR.PATCH")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        major += 1; minor = 0; patch = 0
    elif part == "minor":
        minor += 1; patch = 0
    elif part == "patch":
        patch += 1
    else:
        sys.exit(f"Nieznany typ bumpa: '{part}'. Użyj major/minor/patch.")
    return f"{major}.{minor}.{patch}"


def read_changelog() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def write_changelog(text: str) -> None:
    CHANGELOG.write_text(text, encoding="utf-8")


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_version() -> None:
    print(read_version())


def cmd_bump(part: str) -> None:
    new_v = bump(part)
    write_version(new_v)


def cmd_add(entry_type: str, message: str) -> None:
    et = entry_type.lower()
    if et not in VALID_TYPES:
        sys.exit(f"Nieznany typ: '{et}'. Dozwolone: {', '.join(sorted(VALID_TYPES))}")

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section_header = f"### {et.capitalize()}"
    new_line = f"- [{now}] {message}"

    text = read_changelog()

    # Find the Unreleased block and insert / append to the right sub-section.
    unreleased_pattern = re.compile(r"(## \[Unreleased\].*?)(?=\n## \[|\Z)", re.DOTALL)
    m = unreleased_pattern.search(text)
    if not m:
        sys.exit("Nie znaleziono sekcji '## [Unreleased]' w CHANGELOG.md")

    unreleased_block = m.group(1)

    if section_header in unreleased_block:
        # Append after the last entry of the existing sub-section.
        updated_block = unreleased_block.replace(
            section_header,
            section_header,
            1,
        )
        # Insert after the last line of that sub-section.
        sub_pattern = re.compile(
            rf"({re.escape(section_header)}\n(?:- .*\n)*)", re.MULTILINE
        )
        sm = sub_pattern.search(unreleased_block)
        if sm:
            old_sub = sm.group(1)
            new_sub = old_sub.rstrip("\n") + f"\n{new_line}\n"
            updated_block = unreleased_block.replace(old_sub, new_sub, 1)
        else:
            updated_block = unreleased_block + f"\n{section_header}\n{new_line}\n"
    else:
        # Add a brand-new sub-section inside Unreleased.
        updated_block = unreleased_block.rstrip("\n") + f"\n\n{section_header}\n{new_line}\n"

    new_text = text[:m.start()] + updated_block + text[m.end():]
    write_changelog(new_text)
    print(f"Dodano do [Unreleased] / {section_header}: {message}")


def cmd_release() -> None:
    """Move [Unreleased] content into a new versioned section."""
    version = read_version()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    text = read_changelog()

    unreleased_pattern = re.compile(r"(## \[Unreleased\]\n)(.*?)(?=\n## \[|\Z)", re.DOTALL)
    m = unreleased_pattern.search(text)
    if not m:
        sys.exit("Nie znaleziono sekcji '## [Unreleased]' w CHANGELOG.md")

    unreleased_content = m.group(2).strip()
    if not unreleased_content:
        print("Brak zmian w [Unreleased] — nie ma czego wydawać.")
        return

    new_version_section = f"\n## [{version}] — {today}\n\n{unreleased_content}\n"
    empty_unreleased = "## [Unreleased]\n\n---\n"

    # Replace Unreleased with empty + insert new version section after the "---"
    new_text = (
        text[:m.start()]
        + empty_unreleased
        + new_version_section
        + text[m.end():]
    )
    write_changelog(new_text)
    print(f"Wydano wersję {version} w CHANGELOG.md ({today})")
    print("Pamiętaj: git tag v" + version)


# ── entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "version":
        cmd_version()
    elif cmd == "bump":
        if len(args) < 2:
            sys.exit("Użycie: changelog.py bump major|minor|patch")
        cmd_bump(args[1])
    elif cmd == "add":
        if len(args) < 3:
            sys.exit("Użycie: changelog.py add <typ> <opis>")
        cmd_add(args[1], " ".join(args[2:]))
    elif cmd == "release":
        cmd_release()
    else:
        sys.exit(f"Nieznana komenda: '{cmd}'. Użyj add / bump / release / version.")


if __name__ == "__main__":
    main()
