#!/usr/bin/env python3
"""Bump the package version, commit, tag, and push — the one command to run
after you've made changes and want them to ship to PyPI.

Usage:
    python scripts/release.py           # patch bump: 0.1.0 -> 0.1.1
    python scripts/release.py minor     # 0.1.0 -> 0.2.0
    python scripts/release.py major     # 0.1.0 -> 1.0.0
    python scripts/release.py 0.3.0     # set an explicit version

This does NOT publish to PyPI by itself. It ends by printing a GitHub URL —
open it and click "Publish release". That's the trigger that runs
.github/workflows/publish.yml and pushes the new version to PyPI via
trusted publishing. Keeping that as a manual click means a bad `git push`
can never accidentally burn a PyPI version (uploads there are permanent).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
REPO = "Playgentik/playgentik-python"


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def current_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        sys.exit("Could not find `version = \"...\"` in pyproject.toml")
    return m.group(1)


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:  # patch
        patch += 1
    return f"{major}.{minor}.{patch}"


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "patch"
    old = current_version()

    if re.fullmatch(r"\d+\.\d+\.\d+", arg):
        new = arg
    elif arg in ("major", "minor", "patch"):
        new = bump(old, arg)
    else:
        sys.exit(f"Usage: release.py [major|minor|patch|X.Y.Z] (got {arg!r})")

    if new == old:
        sys.exit(f"New version {new} is the same as the current version — nothing to do.")

    text = PYPROJECT.read_text()
    text = re.sub(
        r'^version\s*=\s*"[^"]+"',
        f'version = "{new}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(text)

    run("git", "add", "-A")
    run("git", "commit", "-m", f"chore: release v{new}")
    run("git", "tag", f"v{new}")
    run("git", "push", "origin", "HEAD")
    run("git", "push", "origin", f"v{new}")

    url = f"https://github.com/{REPO}/releases/new?tag=v{new}&title=v{new}"
    print(f"\nBumped {old} -> {new}, committed, tagged, and pushed.")
    print("Now open this and click 'Publish release' to actually trigger the PyPI publish:\n")
    print(f"  {url}\n")


if __name__ == "__main__":
    main()
