"""Run explicit SurveyGraph topics with live child logs and optional batch state.

The child process inherits this process's stdout/stderr, so PM2 receives Python
logs immediately instead of only after an entire topic exits. In batch mode,
progress is saved after every topic so restarts can skip completed work.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
STATE_FILE = PROJECT_ROOT / "outputs" / "sg_endtoend_state.json"
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
    pipeline_args: Iterable[str] = (),
    project_root: str | Path | None = None,
) -> list[str]:
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    command = [str(python_executable), "-u", str(root / "tasks" / "mekg_run.py")]
    if resume_task_id:
        command.extend(["--resume", "--task_id", resume_task_id])
    else:
        command.extend(["--topic", topic])
    command.extend(pipeline_args)
    return command


def run_topic(
    topic: str,
    *,
    python_executable: str | Path = PYTHON,
    project_root: str | Path = PROJECT_ROOT,
    timeout_seconds: float | None = DEFAULT_TOPIC_TIMEOUT_SECONDS,
    resume_task_id: str | None = None,
    pipeline_args: Iterable[str] = (),
) -> int:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    command = build_command(topic, python_executable, resume_task_id, pipeline_args, project_root)

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
    pipeline_args: Iterable[str] = (),
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
                pipeline_args=pipeline_args,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run SurveyGraph using the current Python interpreter. Pipeline options are forwarded unchanged.",
        epilog="Example: python run_sg_endtoend.py --topic 'retrieval augmented generation' --max_papers 20 --no-memgraph --no-evaluation",
        allow_abbrev=False,
    )
    parser.add_argument("--topic", action="append", help="Research topic; repeat for an explicit sequential batch")
    parser.add_argument("--python", default=sys.executable, help="Optional child Python interpreter")
    parser.add_argument("--state-file", type=Path, help="Batch progress file; only used with multiple topics")
    parser.add_argument("--topic-timeout", type=float, help="Seconds per topic (0 disables the timeout)")
    parser.add_argument("--dry-run", action="store_true", help="Print the exact child command as JSON without API calls")
    args, pipeline_args = parser.parse_known_args(argv)
    if not args.topic and not any(flag in pipeline_args for flag in ("--resume", "--list-tasks")):
        parser.error("--topic is required for a new run (or use --resume / --list-tasks)")
    try:
        timeout = args.topic_timeout if args.topic_timeout is not None else configured_timeout()
    except ValueError as exc:
        parser.error(f"invalid SG_TOPIC_TIMEOUT_SECONDS: {exc}")
    if timeout is not None and timeout <= 0:
        timeout = None
    topics = args.topic or [""]
    if len(topics) > 1 and any(flag in pipeline_args for flag in ("--resume", "--task_id", "--list-tasks")):
        parser.error("--resume, --task_id and --list-tasks require a single task")
    commands = [build_command(topic, args.python, pipeline_args=pipeline_args) for topic in topics]
    if not args.topic:
        commands[0] = [args.python, "-u", str(PROJECT_ROOT / "tasks" / "mekg_run.py"), *pipeline_args]
    if args.dry_run:
        print(json.dumps(commands[0] if len(commands) == 1 else commands, ensure_ascii=False))
        return 0
    if len(topics) > 1:
        import hashlib
        signature = hashlib.sha256(json.dumps(pipeline_args).encode()).hexdigest()[:12]
        state_file = args.state_file or STATE_FILE.with_name(f"sg_endtoend_{signature}.json")
        return run_all_topics(topics, state_file=state_file, python_executable=args.python,
                              project_root=PROJECT_ROOT, timeout_seconds=timeout, pipeline_args=pipeline_args)
    if not args.topic:
        process = subprocess.Popen(commands[0], cwd=str(PROJECT_ROOT), env={**os.environ, "PYTHONUNBUFFERED": "1"})
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process_tree(process)
            process.wait()
            return TIMEOUT_RETURN_CODE
        except KeyboardInterrupt:
            terminate_process_tree(process)
            process.wait()
            raise
    return run_topic(topics[0], python_executable=args.python, project_root=PROJECT_ROOT,
                     timeout_seconds=timeout, pipeline_args=pipeline_args)


if __name__ == "__main__":
    sys.exit(main())
