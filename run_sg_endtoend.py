"""Run SurveyGraph topics sequentially under PM2 with live child logs.

The child process inherits this process's stdout/stderr, so PM2 receives Python
logs immediately instead of only after an entire topic exits. Progress is saved
after every topic, allowing a restarted runner to skip completed work.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
STATE_FILE = PROJECT_ROOT / "outputs" / "sg_endtoend_state.json"
TOPICS = [
    "LLM-based Multi-Agent",
    "Evaluation of Large Language Models",
    "Retrieval-Augmented Generation",
    "Multimodal Large Language Models",
    "Instruction Tuning",
]
DEFAULT_TOPIC_TIMEOUT_SECONDS = 4 * 60 * 60
TIMEOUT_RETURN_CODE = 124


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"topics": {}}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"=== SG STATE WARNING: cannot read {state_file}: {exc} ===", flush=True)
        return {"topics": {}}
    if not isinstance(state, dict) or not isinstance(state.get("topics"), dict):
        return {"topics": {}}
    return state


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_file.with_suffix(state_file.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(state_file)


def terminate_process_tree(process: subprocess.Popen) -> None:
    """Terminate a timed-out child and its descendants on Windows."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.kill()


def build_command(
    topic: str,
    python_executable: str | Path,
    resume_task_id: str | None = None,
) -> list[str]:
    command = [str(python_executable), "-u", "tasks/mekg_run.py"]
    if resume_task_id:
        command.extend(["--resume", "--task_id", resume_task_id])
    else:
        command.extend([
            "--topic",
            topic,
            "--max_papers",
            "30",
            "--year_start",
            "2022",
            "--year_end",
            "2024",
        ])
    command.append("--no-evaluation")
    return command


def run_topic(
    topic: str,
    *,
    python_executable: str | Path = PYTHON,
    project_root: str | Path = PROJECT_ROOT,
    timeout_seconds: float | None = DEFAULT_TOPIC_TIMEOUT_SECONDS,
    resume_task_id: str | None = None,
) -> int:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    command = build_command(topic, python_executable, resume_task_id)

    # Do not set stdout/stderr to PIPE: inheriting them is what makes logs appear
    # live in `pm2 logs sg`.
    process = subprocess.Popen(command, cwd=str(project_root), env=env)
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        print(
            f"=== SG TIMEOUT {topic} after {timeout_seconds:g}s; "
            "terminating child tree and continuing ===",
            flush=True,
        )
        terminate_process_tree(process)
        return TIMEOUT_RETURN_CODE
    except KeyboardInterrupt:
        terminate_process_tree(process)
        raise


def run_all_topics(
    topics: Iterable[str],
    *,
    state_file: str | Path = STATE_FILE,
    python_executable: str | Path = PYTHON,
    project_root: str | Path = PROJECT_ROOT,
    timeout_seconds: float | None = DEFAULT_TOPIC_TIMEOUT_SECONDS,
) -> int:
    state_path = Path(state_file)
    state = load_state(state_path)
    failed = False

    for topic in topics:
        previous = state["topics"].get(topic, {})
        if previous.get("status") == "completed":
            print(f"=== SG SKIP {topic} (already completed) ===", flush=True)
            continue

        resume_task_id = previous.get("resume_task_id") or previous.get("task_id")
        action = f"RESUME task_id={resume_task_id}" if resume_task_id else "START"
        print(f"=== SG {action} {topic} at {now_iso()} ===", flush=True)
        running_state = {
            "status": "running",
            "started_at": previous.get("started_at", now_iso()),
        }
        if resume_task_id:
            running_state["resume_task_id"] = resume_task_id
        state["topics"][topic] = running_state
        save_state(state_path, state)

        try:
            return_code = run_topic(
                topic,
                python_executable=python_executable,
                project_root=project_root,
                timeout_seconds=timeout_seconds,
                resume_task_id=resume_task_id,
            )
        except Exception as exc:  # Keep later topics runnable after launcher errors.
            failed = True
            state["topics"][topic] = {
                "status": "launcher_error",
                "finished_at": now_iso(),
                "error": f"{type(exc).__name__}: {exc}",
            }
            save_state(state_path, state)
            print(f"=== SG ERROR {topic}: {type(exc).__name__}: {exc} ===", flush=True)
            continue

        if return_code == 0:
            status = "completed"
        elif return_code == TIMEOUT_RETURN_CODE:
            status = "timeout"
            failed = True
        else:
            status = "failed"
            failed = True

        final_state = {
            "status": status,
            "return_code": return_code,
            "finished_at": now_iso(),
        }
        if resume_task_id:
            final_state["task_id"] = resume_task_id
        state["topics"][topic] = final_state
        save_state(state_path, state)
        print(f"=== SG DONE {topic} rc={return_code} status={status} ===", flush=True)

    print(
        "=== SG ALL TOPICS PROCESSED " + ("WITH FAILURES" if failed else "SUCCESSFULLY") + " ===",
        flush=True,
    )
    return 1 if failed else 0


def configured_timeout() -> float | None:
    raw = os.environ.get("SG_TOPIC_TIMEOUT_SECONDS", str(DEFAULT_TOPIC_TIMEOUT_SECONDS))
    value = float(raw)
    return None if value <= 0 else value


def main() -> int:
    return run_all_topics(TOPICS, timeout_seconds=configured_timeout())


if __name__ == "__main__":
    sys.exit(main())
