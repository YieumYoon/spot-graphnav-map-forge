#!/usr/bin/env python3
"""Verify that the active Python package remains read-only and Extension-supporting."""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "spot_graphnav_map_forge"
PYPROJECT = ROOT / "pyproject.toml"

ALLOWED_MODULES = frozenset(
    {
        "__init__",
        "__main__",
        "archive",
        "backup",
        "cli",
        "models",
        "reconnect",
        "site_elements",
        "topology",
        "wire",
    }
)
ALLOWED_PACKAGE_FILES = frozenset({"README.md"} | {f"{module}.py" for module in ALLOWED_MODULES})
ALLOWED_COMMANDS = frozenset({"inspect", "graph-baseline", "reconcile-graph"})
ARCHIVED_MODULES = frozenset(
    {
        "actions",
        "audit",
        "builder",
        "clone",
        "geometry",
        "planner",
        "remap",
        "validator",
        "walk_archive",
        "web",
        "web_assets",
    }
)
NETWORK_MODULES = frozenset(
    {
        "aiohttp",
        "ftplib",
        "http.client",
        "httpx",
        "requests",
        "socket",
        "smtplib",
        "subprocess",
        "urllib.request",
        "websockets",
    }
)
ARCHIVED_SYMBOLS = frozenset(
    {
        "build_clone",
        "clone_subgraph",
        "encode_fields",
        "export_walk_archive",
        "reconstruct_final_graph",
        "reissue_walk_recording",
        "rewrite_length_delimited_tokens",
        "serve_editor",
        "validate_bundle",
        "validate_walk_archive",
        "walk_target_opaque_profile",
        "build_workspace_payload",
        "clone_edge_snapshot",
        "clone_site_element",
        "clone_triggered_site_element",
        "clone_waypoint_snapshot",
        "create_plan",
        "create_preservation_audit",
        "deterministic_uuid4",
        "is_orbit_native_id",
        "orbit_native_id",
        "resolve_triggered_action_exclusions",
        "save_plan",
        "selection_dependency_waypoint_ids",
        "selection_only_edge_keys",
        "source_mission_ids",
    }
)


def _active_package_files(package: Path) -> set[str]:
    return {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }


def _network_imports(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    module = node.module or ""
    imports = [module]
    imports.extend(f"{module}.{alias.name}" if module else alias.name for alias in node.names)
    return imports


def _matches_module(name: str, blocked: str) -> bool:
    return name == blocked or name.startswith(f"{blocked}.")


def source_violations(package: Path) -> list[str]:
    violations: list[str] = []
    sources = sorted(package.rglob("*.py"))
    observed_files = _active_package_files(package)
    unexpected_files = sorted(observed_files - ALLOWED_PACKAGE_FILES)
    missing_files = sorted(ALLOWED_PACKAGE_FILES - observed_files)
    violations.extend(f"unexpected active package file: {name}" for name in unexpected_files)
    violations.extend(f"missing active package file: {name}" for name in missing_files)

    root_sources = [source for source in sources if source.parent == package]
    observed_modules = {source.stem for source in root_sources}
    unexpected = sorted(observed_modules - ALLOWED_MODULES)
    missing = sorted(ALLOWED_MODULES - observed_modules)
    violations.extend(f"unexpected active module: {name}.py" for name in unexpected)
    violations.extend(f"missing active module: {name}.py" for name in missing)

    commands: set[str] = set()
    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = _network_imports(node)
                if isinstance(node, ast.ImportFrom):
                    imported_module = node.module or ""
                    if any(part in ARCHIVED_MODULES for part in imported_module.split(".")):
                        violations.append(
                            f"{source.name}: archived module import: {imported_module}"
                        )
                for alias in node.names:
                    if alias.name in ARCHIVED_SYMBOLS:
                        violations.append(f"{source.name}: archived symbol import: {alias.name}")
            else:
                imported = []
            for name in imported:
                if any(_matches_module(name, blocked) for blocked in NETWORK_MODULES):
                    violations.append(f"{source.name}: forbidden network import: {name}")
                parts = name.split(".")
                if any(part in ARCHIVED_MODULES for part in parts):
                    violations.append(f"{source.name}: archived module import: {name}")

            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in ARCHIVED_SYMBOLS
            ):
                violations.append(f"{source.name}: archived function definition: {node.name}")
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            ):
                violations.append(f"{source.name}: dynamic import escape hatch")
            function = node.func
            if (
                isinstance(function, ast.Attribute)
                and function.attr == "add_parser"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                commands.add(node.args[0].value)

    if commands != ALLOWED_COMMANDS:
        violations.append(
            "CLI command allowlist mismatch: "
            f"expected {sorted(ALLOWED_COMMANDS)}, observed {sorted(commands)}"
        )
    return sorted(set(violations))


def metadata_violations(pyproject: Path) -> list[str]:
    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    scripts = metadata.get("project", {}).get("scripts", {})
    if scripts != {"spot-map-forge": "spot_graphnav_map_forge.cli:main"}:
        return [f"unexpected project scripts: {scripts}"]
    package_data = metadata.get("tool", {}).get("setuptools", {}).get("package-data", {})
    if package_data:
        return [f"unexpected active package data: {sorted(package_data)}"]
    return []


def collect_violations(
    package: Path = PACKAGE,
    pyproject: Path = PYPROJECT,
) -> list[str]:
    return sorted(set(source_violations(package) + metadata_violations(pyproject)))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--package", type=Path, default=PACKAGE)
    result.add_argument("--pyproject", type=Path, default=PYPROJECT)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    violations = collect_violations(args.package, args.pyproject)
    for violation in violations:
        print(f"ERROR: {violation}", file=sys.stderr)
    if violations:
        return 1
    print(
        "Active boundary check passed: "
        f"{len(ALLOWED_MODULES)} modules, {len(ALLOWED_COMMANDS)} read-only commands."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
