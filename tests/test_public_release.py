from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_required_release_documents_exist() -> None:
    required = (
        "README.md",
        ".env.example",
        "LICENSE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CITATION.cff",
        "data/README.md",
        "docs/PUBLIC_RELEASE_BOUNDARY.md",
        ".github/workflows/ci.yml",
        "scripts/audit_release_assets.py",
        "scripts/check_public_release.py",
        "scripts/stage_public_release.py",
        "scripts/package_public_release.py",
    )
    missing = [path for path in required if not (ROOT / path).is_file()]
    assert not missing, f"missing release files: {missing}"


def test_frontend_configuration_has_local_safe_defaults() -> None:
    sys.path.insert(0, str(ROOT / "frontend"))
    from config import DatabaseConfig, JWTConfig  # type: ignore

    assert DatabaseConfig.HOST == "127.0.0.1"
    assert DatabaseConfig.PASSWORD == ""
    assert JWTConfig.SECRET_KEY
    assert "change-in-production" not in JWTConfig.SECRET_KEY


def test_core_configuration_does_not_require_a_secret(monkeypatch) -> None:
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("SURVEYGRAPH_EXPERIMENT_CONFIG", raising=False)
    sys.path.insert(0, str(ROOT))
    from src.configs import config

    assert config.TOKEN == ""
    assert config.MULTIMODAL_API_KEY == ""
    assert config.AI_IMAGE_API_KEY == ""


def test_public_release_scan_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_public_release.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PUBLIC_RELEASE_SCAN: PASS" in result.stdout


def test_asset_audit_includes_ignored_local_research_files(tmp_path: Path) -> None:
    output = tmp_path / "RESEARCH_ASSET_MANIFEST.tsv"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_release_assets.py",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    present_paths = {row["path"] for row in rows if row["exists"] == "true"}

    assert any(path.startswith("refer/") for path in present_paths)
    assert any(path.startswith("data/graph_db/") for path in present_paths)
    assert any(
        path.startswith("paper/openreview_supplementary_")
        for path in present_paths
    )


def test_public_staging_uses_a_strict_allowlist(tmp_path: Path) -> None:
    output = tmp_path / "public-release"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/stage_public_release.py",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PUBLIC_STAGING: PASS" in result.stdout

    required = {
        "README.md",
        "LICENSE",
        "CITATION.cff",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "src/configs/config.py",
        "mekg/__init__.py",
        "tests/test_public_release.py",
        "scripts/check_public_release.py",
        "docs/PUBLIC_RELEASE_BOUNDARY.md",
        "RELEASE_MANIFEST.json",
    }
    staged_files = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert required <= staged_files

    forbidden_prefixes = (
        "paper/",
        "refer/",
        "release_artifacts/",
        "docs/superpowers/",
        ".codex-tasks/",
    )
    forbidden_names = {
        "docs/EMNLP2026_submission_fillin.md",
        "tools/package_anonymous_submission.py",
    }
    forbidden_suffixes = (".pdf", ".zip", ".db", ".env", ".local.json")
    assert not any(
        path.startswith(forbidden_prefixes)
        or path in forbidden_names
        or path.lower().endswith(forbidden_suffixes)
        or "paperreview" in path.lower()
        or "rebuttal" in path.lower()
        or path.endswith("TO DO list.csv")
        for path in staged_files
    )

    manifest = json.loads(
        (output / "RELEASE_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["included_count"] == len(staged_files) - 1
    assert manifest["schema"] == 1


def test_staged_tree_passes_standalone_scan(tmp_path: Path) -> None:
    output = tmp_path / "public-release"
    stage = subprocess.run(
        [sys.executable, "scripts/stage_public_release.py", "--output", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert stage.returncode == 0, stage.stdout + stage.stderr

    scan = subprocess.run(
        [sys.executable, "scripts/check_public_release.py", "--root", str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert scan.returncode == 0, scan.stdout + scan.stderr
    assert "PUBLIC_RELEASE_SCAN: PASS" in scan.stdout


def test_standalone_scan_rejects_private_state(tmp_path: Path) -> None:
    release_root = tmp_path / "unsafe-release"
    release_root.mkdir()
    (release_root / ".env").write_text(
        "TOKEN=" + "sk" + "-" + "A" * 32 + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_public_release.py",
            "--root",
            str(release_root),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert "PUBLIC_RELEASE_SCAN: FAIL" in result.stdout
    assert "private path" in result.stdout


def test_public_release_package_contains_only_scanned_tree(tmp_path: Path) -> None:
    output = tmp_path / "SurveyGraph-public-release.zip"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/package_public_release.py",
            "--source",
            str(ROOT / "release_artifacts" / "public_release"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PUBLIC_PACKAGE: PASS" in result.stdout
    assert output.is_file()
    assert output.with_suffix(".zip.sha256").is_file()

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert "SurveyGraph-public-release/README.md" in names
    assert "SurveyGraph-public-release/RELEASE_MANIFEST.json" in names
    assert not any(
        "paper/" in name
        or "refer/" in name
        or name.lower().endswith((".pdf", ".zip", ".db", ".env"))
        or "paperreview" in name.lower()
        or "rebuttal" in name.lower()
        or "submission" in name.lower()
        for name in names
    )


def test_env_example_contains_no_credential_value() -> None:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "sk-" not in content
    assert "AKIA" not in content
    assert "DB_PASSWORD=" in content
    assert "JWT_SECRET=replace-with" in content


def test_scanner_does_not_ship_historical_secret_fragments() -> None:
    content = (ROOT / "scripts/check_public_release.py").read_text(encoding="utf-8")
    assert "y2" + "iX" not in content
    assert "CBTL" + "4ZRWdaZE" not in content
