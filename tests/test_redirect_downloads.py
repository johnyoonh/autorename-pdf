import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "automation" / "redirect-downloads-to-cloud.sh"


def run_script(home: Path, cloud_drive: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(SCRIPT), "--home", str(home), "--cloud-drive", str(cloud_drive), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_dry_run_does_not_mutate(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cloud_drive = tmp_path / "CloudDrive"
    downloads = home / "Downloads"
    home.mkdir()
    cloud_drive.mkdir()
    downloads.mkdir()
    (downloads / "keep.txt").write_text("keep", encoding="utf-8")

    result = run_script(home, cloud_drive)

    assert result.returncode == 0
    assert "DRY RUN: rename" in result.stdout
    assert "DRY RUN: link" in result.stdout
    assert downloads.is_dir()
    assert not downloads.is_symlink()
    assert not (home / "Downloads-local").exists()
    assert not (cloud_drive / "Downloads").exists()


def test_apply_preserves_local_downloads_and_creates_symlink(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cloud_drive = tmp_path / "CloudDrive"
    downloads = home / "Downloads"
    home.mkdir()
    cloud_drive.mkdir()
    downloads.mkdir()
    (downloads / "keep.txt").write_text("keep", encoding="utf-8")

    result = run_script(home, cloud_drive, "--apply")

    assert result.returncode == 0, result.stderr
    backup = home / "Downloads-local"
    target = cloud_drive / "Downloads"
    assert backup.is_dir()
    assert (backup / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert target.is_dir()
    assert downloads.is_symlink()
    assert os.readlink(downloads) == str(target)


def test_apply_is_idempotent_for_expected_symlink(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cloud_drive = tmp_path / "CloudDrive"
    target = cloud_drive / "Downloads"
    home.mkdir()
    cloud_drive.mkdir()
    target.mkdir()
    (home / "Downloads").symlink_to(target)

    result = run_script(home, cloud_drive, "--apply")

    assert result.returncode == 0
    assert "already linked" in result.stdout
    assert (home / "Downloads").is_symlink()


def test_refuses_to_overwrite_existing_backup(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cloud_drive = tmp_path / "CloudDrive"
    home.mkdir()
    cloud_drive.mkdir()
    downloads = home / "Downloads"
    downloads.mkdir()
    backup = home / "Downloads-local"
    backup.mkdir()

    result = run_script(home, cloud_drive, "--apply")

    assert result.returncode == 1
    assert "refusing to overwrite" in result.stderr
    assert downloads.is_dir()
    assert not downloads.is_symlink()
    assert backup.is_dir()
    assert not (cloud_drive / "Downloads").exists()


def test_refuses_conflicting_downloads_symlink(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cloud_drive = tmp_path / "CloudDrive"
    other_target = tmp_path / "OtherDownloads"
    home.mkdir()
    cloud_drive.mkdir()
    other_target.mkdir()
    downloads = home / "Downloads"
    downloads.symlink_to(other_target)

    result = run_script(home, cloud_drive, "--apply")

    assert result.returncode == 1
    assert "different target" in result.stderr
    assert os.readlink(downloads) == str(other_target)
    assert not (cloud_drive / "Downloads").exists()
