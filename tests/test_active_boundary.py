from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_active_boundary import (  # noqa: E402
    ALLOWED_PACKAGE_FILES,
    collect_violations,
    source_violations,
)


def test_active_package_boundary_is_allowlisted_and_read_only() -> None:
    assert collect_violations() == []


def test_boundary_checker_rejects_nested_assets_and_import_escape_hatches(
    tmp_path: Path,
) -> None:
    package = tmp_path / "spot_graphnav_map_forge"
    for relative in ALLOWED_PACKAGE_FILES:
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "from urllib import request\n"
        "plugin = __import__('legacy_plugin')\n"
        "def build_workspace_payload():\n"
        "    return request\n",
        encoding="utf-8",
    )
    nested_asset = package / "web_assets" / "app.js"
    nested_asset.parent.mkdir()
    nested_asset.write_text("legacy clone editor", encoding="utf-8")

    violations = source_violations(package)

    assert "unexpected active package file: web_assets/app.js" in violations
    assert "cli.py: forbidden network import: urllib.request" in violations
    assert "cli.py: dynamic import escape hatch" in violations
    assert "cli.py: archived function definition: build_workspace_payload" in violations
