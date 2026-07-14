"""Read-only access to a backup tar archive."""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from pathlib import Path


class BackupArchive:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._tar: tarfile.TarFile | None = None
        self._members: dict[str, tarfile.TarInfo] = {}

    def __enter__(self) -> BackupArchive:
        self._tar = tarfile.open(self.path, mode="r:*")
        self._members = {member.name: member for member in self._tar.getmembers()}
        return self

    def __exit__(self, *_: object) -> None:
        if self._tar is not None:
            self._tar.close()
        self._tar = None
        self._members = {}

    def names(self, prefix: str = "") -> Iterator[str]:
        for name in self._members:
            if name.startswith(prefix) and self._members[name].isfile():
                yield name

    def exists(self, name: str) -> bool:
        member = self._members.get(name)
        return member is not None and member.isfile()

    def read(self, name: str) -> bytes:
        if self._tar is None:
            raise RuntimeError("BackupArchive must be used as a context manager")
        member = self._members.get(name)
        if member is None or not member.isfile():
            raise FileNotFoundError(name)
        stream = self._tar.extractfile(member)
        if stream is None:
            raise FileNotFoundError(name)
        return stream.read()

    def basename_index(self, prefix: str) -> dict[str, str]:
        return {name.rsplit("/", 1)[-1]: name for name in self.names(prefix)}
