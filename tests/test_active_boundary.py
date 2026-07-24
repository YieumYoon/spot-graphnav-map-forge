from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_active_boundary import (  # noqa: E402
    ALLOWED_COMMANDS,
    ALLOWED_MODULES,
    collect_violations,
)
from spot_graphnav_map_forge.cli import _parser  # noqa: E402


def test_active_package_boundary_is_allowlisted_and_read_only() -> None:
    assert collect_violations() == []


def test_cli_exposes_only_read_only_support_commands() -> None:
    parser = _parser()
    subparsers = next(
        action
        for action in parser._actions  # noqa: SLF001 - argparse has no public choices accessor
        if action.__class__.__name__ == "_SubParsersAction"
    )

    assert set(subparsers.choices) == ALLOWED_COMMANDS


def test_boundary_checker_defines_each_active_module_explicitly() -> None:
    observed = {path.stem for path in (ROOT / "src" / "spot_graphnav_map_forge").glob("*.py")}

    assert observed == ALLOWED_MODULES


def test_active_sources_have_no_dynamic_import_escape_hatch() -> None:
    for source in (ROOT / "src" / "spot_graphnav_map_forge").glob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "__import__")
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
            )
        ]
        assert not calls, source.name
