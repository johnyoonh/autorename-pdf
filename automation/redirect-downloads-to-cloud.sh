#!/usr/bin/env bash
set -euo pipefail

HOME_DIR="$HOME"
CLOUD_DRIVE="/Volumes/CloudDrive"
BACKUP_NAME="Downloads-local"
APPLY=0

usage() {
  cat <<'EOF'
Usage: bash automation/redirect-downloads-to-cloud.sh [options]

Safely redirect ~/Downloads to a Downloads directory on CloudDrive.
The existing local Downloads directory is renamed and preserved.

Options:
  --apply              Perform the changes. Without this flag, only print the plan.
  --home PATH          Home directory to operate on (default: $HOME).
  --cloud-drive PATH   CloudDrive mount point (default: /Volumes/CloudDrive).
  --backup-name NAME   Local backup directory name (default: Downloads-local).
  -h, --help           Show this help.
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

path_exists() {
  [[ -e "$1" || -L "$1" ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      shift
      ;;
    --home)
      [[ $# -ge 2 ]] || fail "--home requires a path"
      HOME_DIR="$2"
      shift 2
      ;;
    --cloud-drive)
      [[ $# -ge 2 ]] || fail "--cloud-drive requires a path"
      CLOUD_DRIVE="$2"
      shift 2
      ;;
    --backup-name)
      [[ $# -ge 2 ]] || fail "--backup-name requires a name"
      BACKUP_NAME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ -n "$BACKUP_NAME" ]] || fail "backup name cannot be empty"
[[ "$BACKUP_NAME" != */* ]] || fail "backup name must be a single directory name"
[[ -d "$HOME_DIR" ]] || fail "home directory does not exist: $HOME_DIR"
[[ -d "$CLOUD_DRIVE" ]] || fail "CloudDrive is not mounted at: $CLOUD_DRIVE"

SOURCE="$HOME_DIR/Downloads"
BACKUP="$HOME_DIR/$BACKUP_NAME"
TARGET="$CLOUD_DRIVE/Downloads"

if [[ -L "$SOURCE" ]]; then
  CURRENT_TARGET="$(readlink "$SOURCE")"
  if [[ "$CURRENT_TARGET" == "$TARGET" ]]; then
    printf 'Downloads is already linked to %s\n' "$TARGET"
    exit 0
  fi
  fail "Downloads is already a symlink to a different target: $CURRENT_TARGET"
fi

if path_exists "$SOURCE" && [[ ! -d "$SOURCE" ]]; then
  fail "Downloads exists but is not a directory: $SOURCE"
fi

if path_exists "$TARGET" && [[ ! -d "$TARGET" ]]; then
  fail "CloudDrive Downloads exists but is not a directory: $TARGET"
fi

if [[ -d "$SOURCE" ]] && path_exists "$BACKUP"; then
  fail "backup path already exists; refusing to overwrite it: $BACKUP"
fi

if [[ "$APPLY" -eq 0 ]]; then
  if [[ ! -d "$TARGET" ]]; then
    printf 'DRY RUN: create %s\n' "$TARGET"
  fi
  if [[ -d "$SOURCE" ]]; then
    printf 'DRY RUN: rename %s -> %s\n' "$SOURCE" "$BACKUP"
  fi
  printf 'DRY RUN: link %s -> %s\n' "$SOURCE" "$TARGET"
  printf 'Re-run with --apply to perform these changes.\n'
  exit 0
fi

if [[ ! -d "$TARGET" ]]; then
  mkdir -p "$TARGET"
  printf 'Created %s\n' "$TARGET"
fi

MOVED_SOURCE=0
if [[ -d "$SOURCE" ]]; then
  mv "$SOURCE" "$BACKUP"
  MOVED_SOURCE=1
  printf 'Renamed %s -> %s\n' "$SOURCE" "$BACKUP"
fi

if ! ln -s "$TARGET" "$SOURCE"; then
  if [[ "$MOVED_SOURCE" -eq 1 && ! -e "$SOURCE" && -d "$BACKUP" ]]; then
    if mv "$BACKUP" "$SOURCE"; then
      printf 'Restored %s after symlink creation failed.\n' "$SOURCE" >&2
    else
      printf 'Warning: could not restore %s from %s\n' "$SOURCE" "$BACKUP" >&2
    fi
  fi
  fail "could not create Downloads symlink"
fi

printf 'Linked %s -> %s\n' "$SOURCE" "$TARGET"
printf 'Existing local downloads remain in %s\n' "$BACKUP"
