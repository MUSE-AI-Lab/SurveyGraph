#!/usr/bin/env python3
"""Inventory the complete local research workspace without deleting anything."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "release_artifacts",
    ".codex-tasks",
}
PUBLIC_ROOTS = {
    ".github",
    "src",
    "mekg",
    "evaluation",
    "experiments",
    "tasks",
    "frontend",
    "tests",
    "docs",
    "resources",
    "scripts",
    "OpenAlex",
}


def local_paths() -> set[str]:
    """Return every regular file in the workspace, including ignored files."""
    paths: set[str] = set()
    for current, directories, files in os.walk(ROOT, topdown=True, followlinks=False):
        directories[:] = sorted(
            directory for directory in directories if directory not in SKIP_DIRS
        )
        for filename in sorted(files):
            path = Path(current) / filename
            try:
                relative = path.relative_to(ROOT).as_posix()
            except ValueError:
                continue
            paths.add(relative)
    return paths


def staged_deleted_paths() -> set[str]:
    """Keep absent staged paths visible in the manifest as historical records."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=D", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return {
        item.decode("utf-8", "surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def classify(relative: str, exists: bool) -> str:
    normalized = relative.replace(os.sep, "/")
    root = normalized.split("/", 1)[0]
    name = Path(normalized).name.lower()
    suffix = Path(normalized).suffix.lower()
    if not exists:
        return "removed-sensitive-or-baseline-only"
    if normalized.startswith("refer/") or root in {"backup", "backups"}:
        return "preserve-local-third-party-or-history"
    if normalized.startswith("data/graph_db/") or root in {
        "output",
        "outputs",
        "tmp",
        "log",
    }:
        return "preserve-local-generated-state"
    if normalized.startswith("paper/openreview_") or suffix in {
        ".pdf",
        ".zip",
        ".db",
    }:
        return "preserve-local-research-artifact"
    if (
        name == ".env"
        or suffix in {".env", ".json", ".yaml", ".yml"}
        and ("local" in normalized.lower() or "paperreview" in normalized.lower())
    ):
        return "preserve-local-configuration-or-session"
    if root in PUBLIC_ROOTS or normalized in {
        ".env.example",
        ".gitignore",
        "README.md",
        "LICENSE",
        "CITATION.cff",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "requirements.txt",
        "pytest.ini",
        "run_sg_endtoend.py",
        "run.sh",
    }:
        return "public-release-candidate"
    return "review-before-publish"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory local source, results, references, and private artifacts."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "release_artifacts" / "RESEARCH_ASSET_MANIFEST.tsv",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for relative in sorted(local_paths() | staged_deleted_paths()):
        path = ROOT / relative
        exists = path.is_file()
        rows.append(
            {
                "path": relative,
                "exists": str(exists).lower(),
                "classification": classify(relative, exists),
                "bytes": path.stat().st_size if exists else 0,
                "sha256": sha256(path) if exists else "",
            }
        )
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["path", "exists", "classification", "bytes", "sha256"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    print("ASSET_MANIFEST: PASS")
    print(f"files inventoried: {len(rows)}")
    print(f"present files: {sum(row['exists'] == 'true' for row in rows)}")
    print(f"output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
