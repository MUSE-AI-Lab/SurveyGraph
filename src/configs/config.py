import json
import os
from pathlib import Path
from typing import Any, Dict


FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent
# Only the checked-in example is eligible as an import-time fallback. Local
# provider settings must be selected explicitly with SURVEYGRAPH_EXPERIMENT_CONFIG.
DEFAULT_EXPERIMENT_CONFIG = BASE_DIR / "experiments" / "configs" / "dashscope_models.example.json"


def _load_external_config() -> Dict[str, Any]:
    config_path = os.getenv("SURVEYGRAPH_EXPERIMENT_CONFIG", "").strip()
    candidates = [Path(config_path)] if config_path else []
    candidates.append(DEFAULT_EXPERIMENT_CONFIG)

    for candidate in candidates:
        try:
            if candidate and candidate.exists():
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            continue
    return {}


_EXTERNAL_CONFIG = _load_external_config()


def _cfg(name: str, default: Any) -> Any:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    if name in _EXTERNAL_CONFIG and _EXTERNAL_CONFIG[name] not in (None, ""):
        return _EXTERNAL_CONFIG[name]
    return default


def _cfg_int(name: str, default: int) -> int:
    try:
        return int(_cfg(name, default))
    except Exception:
        return default


def _cfg_float(name: str, default: float) -> float:
    try:
        return float(_cfg(name, default))
    except Exception:
        return default


def _cfg_bool(name: str, default: bool) -> bool:
    value = _cfg(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


# huggingface mirror
# os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
# os.environ["HF_HOME"] = os.path.expanduser("~/hf_cache/")

REMOTE_URL = _cfg(
    "REMOTE_URL",
    "",
)
TOKEN = _cfg(
    "TOKEN",
    os.getenv("OPENAI_API_KEY", os.getenv("DASHSCOPE_API_KEY", "")),
)
DEFAULT_CHATAGENT_MODEL = _cfg("DEFAULT_CHATAGENT_MODEL", "qwen3.6-plus")
ADVANCED_CHATAGENT_MODEL = _cfg(
    "ADVANCED_CHATAGENT_MODEL",
    DEFAULT_CHATAGENT_MODEL,
)
EVAL_TEXT_MODEL = _cfg("EVAL_TEXT_MODEL", DEFAULT_CHATAGENT_MODEL)

LOCAL_URL = _cfg("LOCAL_URL", "LOCAL_URL")
LOCAL_LLM = _cfg("LOCAL_LLM", "LOCAL_LLM")
DEFAULT_EMBED_LOCAL_MODEL = _cfg("DEFAULT_EMBED_LOCAL_MODEL", "DEFAULT_EMBED_LOCAL_MODEL")

## for embedding model
DEFAULT_EMBED_ONLINE_MODEL = _cfg("DEFAULT_EMBED_ONLINE_MODEL", "BAAI/bge-base-en-v1.5")
EMBED_REMOTE_URL = _cfg("EMBED_REMOTE_URL", "")
EMBED_TOKEN = _cfg("EMBED_TOKEN", "")
SPLITTER_WINDOW_SIZE = _cfg_int("SPLITTER_WINDOW_SIZE", 6)
SPLITTER_CHUNK_SIZE = _cfg_int("SPLITTER_CHUNK_SIZE", 2048)

## for preprocessing
CRAWLER_BASE_URL = _cfg("CRAWLER_BASE_URL", "")
CRAWLER_GOOGLE_SCHOLAR_SEND_TASK_URL = _cfg("CRAWLER_GOOGLE_SCHOLAR_SEND_TASK_URL", "")
DEFAULT_DATA_FETCHER_ENABLE_CACHE = _cfg_bool("DEFAULT_DATA_FETCHER_ENABLE_CACHE", True)
CUT_WORD_LENGTH = _cfg_int("CUT_WORD_LENGTH", 10)
MD_TEXT_LENGTH = _cfg_int("MD_TEXT_LENGTH", 100000)
ARXIV_PROJECTION = (
    "_id, title, authors, detail_url, abstract, md_text, reference, detail_id, image"
)

## Iteration and paper pool limits
DEFAULT_ITERATION_LIMIT = _cfg_int("DEFAULT_ITERATION_LIMIT", 3)
DEFAULT_PAPER_POOL_LIMIT = _cfg_int("DEFAULT_PAPER_POOL_LIMIT", 1024)

## Keyword generation strategy
MAX_TOTAL_KEYWORDS = _cfg_int("MAX_TOTAL_KEYWORDS", 4)
MIN_PAPERS_BEFORE_EXPANSION = _cfg_int("MIN_PAPERS_BEFORE_EXPANSION", 50)
KEYWORD_SIMILARITY_THRESHOLD = _cfg_float("KEYWORD_SIMILARITY_THRESHOLD", 0.7)

## llamaindex OpenAI
DEFAULT_LLAMAINDEX_OPENAI_MODEL = _cfg(
    "DEFAULT_LLAMAINDEX_OPENAI_MODEL",
    DEFAULT_CHATAGENT_MODEL,
)

# ============================================
# 并发配置
# ============================================
PAPER_SEARCH_WORKERS = _cfg_int("PAPER_SEARCH_WORKERS", 100)
PDF_DOWNLOAD_WORKERS = _cfg_int("PDF_DOWNLOAD_WORKERS", 100)
OPENALEX_CONCURRENT = _cfg_int("OPENALEX_CONCURRENT", 100)
CHAT_AGENT_WORKERS = _cfg_int("CHAT_AGENT_WORKERS", 200)
PAPER_ATTRI_WORKERS = _cfg_int("PAPER_ATTRI_WORKERS", 200)
RELATION_DISCOVERY_WORKERS = _cfg_int("RELATION_DISCOVERY_WORKERS", 100)
ENTITY_EXTRACTION_WORKERS = _cfg_int("ENTITY_EXTRACTION_WORKERS", 100)
MOUNT_PAPERS_WORKERS = _cfg_int("MOUNT_PAPERS_WORKERS", 200)
CONTENT_GEN_WORKERS = _cfg_int("CONTENT_GEN_WORKERS", 50)
EVALUATION_WORKERS = _cfg_int("EVALUATION_WORKERS", 100)
COMMUNITY_LABEL_WORKERS = _cfg_int("COMMUNITY_LABEL_WORKERS", 100)
SECTION_REFLECTION_WORKERS = _cfg_int("SECTION_REFLECTION_WORKERS", 50)
RELEVANCE_FILTER_WORKERS = _cfg_int("RELEVANCE_FILTER_WORKERS", 200)
TASK_QUEUE_WORKERS = _cfg_int("TASK_QUEUE_WORKERS", 100)

## survey generation
COARSE_GRAINED_TOPK = _cfg_int("COARSE_GRAINED_TOPK", 200)
MIN_FILTERED_LIMIT = _cfg_int("MIN_FILTERED_LIMIT", 150)
NUM_PROCESS_LIMIT = _cfg_int("NUM_PROCESS_LIMIT", 10)

## fig retrieving
FIG_RETRIEVE_URL = _cfg("FIG_RETRIEVE_URL", "")
ENHANCED_FIG_RETRIEVE_URL = _cfg("ENHANCED_FIG_RETRIEVE_URL", "")
FIG_CHUNK_SIZE = _cfg_int("FIG_CHUNK_SIZE", 8192)
MATCH_TOPK = _cfg_int("MATCH_TOPK", 3)
FIG_RETRIEVE_Authorization = _cfg("FIG_RETRIEVE_Authorization", "")
FIG_RETRIEVE_TOKEN = _cfg("FIG_RETRIEVE_TOKEN", "")

# ============================================
# New configurations for online search and multimodal features
# ============================================
OPENALEX_EMAIL = _cfg("OPENALEX_EMAIL", "surveyx@example.com")
OPENALEX_MAX_RESULTS = _cfg_int("OPENALEX_MAX_RESULTS", 200)
OPENALEX_ENABLE_CACHE = _cfg_bool("OPENALEX_ENABLE_CACHE", True)

ARXIV_MAX_RESULTS = _cfg_int("ARXIV_MAX_RESULTS", 100)
ARXIV_DEFAULT_CATEGORIES = _EXTERNAL_CONFIG.get(
    "ARXIV_DEFAULT_CATEGORIES",
    ["cs.CL", "cs.AI", "cs.LG", "cs.CV", "cs.IR"],
)
ARXIV_REQUEST_INTERVAL = _cfg_float("ARXIV_REQUEST_INTERVAL", 3.0)

MINERU_BACKEND = _cfg("MINERU_BACKEND", "pipeline")
MINERU_DEVICE = _cfg("MINERU_DEVICE", "cuda")

MULTIMODAL_API_URL = _cfg("MULTIMODAL_API_URL", REMOTE_URL)
MULTIMODAL_API_KEY = _cfg("MULTIMODAL_API_KEY", TOKEN)
MULTIMODAL_MODEL = _cfg("MULTIMODAL_MODEL", DEFAULT_CHATAGENT_MODEL)

MAX_IMAGES_TOTAL = _cfg_int("MAX_IMAGES_TOTAL", 8)
MAX_IMAGES_PER_SECTION = _cfg_int("MAX_IMAGES_PER_SECTION", 2)
MIN_IMAGE_RELEVANCE_SCORE = _cfg_int("MIN_IMAGE_RELEVANCE_SCORE", 6)
MIN_IMAGE_QUALITY_SCORE = _cfg_int("MIN_IMAGE_QUALITY_SCORE", 5)
MIN_IMAGE_ACADEMIC_VALUE = _cfg_int("MIN_IMAGE_ACADEMIC_VALUE", 6)

ONLINE_SEARCH_MAX_PAPERS = _cfg_int("ONLINE_SEARCH_MAX_PAPERS", 50)
ONLINE_SEARCH_MAX_DOWNLOADS = _cfg_int("ONLINE_SEARCH_MAX_DOWNLOADS", 30)
ONLINE_SEARCH_ENABLE_MULTIMODAL = _cfg_bool("ONLINE_SEARCH_ENABLE_MULTIMODAL", True)

RELEVANCE_FILTER_MODEL = _cfg("RELEVANCE_FILTER_MODEL", DEFAULT_CHATAGENT_MODEL)
RELEVANCE_FILTER_THRESHOLD = _cfg_float("RELEVANCE_FILTER_THRESHOLD", 0.5)
RELEVANCE_FILTER_USE_LLM = _cfg_bool("RELEVANCE_FILTER_USE_LLM", True)

# ============================================
# AI Image Generation configuration
# ============================================
AI_IMAGE_API_URL = _cfg("AI_IMAGE_API_URL", REMOTE_URL)
AI_IMAGE_API_KEY = _cfg("AI_IMAGE_API_KEY", TOKEN)
AI_IMAGE_MODEL = _cfg("AI_IMAGE_MODEL", DEFAULT_CHATAGENT_MODEL)
ENABLE_AI_IMAGES = _cfg_bool("ENABLE_AI_IMAGES", True)

AI_IMAGE_MAX_PER_SURVEY = _cfg_int("AI_IMAGE_MAX_PER_SURVEY", 5)
AI_IMAGE_MAX_ITERATIONS = _cfg_int("AI_IMAGE_MAX_ITERATIONS", 3)
AI_IMAGE_MIN_QUALITY_SCORE = _cfg_float("AI_IMAGE_MIN_QUALITY_SCORE", 7.0)
AI_IMAGE_PREFER_SURVEY_STYLE = _cfg_bool("AI_IMAGE_PREFER_SURVEY_STYLE", True)

# ============================================
# Survey LaTeX configuration
# ============================================
SURVEY_AUTHOR_URL = _cfg("SURVEY_AUTHOR_URL", "https://surveygraph.pisces.ink")
SURVEY_AUTHOR_TEXT = _cfg("SURVEY_AUTHOR_TEXT", "https://surveygraph.pisces.ink")
