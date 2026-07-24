from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_GUIDES = tuple(
    sorted(
        {
            ROOT / "README.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "SECURITY.md",
            ROOT / "src" / "spot_graphnav_map_forge" / "README.md",
            *(ROOT / "docs").rglob("*.md"),
            *(ROOT / "extension").rglob("README.md"),
        }
    )
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_public_entrypoint_links_current_components_and_archive_summary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documentation_map = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    readme_targets = set(MARKDOWN_LINK.findall(readme))
    documentation_targets = set(MARKDOWN_LINK.findall(documentation_map))

    assert "extension/orbit-site-map-editor/README.md" in readme_targets
    assert "extension/orbit-graph-repair/README.md" in readme_targets
    assert "docs/legacy/offline-clone.md" in readme_targets
    assert "legacy/offline-clone.md" in documentation_targets


def test_public_document_links_resolve() -> None:
    for guide in PUBLIC_GUIDES:
        text = guide.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text or path_text.startswith("mailto:"):
                continue
            resolved = (guide.parent / path_text).resolve()
            assert resolved.exists(), f"{guide.relative_to(ROOT)} -> {target}"


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
