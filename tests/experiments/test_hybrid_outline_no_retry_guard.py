import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_hybrid_outline_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "outline"
        / "hybrid_outline_generator.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_hybrid_outline_generator_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    original_models = sys.modules.get("src.models")
    original_llm = sys.modules.get("src.models.LLM")
    original_utils = sys.modules.get("src.models.LLM.utils")

    models_stub = types.ModuleType("src.models")
    llm_stub = types.ModuleType("src.models.LLM")
    utils_stub = types.ModuleType("src.models.LLM.utils")
    llm_stub.ChatAgent = lambda: None
    utils_stub.load_prompt = lambda *args, **kwargs: ""
    sys.modules["src.models"] = models_stub
    sys.modules["src.models.LLM"] = llm_stub
    sys.modules["src.models.LLM.utils"] = utils_stub
    try:
        spec.loader.exec_module(module)
    finally:
        if original_models is None:
            sys.modules.pop("src.models", None)
        else:
            sys.modules["src.models"] = original_models
        if original_llm is None:
            sys.modules.pop("src.models.LLM", None)
        else:
            sys.modules["src.models.LLM"] = original_llm
        if original_utils is None:
            sys.modules.pop("src.models.LLM.utils", None)
        else:
            sys.modules["src.models.LLM.utils"] = original_utils
    return module


hybrid_module = _load_hybrid_outline_module()
HybridOutlineGenerator = hybrid_module.HybridOutlineGenerator
HybridOutline = hybrid_module.HybridOutline
OutlineSection = hybrid_module.OutlineSection


class FakeNoRetryChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by hybrid outline calls"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return json.dumps(
            {
                "title": "Merged Survey",
                "sections": [
                    {
                        "title": "Introduction",
                        "description": "Scope.",
                        "key_points": ["motivation"],
                        "subsections": [],
                    },
                    {
                        "title": "Methods",
                        "description": "Methods.",
                        "key_points": ["workflow"],
                        "subsections": [],
                    },
                ],
            }
        )


def test_merge_outlines_uses_no_retry_chat_guard():
    chat_agent = FakeNoRetryChatAgent()
    generator = HybridOutlineGenerator(
        chat_agent=chat_agent,
        use_embedding_clustering=False,
    )
    top_down = HybridOutline(
        title="Top Down",
        topic="Function Calling",
        sections=[
            OutlineSection(
                title="Introduction",
                description="Intro.",
                key_points=["scope"],
            )
        ],
    )
    bottom_up = [
        OutlineSection(
            title="Methods",
            description="Methods.",
            key_points=["workflow"],
        )
    ]

    merged = generator._merge_outlines("Function Calling", top_down, bottom_up)

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert chat_agent.no_retry_calls[0][1]["model"] == hybrid_module.ADVANCED_CHATAGENT_MODEL
    assert merged.title == "Merged Survey"
    assert [section.title for section in merged.sections] == ["Introduction", "Methods"]
