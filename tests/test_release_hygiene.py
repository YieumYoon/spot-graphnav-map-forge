import io
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_release_hygiene import scan_path  # noqa: E402

SCRIPT = ROOT / "scripts" / "check_release_hygiene.py"


def _run_check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_hygiene_accepts_synthetic_public_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Synthetic map fixture; connect only to 127.0.0.1.\n", encoding="utf-8"
    )

    result = _run_check(tmp_path)

    assert result.returncode == 0
    assert "passed" in result.stdout


def test_release_hygiene_rejects_private_paths_and_walks(tmp_path: Path) -> None:
    private_path = "/" + "Users/example/private/backup.tar"
    (tmp_path / "notes.txt").write_text(f"Local source: {private_path}\n", encoding="utf-8")
    (tmp_path / "generated.walk.zip").write_bytes(b"not an archive")

    result = _run_check(tmp_path)

    assert result.returncode == 1
    assert "absolute home-directory path" in result.stderr
    assert "backup, Walk, or credential artifact" in result.stderr


def test_release_hygiene_scans_archive_members_and_absolute_symlinks(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "synthetic.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("package/.env", "synthetic environment fixture")
        link_member = zipfile.ZipInfo("package/absolute-link")
        link_member.create_system = 3
        link_member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link_member, "/private/synthetic-target")

    source_distribution = tmp_path / "synthetic.tar.gz"
    private_address = ".".join(("10", "1", "2", "3"))
    payload = f"internal endpoint: {private_address}\n".encode()
    with tarfile.open(source_distribution, "w:gz") as archive:
        member = tarfile.TarInfo("synthetic/notes.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
        link_member = tarfile.TarInfo("synthetic/absolute-link")
        link_member.type = tarfile.SYMTYPE
        link_member.linkname = "/private/synthetic-target"
        archive.addfile(link_member)

    link = tmp_path / "absolute-link"
    link.symlink_to("/private/synthetic-target")

    wheel_findings = scan_path(wheel)
    source_findings = scan_path(source_distribution)
    link_result = _run_check(link)

    assert any(finding.reason == "environment file" for finding in wheel_findings)
    assert any(finding.reason == "absolute symlink target" for finding in wheel_findings)
    assert any(finding.reason == "private IPv4 address" for finding in source_findings)
    assert any(finding.reason == "absolute symlink target" for finding in source_findings)
    assert link_result.returncode == 1
    assert "absolute symlink target" in link_result.stderr
