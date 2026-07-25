#!/usr/bin/env python3
"""Run deterministic static qualification for the Orbit Site Map Editor extension."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

if __package__:
    from .chrome_version import validate_chrome_version
else:
    from chrome_version import validate_chrome_version

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension" / "orbit-site-map-editor"
MANIFEST = EXTENSION / "manifest.json"
QUALIFICATION = ROOT / "docs" / "orbit-site-map-editor-qualification.md"


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def validate_manifest(*, release: bool) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
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
        qualification = QUALIFICATION.read_text(encoding="utf-8")
        expected = f"- Extension release: {manifest['version']}"
        if expected not in qualification:
            fail("qualification document does not name the manifest release version")

    listed_paths: list[str] = []
    for content_script in manifest.get("content_scripts", []):
        listed_paths.extend(content_script.get("css", []))
        listed_paths.extend(content_script.get("js", []))
    for resource in manifest.get("web_accessible_resources", []):
        listed_paths.extend(resource.get("resources", []))
    missing = sorted(path for path in set(listed_paths) if not (EXTENSION / path).is_file())
    if missing:
        fail(f"manifest references missing files: {', '.join(missing)}")

    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    if "extensionContext.getVersionLabel" not in content:
        fail("panel must read its build label from the extension manifest")
    if re.search(r'class="osme-version">[0-9]', content):
        fail("panel contains a hardcoded displayed version")
    return manifest


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--full", action="store_true", help="run the entire test suite")
    result.add_argument(
        "--release",
        action="store_true",
        help="also require release manifest metadata with no development label",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = validate_manifest(release=args.release)
    run([sys.executable, str(ROOT / "scripts" / "check_active_boundary.py")])

    node = shutil.which("node")
    ruff = shutil.which("ruff")
    if not node:
        fail("node is required; use the repository Node.js environment")
    if not ruff:
        fail("ruff is required; run this script through uv")

    for source in sorted(EXTENSION.glob("*.js")):
        run([node, "--check", str(source)])

    tests = (
        []
        if args.full
        else [
            "tests/test_editor_extension.py",
            "tests/test_editor_dev_workflow.py",
            "tests/test_workflow_docs.py",
        ]
    )
    run([sys.executable, "-m", "pytest", *tests])
    run([ruff, "check", "."])
    run([ruff, "format", "--check", "."])

    label = manifest.get("version_name", manifest["version"])
    scope = "full" if args.full else "targeted"
    print(f"Editor extension {scope} qualification passed: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
