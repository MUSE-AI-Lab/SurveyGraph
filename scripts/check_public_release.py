#!/usr/bin/env python3
"""Fail fast when release files contain credentials or private state."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CANDIDATE_ROOTS = {
    ".github",
    "src",
    "mekg",
    "evaluation",
    "experiments",
    "frontend",
    "tasks",
    "tests",
    "docs",
    "resources",
    "scripts",
    "OpenAlex",
}
PUBLIC_CANDIDATE_FILES = {
    ".gitattributes",
    ".env.example",
    ".gitignore",
    "README.md",
    "README_zh.md",
    "LICENSE",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "requirements.txt",
    "pytest.ini",
    "run_sg_endtoend.py",
    "run.sh",
}
PUBLIC_TOOL_FILES = {
    "tools/check_expense.py",
    "tools/remove_unsuccessful.py",
    "tools/remve_log.py",
    "tools/test_crawler.py",
    "tools/test_multimodal.py",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(?:api[_-]?key|token|password|secret)\s*[:=]\s*['\"][A-Za-z0-9_-]{24,}['\"]"),
    re.compile(r"(?im)^\s*(?:api[_-]?key|token|password|secret)\s*=\s*[A-Za-z0-9_-]{24,}\s*$"),
)
PRIVATE_PATH_PATTERNS = (
    "*.env",
    "*.local.json",
    "*.local.yaml",
    "*.local.yml",
    "*.db",
    "*.zip",
    "*.tar.gz",
    "*.pdf",
    "paperreview*",
    "refer/*",
    "paper/*",
    "*rebuttal*",
    "*submission*",
)
TEXT_SUFFIXES = {
    ".c",
    ".cfg",
    ".cmd",
    ".cpp",
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".tex",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def repository_candidate_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = {
        item.decode("utf-8", "surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }
    return sorted(path for path in paths if is_public_candidate(path))


def is_public_candidate(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    root, _, _ = normalized.partition("/")
    if normalized in PUBLIC_CANDIDATE_FILES:
        return True
    if root == "tools":
        return normalized in PUBLIC_TOOL_FILES
    if root not in PUBLIC_CANDIDATE_ROOTS:
        return False
    if normalized.startswith("docs/superpowers/"):
        return False
    if normalized in {
        "docs/EMNLP2026_submission_fillin.md",
        "tools/package_anonymous_submission.py",
    }:
        return False
    name = Path(normalized).name.lower()
    if name.endswith("to do list.csv") or "to do list" in name:
        return False
    if any(marker in normalized.lower() for marker in ("paperreview", "rebuttal", "submission", "upload")):
        return False
    suffix = Path(normalized).suffix.lower()
    return suffix not in {".pdf", ".zip", ".db", ".env", ".local.json", ".local.yaml", ".local.yml"}


def filesystem_paths(root: Path) -> list[str]:
    paths = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(directory for directory in directories if directory != ".git")
        for filename in sorted(files):
            path = Path(current) / filename
            paths.append(path.relative_to(root).as_posix())
    return sorted(paths)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a repository or staged release tree.")
    parser.add_argument(
        "--root",
        type=Path,
        help="scan every file beneath this standalone release directory",
    )
    args = parser.parse_args()
    scan_root = args.root.resolve() if args.root else ROOT
    if args.root and not scan_root.is_dir():
        parser.error(f"scan root is not a directory: {scan_root}")
    paths = filesystem_paths(scan_root) if args.root else repository_candidate_paths()
    findings: list[str] = []
    for relative in paths:
        normalized = relative.replace("\\", "/")
        if normalized == ".env.example":
            continue
        if args.root and any(
            fnmatch.fnmatch(normalized, pattern) for pattern in PRIVATE_PATH_PATTERNS
        ):
            findings.append(f"private path: {relative}")
            continue
        path = scan_root / relative
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            findings.append(f"unreadable file: {relative}: {exc}")
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(f"credential-shaped literal in {relative}: {pattern.pattern}")

    if findings:
        print("PUBLIC_RELEASE_SCAN: FAIL")
        print("\n".join(f"- {item}" for item in findings))
        return 1

    print("PUBLIC_RELEASE_SCAN: PASS")
    print(f"files checked: {len(paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
