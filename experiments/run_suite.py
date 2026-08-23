import argparse
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.lib.config_utils import (
    build_process_env,
    ensure_dir,
    load_experiment_config,
    output_json,
    repo_python,
    slugify,
    timestamp_slug,
)


def load_manifest(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_run_directory(suite_name: str, run_name: str, suite_timestamp: str) -> Path:
    return ensure_dir(Path("outputs") / "experiment_suites" / suite_name / suite_timestamp / slugify(run_name))


def augment_command(run: Dict[str, Any], run_dir: Path, suite_timestamp: str) -> List[str]:
    command = list(run["command"])
    if command and command[0].lower() == "python":
        command[0] = repo_python()
    command_str = " ".join(command)

    if "tasks/mekg_run.py" in command_str and "--task_id" not in command:
        task_id = f"{suite_timestamp}_{slugify(run['name'])}"
        command.extend(["--task_id", task_id])

    if "evaluation.main" in command_str and "--output-dir" not in command:
        command.extend(["--output-dir", str(run_dir / "evaluation_output")])

    return command


def run_one(
    run: Dict[str, Any],
    config: Dict[str, Any],
    suite_name: str,
    suite_timestamp: str,
    dry_run: bool
) -> Dict[str, Any]:
    run_dir = build_run_directory(suite_name, run["name"], suite_timestamp)
    log_path = run_dir / "stdout.log"
    command = augment_command(run, run_dir, suite_timestamp)

    env = build_process_env(
        config,
        default_model=run.get("env", {}).get("DEFAULT_CHATAGENT_MODEL"),
        advanced_model=run.get("env", {}).get("ADVANCED_CHATAGENT_MODEL"),
        eval_text_model=run.get("env", {}).get("EVAL_TEXT_MODEL"),
        extra_env=run.get("env", {})
    )
    env["SURVEYGRAPH_EXPERIMENT_RUN_DIR"] = str(run_dir.resolve())

    metadata = {
        "name": run["name"],
        "command": command,
        "run_dir": str(run_dir),
        "started_at": datetime.now().isoformat(),
        "timeout_sec": run.get("timeout_sec", 14400),
    }
    output_json(run_dir / "run_meta.json", metadata)

    if dry_run:
        return {
            **metadata,
            "returncode": 0,
            "status": "dry_run"
        }

    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            timeout=run.get("timeout_sec", 14400),
            text=True
        )

    return {
        **metadata,
        "finished_at": datetime.now().isoformat(),
        "returncode": process.returncode,
        "status": "success" if process.returncode == 0 else "failed",
        "log_path": str(log_path)
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SurveyGraph experiment suite in isolated parallel processes")
    parser.add_argument("--manifest", type=str, required=True, help="manifest JSON 路径")
    parser.add_argument("--config", type=str, default=None, help="实验配置 JSON 路径")
    parser.add_argument("--max-parallel", type=int, default=None, help="覆盖 manifest 中的并发上限")
    parser.add_argument("--dry-run", action="store_true", help="只生成命令与目录，不真正执行")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    config = load_experiment_config(args.config)
    suite_name = manifest["suite_name"]
    max_parallel = args.max_parallel or manifest.get("max_parallel", 1)
    suite_timestamp = timestamp_slug()

    summary_root = ensure_dir(Path("outputs") / "experiment_suites" / suite_name / suite_timestamp)
    output_json(summary_root / "suite_meta.json", {
        "manifest": args.manifest,
        "config_path": config["_config_path"],
        "max_parallel": max_parallel,
        "dry_run": args.dry_run,
        "run_count": len(manifest.get("runs", []))
    })

    results = []
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        future_map = {
            executor.submit(run_one, run, config, suite_name, suite_timestamp, args.dry_run): run
            for run in manifest.get("runs", [])
        }
        for future in as_completed(future_map):
            run = future_map[future]
            try:
                result = future.result()
            except Exception as e:
                result = {
                    "name": run["name"],
                    "status": "exception",
                    "error": repr(e)
                }
            results.append(result)
            print(f"[{result['status']}] {run['name']}")

    output_json(summary_root / "suite_results.json", {
        "suite_name": suite_name,
        "timestamp": suite_timestamp,
        "results": results
    })
    print(f"[done] suite summary saved to {summary_root / 'suite_results.json'}")


if __name__ == "__main__":
    main()
