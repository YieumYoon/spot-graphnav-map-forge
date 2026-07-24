from __future__ import annotations

import re
import tomllib
from pathlib import Path

from spot_graphnav_map_forge.cli import _parser

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_GUIDES = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "compatibility.md",
    ROOT / "docs" / "legacy" / "offline-clone.md",
    ROOT / "docs" / "privacy.md",
    ROOT / "docs" / "workflows" / "orbit-native-map-split.md",
    ROOT / "docs" / "workflows" / "orbit-native-operation-journal-template.md",
    ROOT / "docs" / "orbit-site-map-editor-assistant-feature-research.md",
    ROOT / "docs" / "orbit-site-map-editor-qualification.md",
    ROOT / "extension" / "README.md",
    ROOT / "extension" / "orbit-graph-repair" / "README.md",
    ROOT / "extension" / "orbit-site-map-editor" / "README.md",
    ROOT / "src" / "spot_graphnav_map_forge" / "README.md",
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_public_entrypoint_is_extension_first_and_archive_is_not_a_workflow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.index("Orbit Site Map Editor") < readme.index("Archived offline clone research")
    assert "never presses **Save**" in readme
    assert "archive/offline-clone-2026-07" in readme
    assert "uv run spot-map-forge build" not in readme
    assert "uv run spot-map-forge export-walk" not in readme

    documentation_map = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "## Orbit Site Map Editor" in documentation_map
    assert "## Archived research" in documentation_map
    assert "not shipped or supported" in documentation_map


def test_public_document_links_resolve() -> None:
    for guide in PUBLIC_GUIDES:
        text = guide.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text or path_text.startswith("mailto:"):
                continue
            resolved = (guide.parent / path_text).resolve()
            assert resolved.exists(), f"{guide.relative_to(ROOT)} -> {target}"


def test_cli_and_package_metadata_are_read_only_extension_support() -> None:
    help_text = " ".join(_parser().format_help().split())
    assert "Read-only Orbit backup inventory" in help_text
    assert "never uploads, imports, remaps, or mutates Orbit data" in help_text
    assert "offline clone workflow" not in help_text

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["version"] == "0.2.0a1"
    assert metadata["project"]["description"] == (
        "Orbit Site Map Chrome extensions with read-only backup baselines"
    )


def test_active_documentation_does_not_expose_archived_commands() -> None:
    archived_commands = (
        "prepare",
        "plan",
        "audit",
        "build",
        "validate",
        "export-walk",
        "reissue-walk",
        "validate-walk",
        "serve",
    )
    active_guides = [
        guide for guide in PUBLIC_GUIDES if guide != ROOT / "docs" / "legacy" / "offline-clone.md"
    ]
    for guide in active_guides:
        text = guide.read_text(encoding="utf-8")
        for command in archived_commands:
            assert f"spot-map-forge {command}" not in text, (
                f"{guide.relative_to(ROOT)} exposes archived command {command}"
            )
