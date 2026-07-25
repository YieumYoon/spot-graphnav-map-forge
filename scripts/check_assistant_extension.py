#!/usr/bin/env python3
"""Run deterministic static qualification for the Orbit Site Map Assistant extension."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

if __package__:
    from .chrome_version import validate_chrome_version
else:
    from chrome_version import validate_chrome_version

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension" / "orbit-graph-repair"
MANIFEST = EXTENSION / "manifest.json"
RELEASE_RECORD = ROOT / "docs" / "orbit-map-assistant-knowledge-base.md"


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def _listed_paths(manifest: dict) -> list[str]:
    listed_paths: list[str] = []
    for content_script in manifest.get("content_scripts", []):
        listed_paths.extend(content_script.get("css", []))
        listed_paths.extend(content_script.get("js", []))
    for resource in manifest.get("web_accessible_resources", []):
        listed_paths.extend(resource.get("resources", []))
    return listed_paths


def validate_manifest(
    *,
    release: bool,
    manifest_path: Path = MANIFEST,
    extension: Path = EXTENSION,
    release_record: Path = RELEASE_RECORD,
) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"could not read manifest: {error}")
    if not isinstance(manifest, dict):
        fail("manifest must be a JSON object")

    try:
        validate_chrome_version(manifest.get("version"))
    except ValueError as error:
        fail(f"manifest {error}")

    version_name = manifest.get("version_name")
    if version_name is not None and (not isinstance(version_name, str) or not version_name.strip()):
        fail("manifest version_name must be a non-empty string")
    if release and version_name is not None:
        fail("release qualification requires removing transient version_name")
    if release:
        try:
            current_release = release_record.read_text(encoding="utf-8")
        except OSError as error:
            fail(f"could not read Assistant release record: {error}")
        expected = f"The current extension version is {manifest['version']}."
        if expected not in " ".join(current_release.split()):
            fail("Assistant release record does not name the manifest version")

    listed_paths = _listed_paths(manifest)
    invalid = sorted(
        {repr(path) for path in listed_paths if not isinstance(path, str) or not path.strip()}
    )
    if invalid:
        fail(f"manifest contains invalid file references: {', '.join(invalid)}")
    missing = sorted(path for path in set(listed_paths) if not (extension / path).is_file())
    if missing:
        fail(f"manifest references missing files: {', '.join(missing)}")
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--release",
        action="store_true",
        help="also require release manifest metadata with no development label",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = validate_manifest(release=args.release)

    node = shutil.which("node")
    if not node:
        fail("node is required; use the repository Node.js environment")
    for source in sorted(EXTENSION.glob("*.js")):
        run([node, "--check", str(source)])

    label = manifest.get("version_name", manifest["version"])
    print(f"Assistant extension static qualification passed: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
