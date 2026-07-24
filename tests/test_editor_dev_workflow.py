from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.chrome_version import validate_chrome_version  # noqa: E402

SET_BUILD = ROOT / "scripts" / "set_editor_build.py"
SKILL = ROOT / ".agents" / "skills" / "orbit-extension-dev"


def run_build(manifest: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SET_BUILD), "--manifest", str(manifest), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_editor_build_labels_are_transient_and_release_versions_are_valid(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"manifest_version": 3, "name": "Editor", "version": "0.5.0"}),
        encoding="utf-8",
    )

    dev = run_build(manifest, "dev", "--label", "0.5.0 dev feature-a")
    assert dev.returncode == 0
    assert json.loads(manifest.read_text(encoding="utf-8"))["version_name"] == (
        "0.5.0 dev feature-a"
    )

    restore = run_build(manifest, "release", "--keep-version")
    assert restore.returncode == 0
    restored = json.loads(manifest.read_text(encoding="utf-8"))
    assert restored["version"] == "0.5.0"
    assert "version_name" not in restored

    release = run_build(manifest, "release", "0.6.0")
    assert release.returncode == 0
    assert json.loads(manifest.read_text(encoding="utf-8"))["version"] == "0.6.0"


def test_editor_build_rejects_invalid_release_without_mutating_manifest(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    original = {"manifest_version": 3, "name": "Editor", "version": "0.5.0"}
    manifest.write_text(json.dumps(original), encoding="utf-8")

    result = run_build(manifest, "release", "0.06.0")

    assert result.returncode != 0
    assert json.loads(manifest.read_text(encoding="utf-8")) == original


def test_shared_chrome_version_contract_covers_manifest_limits() -> None:
    assert validate_chrome_version("1") == "1"
    assert validate_chrome_version("1.2.3.65535") == "1.2.3.65535"

    for invalid in (None, "", "0", "1.2.3.4.5", "1.02", "1.65536", "1-beta"):
        with pytest.raises(ValueError):
            validate_chrome_version(invalid)


def test_repo_skill_encodes_reload_order_and_single_browser_ownership() -> None:
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    live = (SKILL / "references" / "live-qualification.md").read_text(encoding="utf-8")
    parallel = (SKILL / "references" / "parallel-development.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "name: orbit-extension-dev" in skill
    assert "extension reload, Orbit reload" in skill
    assert live.index("chrome://extensions") < live.index("Return to the existing Orbit")
    assert "never press **Save**" in live
    assert "one Git worktree" in parallel
    assert "only one agent may reload or operate Orbit" in agents
