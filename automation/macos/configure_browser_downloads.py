#!/usr/bin/env python3
"""Point Safari, Chrome, and Edge downloads at an external macOS volume.

Firefox is intentionally not touched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

DEFAULT_DOWNLOAD_DIR = Path("/Volumes/CloudDrive/Downloads")
TARGET_BROWSERS = ("Safari", "Google Chrome", "Microsoft Edge")
CHROMIUM_PROFILE_ROOTS = {
    "Google Chrome": Path("Library/Application Support/Google/Chrome"),
    "Microsoft Edge": Path("Library/Application Support/Microsoft Edge"),
}


class ConfigurationError(RuntimeError):
    """Raised when it is unsafe to change browser download settings."""


def _run(
    args: list[str], *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _browser_is_running(name: str) -> bool:
    result = subprocess.run(
        ["pgrep", "-x", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _external_volume_root(download_dir: Path) -> Path | None:
    absolute = download_dir.expanduser().absolute()
    parts = absolute.parts
    if len(parts) >= 3 and parts[:2] == ("/", "Volumes"):
        return Path("/Volumes") / parts[2]
    return None


def ensure_download_directory(download_dir: Path) -> None:
    """Create the download directory without accidentally fabricating a volume path."""
    download_dir = download_dir.expanduser().absolute()
    volume_root = _external_volume_root(download_dir)
    if volume_root is not None:
        if not volume_root.exists():
            raise ConfigurationError(
                f"External volume is not mounted: {volume_root}. "
                "Mount it before running this command."
            )
        if not os.path.ismount(volume_root):
            raise ConfigurationError(
                f"Refusing to create downloads under {volume_root}: "
                "the path exists but is not a mounted volume."
            )

    download_dir.mkdir(parents=True, exist_ok=True)
    if not download_dir.is_dir():
        raise ConfigurationError(f"Download path is not a directory: {download_dir}")


def _profile_preference_files(profile_root: Path) -> list[Path]:
    if not profile_root.is_dir():
        return []

    profiles = []
    for child in profile_root.iterdir():
        if child.name == "Default" or child.name.startswith("Profile "):
            preferences = child / "Preferences"
            if preferences.is_file():
                profiles.append(preferences)
    return sorted(profiles)


def _write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())

    try:
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def update_chromium_preferences(preferences: Path, download_dir: Path) -> bool:
    """Update one Chromium profile. Returns True when the file changed."""
    try:
        data = json.loads(preferences.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read Chromium preferences: {preferences}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(f"Unexpected Chromium preference format: {preferences}")

    download = data.setdefault("download", {})
    if not isinstance(download, dict):
        raise ConfigurationError(
            f"Unexpected download preference format in {preferences}"
        )

    desired_directory = str(download_dir.expanduser().absolute())
    changed = (
        download.get("default_directory") != desired_directory
        or download.get("prompt_for_download") is not False
    )
    download["default_directory"] = desired_directory
    download["prompt_for_download"] = False

    if changed:
        _write_json_atomically(preferences, data)
    return changed


def configure_chromium_browser(
    browser: str, *, home: Path, download_dir: Path
) -> tuple[int, int]:
    root = home / CHROMIUM_PROFILE_ROOTS[browser]
    preference_files = _profile_preference_files(root)
    changed = 0
    for preferences in preference_files:
        changed += int(update_chromium_preferences(preferences, download_dir))
    return changed, len(preference_files)


def configure_safari(download_dir: Path) -> None:
    desired_directory = str(download_dir.expanduser().absolute())
    _run(
        [
            "defaults",
            "write",
            "com.apple.Safari",
            "DownloadsPath",
            "-string",
            desired_directory,
        ]
    )

    result = _run(
        ["defaults", "read", "com.apple.Safari", "DownloadsPath"],
        capture_output=True,
    )
    if result.stdout.strip() != desired_directory:
        raise ConfigurationError("Safari did not retain the requested download path")


def configure(download_dir: Path, *, home: Path) -> list[str]:
    if sys.platform != "darwin":
        raise ConfigurationError("This utility only supports macOS")

    running = [name for name in TARGET_BROWSERS if _browser_is_running(name)]
    if running:
        raise ConfigurationError(
            "Quit these browsers before changing their download settings: "
            + ", ".join(running)
        )

    ensure_download_directory(download_dir)
    messages = [f"Download directory ready: {download_dir.expanduser().absolute()}"]

    if shutil.which("defaults") is None:
        raise ConfigurationError("macOS 'defaults' command is unavailable")
    configure_safari(download_dir)
    messages.append("Safari: configured")

    for browser in CHROMIUM_PROFILE_ROOTS:
        changed, profiles = configure_chromium_browser(
            browser, home=home, download_dir=download_dir
        )
        if profiles == 0:
            messages.append(f"{browser}: no existing profile found; skipped")
        else:
            messages.append(
                f"{browser}: configured {profiles} profile(s), changed {changed}"
            )

    messages.append("Firefox: intentionally unchanged")
    return messages


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a download directory and configure Safari, Chrome, and Edge "
            "to use it. Firefox is intentionally excluded."
        )
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"target directory (default: {DEFAULT_DOWNLOAD_DIR})",
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        messages = configure(args.download_dir, home=args.home.expanduser().absolute())
    except (ConfigurationError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for message in messages:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
