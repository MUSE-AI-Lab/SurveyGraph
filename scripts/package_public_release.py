#!/usr/bin/env python3
"""Package the verified public-release tree into a reproducible ZIP archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "release_artifacts" / "public_release"
DEFAULT_OUTPUT = ROOT / "release_artifacts" / "SurveyGraph-public-release.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_scan(source: Path) -> None:
    scanner = ROOT / "scripts" / "check_public_release.py"
    subprocess.run(
        [sys.executable, str(scanner), "--root", str(source)],
        cwd=ROOT,
        check=True,
    )


def source_files(source: Path) -> list[Path]:
    return sorted(path for path in source.rglob("*") if path.is_file())


def write_archive(source: Path, output: Path, root_name: str) -> list[str]:
    files = source_files(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            archive_name = f"{root_name}/{relative}"
            info = zipfile.ZipInfo(archive_name)
            # Fixed metadata makes repeated packages byte-for-byte stable.
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return [f"{root_name}/{path.relative_to(source).as_posix()}" for path in files]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package and verify the deterministic SurveyGraph public tree."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--root-name", default="SurveyGraph-public-release")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        parser.error(f"source is not a directory: {source}")
    if output == source or source in output.parents:
        parser.error("output archive must be outside the source tree")
    if not args.root_name or "/" in args.root_name or "\\" in args.root_name:
        parser.error("root name must be a single non-empty path component")

    manifest_path = source / "RELEASE_MANIFEST.json"
    if not manifest_path.is_file():
        parser.error(f"source is missing RELEASE_MANIFEST.json: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_count = int(manifest["included_count"]) + 1

    run_scan(source)
    archive_names = write_archive(source, output, args.root_name)
    with zipfile.ZipFile(output) as archive:
        actual_names = archive.namelist()
    if len(actual_names) != expected_count or actual_names != archive_names:
        raise SystemExit(
            "archive verification failed: "
            f"expected {expected_count} entries, got {len(actual_names)}"
        )

    digest = sha256(output)
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print("PUBLIC_PACKAGE: PASS")
    print(f"files packaged: {len(archive_names)}")
    print(f"archive: {output}")
    print(f"bytes: {output.stat().st_size}")
    print(f"sha256: {digest}")
    print(f"checksum: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
