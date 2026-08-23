import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_CONFIG = REPO_ROOT / "experiments" / "configs" / "dashscope_models.local.json"
DEFAULT_EXAMPLE_CONFIG = REPO_ROOT / "experiments" / "configs" / "dashscope_models.example.json"


def load_experiment_config(path: Optional[str] = None) -> Dict[str, Any]:
    config_path = Path(
        path
        or os.getenv("SURVEYGRAPH_EXPERIMENT_CONFIG")
        or DEFAULT_LOCAL_CONFIG
    )
    if not config_path.exists():
        raise FileNotFoundError(
            f"实验配置不存在: {config_path}\n"
            f"请先创建本地私有配置，参考: {DEFAULT_EXAMPLE_CONFIG}"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_config_path"] = str(config_path)
    return data


def normalize_chat_completions_url(base_or_chat_url: str) -> str:
    value = str(base_or_chat_url).strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/chat/completions"


def normalize_openai_base_url(base_or_chat_url: str) -> str:
    value = str(base_or_chat_url).strip().rstrip("/")
    if value.endswith("/chat/completions"):
        return value[: -len("/chat/completions")]
    return value


def repo_python() -> str:
    explicit = os.environ.get("PYTHON", "").strip()
    if explicit:
        return explicit

    windows_venv = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    posix_venv = REPO_ROOT / ".venv" / "bin" / "python"
    if windows_venv.exists():
        return str(windows_venv)
    if posix_venv.exists():
        return str(posix_venv)
    return "python"


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return value[:64] or "run"


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_process_env(
    config: Dict[str, Any],
    *,
    default_model: Optional[str] = None,
    advanced_model: Optional[str] = None,
    eval_text_model: Optional[str] = None,
    extra_env: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    def _unique_keep_order(values: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    env = dict(os.environ)
    env["SURVEYGRAPH_EXPERIMENT_CONFIG"] = config["_config_path"]

    remote_url = normalize_chat_completions_url(
        config.get("REMOTE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    )
    env["REMOTE_URL"] = remote_url
    env["TOKEN"] = str(config.get("TOKEN", ""))
    env["OPENAI_API_KEY"] = str(config.get("TOKEN", ""))
    env["DASHSCOPE_API_KEY"] = str(config.get("TOKEN", ""))

    env["DEFAULT_CHATAGENT_MODEL"] = default_model or str(
        config.get("DEFAULT_CHATAGENT_MODEL", "qwen3.6-plus")
    )
    env["ADVANCED_CHATAGENT_MODEL"] = advanced_model or str(
        config.get("ADVANCED_CHATAGENT_MODEL", env["DEFAULT_CHATAGENT_MODEL"])
    )
    env["EVAL_TEXT_MODEL"] = eval_text_model or str(
        config.get("EVAL_TEXT_MODEL", env["DEFAULT_CHATAGENT_MODEL"])
    )
    env["EVALUATION_T2T_MODELS"] = ",".join(
        _unique_keep_order([
            env["DEFAULT_CHATAGENT_MODEL"],
            env["ADVANCED_CHATAGENT_MODEL"],
            env["EVAL_TEXT_MODEL"],
        ])
    )

    for key in [
        "CHAT_AGENT_WORKERS",
        "PAPER_ATTRI_WORKERS",
        "RELATION_DISCOVERY_WORKERS",
        "ENTITY_EXTRACTION_WORKERS",
        "MOUNT_PAPERS_WORKERS",
        "CONTENT_GEN_WORKERS",
        "SECTION_REFLECTION_WORKERS",
        "EVALUATION_WORKERS",
        "COMMUNITY_LABEL_WORKERS",
        "RELEVANCE_FILTER_WORKERS",
        "OPENALEX_CONCURRENT",
        "PDF_DOWNLOAD_WORKERS",
        "PAPER_SEARCH_WORKERS",
        "TASK_QUEUE_WORKERS"
    ]:
        if key in config:
            env[key] = str(config[key])

    if extra_env:
        for key, value in extra_env.items():
            env[key] = str(value)

    env["PYTHONUNBUFFERED"] = "1"
    return env


def get_profile_env(config: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    profiles = config.get("PROFILES", {})
    if profile_name not in profiles:
        raise KeyError(f"配置中不存在 profile: {profile_name}")
    return dict(profiles[profile_name])


def model_catalog(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    catalog = config.get("MODEL_CATALOG", [])
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("MODEL_CATALOG 为空，无法探测模型")
    return catalog


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def flatten_topic(topic: str) -> str:
    return slugify(topic.replace(" ", "_"))
