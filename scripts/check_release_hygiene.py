#!/usr/bin/env python3
"""Reject common private or generated artifacts before a public release."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

MAX_TEXT_BYTES = 8 * 1024 * 1024

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
    }
)

BLOCKED_DIRECTORIES = frozenset(
    {
        ".playwright-cli",
        "build",
        "dist",
        "output",
        "workspace",
    }
)

BLOCKED_FILE_NAMES = frozenset(
    {
        ".DS_Store",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
)

BLOCKED_SUFFIXES = (
    ".key",
    ".p12",
    ".pem",
    ".pfx",
    ".tar",
    ".tar.gz",
    ".walk",
    ".walk.zip",
)

TEXT_PATTERNS = (
    (
        "absolute home-directory path",
        re.compile(r"(?:(?:/Users|/home)/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)"),
    ),
    (
        "email address",
        re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    ),
    (
        "private IPv4 address",
        re.compile(
            r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
            r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
        ),
    ),
    (
        "credential-like assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b"
            r"\s*[:=]\s*[\"']?[^\s\"'{}<>]{8,}"
        ),
    ),
    ("private key material", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
)


@dataclass(frozen=True, order=True)
class Finding:
    location: str
    reason: str


def _path_reason(parts: tuple[str, ...]) -> str | None:
    for part in parts[:-1]:
        if part in BLOCKED_DIRECTORIES:
            return f"generated/private directory: {part}"

    name = parts[-1] if parts else ""
    lowered = name.casefold()
    if name in BLOCKED_FILE_NAMES:
        return "local/private file"
    if lowered == ".env" or (lowered.startswith(".env.") and lowered != ".env.example"):
        return "environment file"
    if lowered.endswith(BLOCKED_SUFFIXES):
        return "backup, Walk, or credential artifact"
    return None


def _decode_text(stream: BinaryIO, size: int) -> str | None:
    if size > MAX_TEXT_BYTES:
        return None
    payload = stream.read(MAX_TEXT_BYTES + 1)
    if len(payload) > MAX_TEXT_BYTES or b"\0" in payload:
        return None
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _scan_text(location: str, text: str) -> Iterable[Finding]:
    for reason, pattern in TEXT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        line = text.count("\n", 0, match.start()) + 1
        yield Finding(f"{location}:{line}", reason)


def _scan_file(path: Path, location: str) -> Iterable[Finding]:
    if path.is_symlink():
        target = os.readlink(path)
        if Path(target).is_absolute():
            yield Finding(location, "absolute symlink target")
        return
    try:
        with path.open("rb") as stream:
            text = _decode_text(stream, path.stat().st_size)
    except OSError as error:
        yield Finding(location, f"could not inspect file: {error}")
        return
    if text is not None:
        yield from _scan_text(location, text)


def scan_tree(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for directory, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in IGNORED_DIRECTORIES and not name.endswith(".egg-info")
        )
        directory_path = Path(directory)
        for name in sorted(file_names):
            path = directory_path / name
            relative = path.relative_to(root)
            parts = relative.parts
            reason = _path_reason(parts)
            if reason is not None:
                findings.append(Finding(relative.as_posix(), reason))
                continue
            findings.extend(_scan_file(path, relative.as_posix()))
    return sorted(set(findings))


def _archive_location(archive_name: str, member_name: str) -> str:
    return f"{archive_name}!/{member_name}"


def scan_zip(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_name = member.filename
            location = _archive_location(path.name, member_name)
            reason = _path_reason(PurePosixPath(member_name).parts)
            if reason is not None:
                findings.append(Finding(location, reason))
                continue
            if member.file_size > MAX_TEXT_BYTES:
                continue
            with archive.open(member) as stream:
                text = _decode_text(stream, member.file_size)
            if text is not None:
                findings.extend(_scan_text(location, text))
    return sorted(set(findings))


def scan_tar(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    with tarfile.open(path, "r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            member_name = member.name
            location = _archive_location(path.name, member_name)
            reason = _path_reason(PurePosixPath(member_name).parts)
            if reason is not None:
                findings.append(Finding(location, reason))
                continue
            if member.size > MAX_TEXT_BYTES:
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            with stream:
                text = _decode_text(stream, member.size)
            if text is not None:
                findings.extend(_scan_text(location, text))
    return sorted(set(findings))


def scan_path(path: Path) -> list[Finding]:
    if path.is_dir():
        return scan_tree(path)
    if zipfile.is_zipfile(path):
        return scan_zip(path)
    if tarfile.is_tarfile(path):
        return scan_tar(path)
    return list(_scan_file(path, path.name))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        metavar="PATH",
        nargs="*",
        type=Path,
        default=[Path.cwd()],
        help="repository, wheel, sdist, or file to inspect (default: current directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    findings: list[Finding] = []
    missing: list[Path] = []
    for path in args.paths:
        if not path.exists():
            missing.append(path)
            continue
        findings.extend(scan_path(path))

    for path in missing:
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
    for finding in sorted(set(findings)):
        print(f"ERROR: {finding.location}: {finding.reason}", file=sys.stderr)
    if missing or findings:
        return 1

    print(f"Release hygiene check passed for {len(args.paths)} path(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
