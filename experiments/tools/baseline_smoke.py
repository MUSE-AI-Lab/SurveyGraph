import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_command(command, cwd, timeout_sec):
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_sec,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "output_preview": completed.stdout[:4000],
    }


def surveyforge() -> dict:
    repo = REPO_ROOT / "refer" / "SurveyForge-main" / "code"
    if not repo.exists():
        return {"status": "missing_repo", "repo": str(repo)}
    checks = []
    checks.append(run_command([sys.executable, "-c", "import importlib.util, sys; print(importlib.util.find_spec('anthropic') is not None)"], repo, 120))
    main_py = repo / "main.py"
    checks.append({
        "command": ["python", str(main_py)],
        "exists": main_py.exists(),
    })
    return {"status": "ok", "repo": str(repo), "checks": checks}


def scisage() -> dict:
    repo = REPO_ROOT / "refer" / "SciSage-main"
    if not repo.exists():
        return {"status": "missing_repo", "repo": str(repo)}
    checks = []
    checks.append(run_command([sys.executable, "-c", "import core, eval; print('import_ok')"], repo, 120))
    readme = repo / "Readme.md"
    checks.append({"command": ["check_readme"], "exists": readme.exists()})
    return {"status": "ok", "repo": str(repo), "checks": checks}


def arise() -> dict:
    repo = REPO_ROOT / "refer" / "ARISE-main"
    if not repo.exists():
        return {"status": "missing_repo", "repo": str(repo)}
    checks = []
    checks.append(run_command([sys.executable, "-c", "import importlib.util; print(importlib.util.find_spec('crewai') is not None)"], repo, 120))
    src_dir = repo / "ARISE_Source_Code"
    checks.append({"command": ["check_source_dir"], "exists": src_dir.exists()})
    return {"status": "ok", "repo": str(repo), "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline smoke harness")
    parser.add_argument("--system", required=True, choices=["surveyforge", "scisage", "arise"])
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    result = globals()[args.system]()
    output_path = Path(args.output) if args.output else Path("outputs") / "baseline_smoke" / f"{args.system}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
