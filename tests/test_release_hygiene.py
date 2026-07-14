import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_release_hygiene.py"


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
