#!/usr/bin/env python3
"""Set a release version or transient development label for the editor extension."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "extension" / "orbit-site-map-editor" / "manifest.json"
VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")


def validate_version(value: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError("version must contain one to four dot-separated integers")
    parts = value.split(".")
    if all(int(part) == 0 for part in parts):
        raise ValueError("version cannot be all zero")
    for part in parts:
        if len(part) > 1 and part.startswith("0"):
            raise ValueError("non-zero version components cannot start with zero")
        if int(part) > 65535:
            raise ValueError("version components must be at most 65535")
    return value


def read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    validate_version(str(payload.get("version", "")))
    return payload


def git_text(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""


def inferred_dev_label(version: str) -> str:
    branch = git_text("branch", "--show-current") or "detached"
    revision = git_text("rev-parse", "--short", "HEAD") or "unknown"
    dirty = bool(git_text("status", "--porcelain"))
    suffix = " dirty" if dirty else ""
    return f"{version} dev {branch}@{revision}{suffix}"


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = root.add_subparsers(dest="command", required=True)

    dev = subparsers.add_parser("dev", help="add a transient display-only development label")
    dev.add_argument("--label", help="explicit label; defaults to version, branch, and revision")

    release = subparsers.add_parser("release", help="set or restore release manifest metadata")
    release.add_argument("version", nargs="?", help="new numeric Chrome extension version")
    release.add_argument(
        "--keep-version",
        action="store_true",
        help="remove version_name without changing the numeric version",
    )
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest_path = args.manifest.resolve()
    manifest = read_manifest(manifest_path)

    if args.command == "dev":
        label = (args.label or inferred_dev_label(manifest["version"])).strip()
        if not label:
            raise ValueError("development label cannot be empty")
        manifest["version_name"] = label[:256]
    else:
        if args.keep_version == bool(args.version):
            raise ValueError("release requires either VERSION or --keep-version")
        if args.version:
            manifest["version"] = validate_version(args.version)
        manifest.pop("version_name", None)

    write_manifest(manifest_path, manifest)
    display = manifest.get("version_name", manifest["version"])
    print(f"Editor extension build label: {display}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}") from None
