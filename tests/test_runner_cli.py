import json
from pathlib import Path
import subprocess
import sys

import pytest
import run_sg_endtoend as runner


def test_default_interpreter_is_the_running_python():
    assert str(runner.PYTHON) == sys.executable


def test_dry_run_preserves_readme_arguments(capsys):
    rc = runner.main(["--topic", "a research topic", "--max_papers", "20", "--no-memgraph", "--no-evaluation", "--dry-run"])
    assert rc == 0
    command = json.loads(capsys.readouterr().out)
    assert command[0] == sys.executable
    assert Path(command[2]).name == "mekg_run.py"
    assert command[3:] == ["--topic", "a research topic", "--max_papers", "20", "--no-memgraph", "--no-evaluation"]


def test_no_topic_shows_error_without_launching(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: pytest.fail("unexpected pipeline launch"))
    with pytest.raises(SystemExit) as error:
        runner.main([])
    assert error.value.code == 2


def test_no_hidden_generation_defaults():
    command = runner.build_command("topic", sys.executable)
    assert command[3:] == ["--topic", "topic"]


def test_real_launcher_forwards_exit_code_and_arguments(tmp_path, monkeypatch):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "mekg_run.py").write_text("import sys\nprint(repr(sys.argv[1:]))\nsys.exit(7)\n", encoding="utf-8")
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    assert runner.main(["--topic", "two words", "--max_papers", "3"]) == 7


def test_shell_wrapper_forwards_arguments_from_another_directory(tmp_path):
    bash = Path("C:/Program Files/Git/bin/bash.exe") if sys.platform == "win32" else Path("/bin/bash")
    if not bash.exists():
        pytest.skip("Bash not installed")
    root = Path(runner.__file__).resolve().parent
    result = subprocess.run([str(bash), str(root / "run.sh"), "--topic", "shell topic", "--max_papers", "5", "--dry-run"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    command = json.loads(result.stdout)
    assert command[3:] == ["--topic", "shell topic", "--max_papers", "5"]
