from __future__ import annotations

import re
import tomllib
from pathlib import Path

from spot_graphnav_map_forge.cli import _parser

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_GUIDES = (
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "workflows" / "orbit-native-map-split.md",
    ROOT / "docs" / "workflows" / "orbit-native-operation-journal-template.md",
    ROOT / "docs" / "workflows" / "offline-map-clone.md",
    ROOT / "extension" / "README.md",
    ROOT / "extension" / "orbit-graph-repair" / "README.md",
    ROOT / "src" / "spot_graphnav_map_forge" / "README.md",
)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_recommended_and_experimental_workflows_are_separate() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    native_link = "docs/workflows/orbit-native-map-split.md"
    clone_link = "docs/workflows/offline-map-clone.md"

    assert native_link in readme
    assert clone_link in readme
    assert readme.index(native_link) < readme.index(clone_link)
    assert "recommended; verified on Orbit 5.1.8" in readme
    assert "experimental" in readme
    assert "never presses **Save**" in readme

    documentation_map = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "## Recommended same-instance workflow" in documentation_map
    assert "## Experimental offline clone workflow" in documentation_map


def test_public_workflow_document_links_resolve() -> None:
    for guide in PUBLIC_GUIDES:
        text = guide.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(text):
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text or path_text.startswith("mailto:"):
                continue
            resolved = (guide.parent / path_text).resolve()
            assert resolved.exists(), f"{guide.relative_to(ROOT)} -> {target}"


def test_cli_and_package_metadata_name_both_workflows() -> None:
    help_text = " ".join(_parser().format_help().split())
    assert "Recommended same-instance workflow" in help_text
    assert "Experimental offline clone workflow" in help_text

    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    description = metadata["project"]["description"]
    assert "Orbit-assisted recording splits" in description
    assert "experimental offline cloning" in description
