"""Shared Chrome extension version validation."""

from __future__ import annotations

import re

VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")


def validate_chrome_version(value: object) -> str:
    """Return a valid one-to-four-component Chrome extension version."""
    if not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value):
        raise ValueError("version must contain one to four dot-separated integers")
    parts = value.split(".")
    if all(int(part) == 0 for part in parts):
        raise ValueError("version cannot be all zero")
    if any(len(part) > 1 and part.startswith("0") for part in parts):
        raise ValueError("non-zero version components cannot start with zero")
    if any(int(part) > 65535 for part in parts):
        raise ValueError("version components must be at most 65535")
    return value
