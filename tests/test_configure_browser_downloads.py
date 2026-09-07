import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).parents[1]
    / "automation"
    / "macos"
    / "configure_browser_downloads.py"
)
SPEC = importlib.util.spec_from_file_location("configure_browser_downloads", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ConfigureBrowserDownloadsTests(unittest.TestCase):
    def test_external_volume_root_only_matches_volumes_paths(self):
        self.assertEqual(
            module._external_volume_root(Path("/Volumes/CloudDrive/Downloads")),
            Path("/Volumes/CloudDrive"),
        )
        self.assertIsNone(module._external_volume_root(Path("/tmp/Downloads")))

    def test_profile_preference_files_only_targets_user_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Chrome"
            for profile in ("Default", "Profile 1", "Guest Profile", "System Profile"):
                directory = root / profile
                directory.mkdir(parents=True)
                (directory / "Preferences").write_text("{}", encoding="utf-8")

            self.assertEqual(
                module._profile_preference_files(root),
                [
                    root / "Default" / "Preferences",
                    root / "Profile 1" / "Preferences",
                ],
            )

    def test_update_chromium_preferences_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            preferences = Path(tmp) / "Preferences"
            preferences.write_text(
                json.dumps(
                    {
                        "download": {
                            "extensions_to_open": "pdf",
                            "prompt_for_download": True,
                        },
                        "homepage": "https://example.com",
                    }
                ),
                encoding="utf-8",
            )

            target = Path("/Volumes/CloudDrive/Downloads")
            self.assertTrue(module.update_chromium_preferences(preferences, target))
            data = json.loads(preferences.read_text(encoding="utf-8"))

            self.assertEqual(data["download"]["default_directory"], str(target))
            self.assertIs(data["download"]["prompt_for_download"], False)
            self.assertEqual(data["download"]["extensions_to_open"], "pdf")
            self.assertEqual(data["homepage"], "https://example.com")
            self.assertFalse(module.update_chromium_preferences(preferences, target))

    def test_ensure_download_directory_refuses_unmounted_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_volume = Path(tmp) / "Volumes" / "CloudDrive"
            fake_volume.mkdir(parents=True)
            target = fake_volume / "Downloads"

            with (
                mock.patch.object(
                    module,
                    "_external_volume_root",
                    return_value=fake_volume,
                ),
                mock.patch.object(module.os.path, "ismount", return_value=False),
            ):
                with self.assertRaisesRegex(
                    module.ConfigurationError, "not a mounted volume"
                ):
                    module.ensure_download_directory(target)

            self.assertFalse(target.exists())

    def test_firefox_is_not_a_target(self):
        self.assertNotIn("Firefox", module.TARGET_BROWSERS)
        self.assertTrue(
            all(
                "Mozilla" not in str(path)
                for path in module.CHROMIUM_PROFILE_ROOTS.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
