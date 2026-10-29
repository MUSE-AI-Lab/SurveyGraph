#!/usr/bin/env python3
"""Build a deterministic public-release tree without deleting local research assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIRECTORIES = {
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
PUBLIC_TOOL_FILES = {
    "tools/check_expense.py",
    "tools/remove_unsuccessful.py",
    "tools/remve_log.py",
    "tools/test_crawler.py",
    "tools/test_multimodal.py",
}
PUBLIC_ROOT_FILES = {
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
EXCLUDED_DIRECTORY_PREFIXES = {
    "docs/superpowers/",
}
EXCLUDED_FILES = {
    "docs/EMNLP2026_submission_fillin.md",
    "tools/package_anonymous_submission.py",
}
PRIVATE_MARKERS = (
    "paperreview",
    "rebuttal",
    "submission",
    "upload",
)
EXCLUDED_SUFFIXES = {
    ".pdf",
    ".zip",
    ".tar.gz",
    ".db",
    ".pyc",
    ".log",
    ".aux",
    ".out",
    ".bbl",
    ".blg",
    ".fdb_latexmk",
    ".fls",
    ".synctex.gz",
    ".toc",
    ".env",
    ".local.json",
    ".local.yaml",
    ".local.yml",
}


def candidate_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(
        {
            item.decode("utf-8", "surrogateescape")
            for item in result.stdout.split(b"\0")
            if item
        }
    )


def is_public_path(relative: str) -> bool:
    normalized = relative.replace(os.sep, "/")
    root, _, _ = normalized.partition("/")
    if normalized in PUBLIC_ROOT_FILES:
        return True
    if root == "tools":
        return normalized in PUBLIC_TOOL_FILES
    if root not in PUBLIC_DIRECTORIES:
        return False
    if any(normalized.startswith(prefix) for prefix in EXCLUDED_DIRECTORY_PREFIXES):
        return False
    if normalized in EXCLUDED_FILES:
        return False
    name = Path(normalized).name.lower()
    suffix = Path(normalized).suffix.lower()
    if name.endswith("to do list.csv") or "to do list" in name:
        return False
    if any(marker in normalized.lower() for marker in PRIVATE_MARKERS):
        return False
    if suffix in EXCLUDED_SUFFIXES or normalized.lower().endswith(".tar.gz"):
        return False
    return True


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def prepare_output(output: Path) -> None:
    """Delete only a clearly disposable child directory, never an arbitrary path."""
    resolved = output.resolve()
    root = ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        if output.exists():
            if not output.is_dir() or any(output.iterdir()):
                raise SystemExit(
                    "refusing to replace a non-empty output outside the repository root"
                )
        else:
            output.mkdir(parents=True, exist_ok=True)
            return
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise SystemExit("output must be a real directory")
        shutil.rmtree(output)
    output.mkdir(parents=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage only explicitly approved SurveyGraph source and documentation."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "release_artifacts" / "public_release",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    prepare_output(output)

    included = []
    excluded_paths = []
    for relative in candidate_paths():
        source = ROOT / relative
        if not source.is_file():
            continue
        if not is_public_path(relative):
            excluded_paths.append(relative)
            continue
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        included.append(
            {
                "path": relative,
                "bytes": source.stat().st_size,
                "sha256": digest(source),
            }
        )

    manifest = {
        "schema": 1,
        "source": "current-working-tree",
        "included_count": len(included),
        "excluded_count": len(excluded_paths),
        "included": included,
        "excluded": excluded_paths,
    }
    (output / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("PUBLIC_STAGING: PASS")
    print(f"included files: {len(included)}")
    print(f"excluded files: {len(excluded_paths)}")
    print(f"output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
