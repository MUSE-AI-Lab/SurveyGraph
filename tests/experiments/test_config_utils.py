import json
from pathlib import Path

from experiments.lib.config_utils import (
    build_process_env,
    load_experiment_config,
    normalize_chat_completions_url,
    normalize_openai_base_url,
)


def test_url_normalization():
    assert normalize_chat_completions_url("https://x/v1") == "https://x/v1/chat/completions"
    assert normalize_chat_completions_url("https://x/v1/chat/completions") == "https://x/v1/chat/completions"
    assert normalize_openai_base_url("https://x/v1/chat/completions") == "https://x/v1"


def test_load_and_build_env(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "REMOTE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "TOKEN": "sk-test",
        "DEFAULT_CHATAGENT_MODEL": "qwen3.6-plus",
        "ADVANCED_CHATAGENT_MODEL": "glm-5.1",
        "CHAT_AGENT_WORKERS": 8
    }), encoding="utf-8")

    monkeypatch.setenv("SURVEYGRAPH_EXPERIMENT_CONFIG", str(config_path))
    config = load_experiment_config()
    env = build_process_env(config)

    assert env["TOKEN"] == "sk-test"
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert env["DEFAULT_CHATAGENT_MODEL"] == "qwen3.6-plus"
    assert env["ADVANCED_CHATAGENT_MODEL"] == "glm-5.1"
    assert env["CHAT_AGENT_WORKERS"] == "8"
