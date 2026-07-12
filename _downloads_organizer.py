"""Conservative organizer for files aging out of Downloads."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


PARTIAL_SUFFIXES = {".crdownload", ".download", ".part"}

EXTENSION_CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".svg", ".dng"},
    "Video": {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp"},
    "Audio": {".mp3", ".m4a", ".wav", ".aac", ".flac"},
    "Archives": {".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar"},
    "Installers": {".dmg", ".pkg", ".msi", ".exe", ".xpi"},
    "Books": {".epub", ".mobi", ".azw", ".azw3"},
    "Spreadsheets": {".xlsx", ".xls", ".csv", ".tsv", ".numbers"},
    "General": {".doc", ".docx", ".rtf", ".txt", ".md", ".pages"},
}

PDF_CATEGORY_KEYWORDS = {
    "Financial": {"invoice", "receipt", "tax", "statement", "financial", "bank", "insurance"},
    "Medical": {"medical", "health", "laboratory", "lab", "prescription", "patient"},
    "Education": {"education", "lecture", "exam", "course", "syllabus", "assignment", "school"},
    "Employment": {"resume", "employment", "offer", "payroll", "benefits"},
}


@dataclass
class OrganizeResult:
    source: str
    destination: str | None
    status: str
    category: str | None = None
    reason: str | None = None
    renamed_to: str | None = None


def collect_eligible_files(source: Path, older_than_days: int, now: dt.datetime | None = None) -> list[Path]:
    """Return safe, top-level files older than the configured threshold."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now.timestamp() - older_than_days * 86400
    eligible: list[Path] = []
    for path in source.iterdir():
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        if path.name.startswith("~$") or path.suffix.lower() in PARTIAL_SUFFIXES:
            continue
        if path.stat().st_mtime <= cutoff:
            eligible.append(path)
    return sorted(eligible, key=lambda p: (p.stat().st_mtime, p.name.lower()))


def classify_extension(path: Path) -> str:
    suffix = path.suffix.lower()
    for category, extensions in EXTENSION_CATEGORIES.items():
        if suffix in extensions:
            return category
    return "Review"


def classify_pdf(doc_type: str | None) -> str:
    if not doc_type:
        return "Review"
    words = doc_type.casefold()
    for category, keywords in PDF_CATEGORY_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", words) for keyword in keywords):
            return category
    return "General"


def destination_for(root: Path, category: str, path: Path, timestamp_source: Path | None = None) -> Path:
    timestamp_source = timestamp_source or path
    year = dt.datetime.fromtimestamp(timestamp_source.stat().st_mtime).strftime("%Y")
    if category in {"Images", "Video", "Audio"}:
        return root / "Media" / category / year / path.name
    if category in {"Financial", "Medical", "Education", "Employment", "General", "Spreadsheets"}:
        return root / "Documents" / category / year / path.name
    if category == "Review":
        return root / "Review" / year / path.name
    return root / category / year / path.name


def organize_files(
    source: Path,
    destination: Path,
    older_than_days: int = 30,
    apply: bool = False,
    pdf_renamer: Callable[[Path, bool], tuple[Path, str | None, str | None]] | None = None,
    now: dt.datetime | None = None,
) -> list[OrganizeResult]:
    """Plan or apply renames and moves. PDF renamer returns path, doc type, error."""
    results: list[OrganizeResult] = []
    for original in collect_eligible_files(source, older_than_days, now=now):
        working = original
        renamed_to = None
        error = None
        doc_type = None
        if original.suffix.lower() == ".pdf" and pdf_renamer:
            working, doc_type, error = pdf_renamer(original, apply)
            if working.name != original.name:
                renamed_to = working.name
        category = classify_pdf(doc_type) if original.suffix.lower() == ".pdf" else classify_extension(original)
        if error:
            category = "Review"

        target = destination_for(destination, category, working, timestamp_source=original)
        if target.exists() and target.resolve() != working.resolve():
            results.append(OrganizeResult(str(original), None, "review", "Review", "destination collision", renamed_to))
            continue

        status = "planned"
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(working), str(target))
            status = "moved"
        results.append(OrganizeResult(str(original), str(target), status, category, error, renamed_to))
    return results


def append_audit_log(path: Path, results: Iterable[OrganizeResult], apply: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps({"timestamp": stamp, "apply": apply, **asdict(result)}, ensure_ascii=False) + "\n")
