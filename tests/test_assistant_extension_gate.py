from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_assistant_extension import validate_manifest  # noqa: E402


def write_extension(
    root: Path,
    *,
    version: object = "0.8.1",
    version_name: object | None = None,
    missing_script: bool = False,
) -> tuple[Path, Path, Path]:
    extension = root / "extension"
    extension.mkdir()
    for name in ("panel.css", "content.js", "page-bridge.js"):
        if missing_script and name == "content.js":
            continue
        (extension / name).write_text("", encoding="utf-8")

    manifest = {
        "manifest_version": 3,
        "name": "Orbit Site Map Assistant",
        "version": version,
        "content_scripts": [{"css": ["panel.css"], "js": ["content.js"]}],
        "web_accessible_resources": [{"resources": ["page-bridge.js"]}],
    }
    if version_name is not None:
        manifest["version_name"] = version_name
    manifest_path = extension / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    release_record = root / "release.md"
    release_record.write_text(
        f"The current extension version is {version}.",
        encoding="utf-8",
    )
    return manifest_path, extension, release_record


def test_assistant_gate_accepts_valid_manifest_and_development_label(tmp_path: Path) -> None:
    manifest_path, extension, release_record = write_extension(
        tmp_path,
        version_name="0.8.1 dev feature-a",
    )

    manifest = validate_manifest(
        release=False,
        manifest_path=manifest_path,
        extension=extension,
        release_record=release_record,
    )

    assert manifest["version"] == "0.8.1"
    assert manifest["version_name"] == "0.8.1 dev feature-a"


@pytest.mark.parametrize("version", ["0", "1.02", "1.2.3.4.5", "1-beta"])
def test_assistant_gate_reuses_chrome_version_validation(
    tmp_path: Path,
    version: str,
) -> None:
    manifest_path, extension, release_record = write_extension(tmp_path, version=version)

    with pytest.raises(SystemExit, match="ERROR: manifest "):
        validate_manifest(
            release=False,
            manifest_path=manifest_path,
            extension=extension,
            release_record=release_record,
        )


def test_assistant_gate_rejects_missing_manifest_file(tmp_path: Path) -> None:
    manifest_path, extension, release_record = write_extension(tmp_path, missing_script=True)

    with pytest.raises(SystemExit, match="manifest references missing files: content.js"):
        validate_manifest(
            release=False,
            manifest_path=manifest_path,
            extension=extension,
            release_record=release_record,
        )


def test_assistant_release_gate_rejects_transient_label(tmp_path: Path) -> None:
    manifest_path, extension, release_record = write_extension(
        tmp_path,
        version_name="0.8.1 dev feature-a",
    )

    with pytest.raises(SystemExit, match="removing transient version_name"):
        validate_manifest(
            release=True,
            manifest_path=manifest_path,
            extension=extension,
            release_record=release_record,
        )


def test_assistant_release_gate_accepts_wrapped_recorded_version(tmp_path: Path) -> None:
    manifest_path, extension, release_record = write_extension(tmp_path)
    release_record.write_text(
        "The current\nextension version is 0.8.1.",
        encoding="utf-8",
    )

    manifest = validate_manifest(
        release=True,
        manifest_path=manifest_path,
        extension=extension,
        release_record=release_record,
    )

    assert manifest["version"] == "0.8.1"


def test_assistant_release_gate_compares_recorded_version(tmp_path: Path) -> None:
    manifest_path, extension, release_record = write_extension(tmp_path)
    release_record.write_text(
        "The current extension version is 0.8.0.",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="release record does not name the manifest version"):
        validate_manifest(
            release=True,
            manifest_path=manifest_path,
            extension=extension,
            release_record=release_record,
        )
