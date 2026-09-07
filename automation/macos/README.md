# macOS browser downloads on CloudDrive

`configure_browser_downloads.py` creates `/Volumes/CloudDrive/Downloads` and points these browsers at it:

- Safari
- Google Chrome (all existing `Default` / `Profile *` profiles)
- Microsoft Edge (all existing `Default` / `Profile *` profiles)

Firefox is intentionally left unchanged.

The script refuses to fabricate `/Volumes/CloudDrive` when the microSD is not mounted, and it requires the targeted browsers to be quit before editing their settings. Existing Chromium profile preferences are preserved except for the download directory and the “ask where to save” toggle.

Run on the Mac after `CloudDrive` is mounted:

```bash
python automation/macos/configure_browser_downloads.py
```

A different destination can be supplied with `--download-dir`. Safari is updated through the macOS `defaults` preference store; Chrome and Edge are updated in each existing profile's `Preferences` JSON. Browser profile creation is deliberately not performed.

After running, launch Safari, Chrome, and Edge and confirm a small test download lands in `/Volumes/CloudDrive/Downloads`. Safari may require macOS folder-access approval for a removable volume on first use; that approval cannot be granted non-interactively.
