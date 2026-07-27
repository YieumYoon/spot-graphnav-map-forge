#!/usr/bin/env python3
"""Bump, label, or release an editor-extension build."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

if __package__:
    from .chrome_version import validate_chrome_version
else:
    from chrome_version import validate_chrome_version

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "extension" / "orbit-site-map-editor" / "manifest.json"


def validate_version(value: str) -> str:
    return validate_chrome_version(value)


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


def inferred_dev_identity() -> str:
    branch = git_text("branch", "--show-current") or "detached"
    revision = git_text("rev-parse", "--short", "HEAD") or "unknown"
    dirty = bool(git_text("status", "--porcelain"))
    suffix = " dirty" if dirty else ""
    return f"{branch}@{revision}{suffix}"


def bump_version(version: str, change: str) -> str:
    parts = [int(part) for part in validate_version(version).split(".")]
    if len(parts) != 3:
        raise ValueError("automatic version bumps require a three-part version")
    major, minor, patch = parts
    if change == "fix":
        patch += 1
    elif change == "feature":
        minor += 1
        patch = 0
    elif change == "breaking":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError("unsupported change type")
    return validate_version(f"{major}.{minor}.{patch}")


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = root.add_subparsers(dest="command", required=True)

    bump = subparsers.add_parser(
        "bump",
        help="bump the numeric version and set its development label",
    )
    bump.add_argument(
        "change",
        choices=("fix", "feature", "breaking"),
        help="fix bumps patch, feature bumps minor, breaking bumps major",
    )
    bump.add_argument(
        "--label",
        help="short development label; defaults to branch and revision",
    )

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

    if args.command == "bump":
        manifest["version"] = bump_version(manifest["version"], args.change)
        identity = (args.label or inferred_dev_identity()).strip()
        if not identity:
            raise ValueError("development label cannot be empty")
        manifest["version_name"] = f"{manifest['version']} dev {identity}"[:256]
    elif args.command == "dev":
        identity = (args.label or inferred_dev_identity()).strip()
        if not identity:
            raise ValueError("development label cannot be empty")
        manifest["version_name"] = f"{manifest['version']} dev {identity}"[:256]
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
