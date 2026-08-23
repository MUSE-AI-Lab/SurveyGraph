import json
import subprocess
from unittest.mock import patch

# The legacy script executes work at import time. Stub subprocess.run so the
# regression tests can import it without launching the real pipeline.
with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
    import run_sg_endtoend as runner


class FakeProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.wait_calls = []

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode


def test_run_topic_inherits_pm2_streams_and_forces_unbuffered_python(monkeypatch, tmp_path):
    seen = {}
    process = FakeProcess()

    def fake_popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    rc = runner.run_topic(
        "test topic",
        python_executable="python.exe",
        project_root=tmp_path,
        timeout_seconds=123,
    )

    assert rc == 0
    assert seen["command"][:2] == ["python.exe", "-u"]
    assert "stdout" not in seen["kwargs"]
    assert "stderr" not in seen["kwargs"]
    assert seen["kwargs"]["env"]["PYTHONUNBUFFERED"] == "1"
    assert process.wait_calls == [123]


def test_run_all_topics_continues_after_timeout_and_records_progress(monkeypatch, tmp_path):
    attempted = []

    def fake_run_topic(topic, **kwargs):
        attempted.append(topic)
        return 124 if topic == "slow" else 0

    monkeypatch.setattr(runner, "run_topic", fake_run_topic)
    state_file = tmp_path / "state.json"

    rc = runner.run_all_topics(
        ["slow", "next"],
        state_file=state_file,
        project_root=tmp_path,
        timeout_seconds=10,
    )

    assert rc == 1
    assert attempted == ["slow", "next"]
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["topics"]["slow"]["status"] == "timeout"
    assert state["topics"]["next"]["status"] == "completed"


def test_run_all_topics_skips_topics_already_completed(monkeypatch, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps({"topics": {"done": {"status": "completed"}}}),
        encoding="utf-8",
    )
    attempted = []
    monkeypatch.setattr(
        runner,
        "run_topic",
        lambda topic, **kwargs: attempted.append(topic) or 0,
    )

    rc = runner.run_all_topics(
        ["done", "pending"],
        state_file=state_file,
        project_root=tmp_path,
        timeout_seconds=None,
    )

    assert rc == 0
    assert attempted == ["pending"]

class TimeoutProcess(FakeProcess):
    pid = 4321

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(["python.exe"], timeout)


def test_run_topic_converts_timeout_to_status_instead_of_crashing(monkeypatch, tmp_path):
    killed = []
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: TimeoutProcess())
    monkeypatch.setattr(runner, "terminate_process_tree", lambda process: killed.append(process.pid))

    rc = runner.run_topic(
        "slow topic",
        python_executable="python.exe",
        project_root=tmp_path,
        timeout_seconds=5,
    )

    assert rc == 124
    assert killed == [4321]


def test_run_all_topics_resumes_saved_task_id(monkeypatch, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "topics": {
                    "interrupted": {
                        "status": "running",
                        "resume_task_id": "task-123",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run_topic(topic, **kwargs):
        calls.append((topic, kwargs.get("resume_task_id")))
        return 0

    monkeypatch.setattr(runner, "run_topic", fake_run_topic)

    rc = runner.run_all_topics(
        ["interrupted"],
        state_file=state_file,
        project_root=tmp_path,
        timeout_seconds=10,
    )

    assert rc == 0
    assert calls == [("interrupted", "task-123")]
