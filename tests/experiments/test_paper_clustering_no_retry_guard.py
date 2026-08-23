import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_paper_clustering_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "outline"
        / "paper_clustering.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_paper_clustering_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    original_models = sys.modules.get("src.models")
    original_llm = sys.modules.get("src.models.LLM")

    models_stub = types.ModuleType("src.models")
    llm_stub = types.ModuleType("src.models.LLM")
    llm_stub.EmbedAgent = lambda: None
    llm_stub.ChatAgent = lambda: None
    sys.modules["src.models"] = models_stub
    sys.modules["src.models.LLM"] = llm_stub
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
    return module


clustering_module = _load_paper_clustering_module()
PaperClusterer = clustering_module.PaperClusterer
ClusterInfo = clustering_module.ClusterInfo


class FakeNoRetryChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by clustering labels"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return json.dumps(
            {
                "title": "Function Calling Evaluation",
                "description": "Benchmarks and metrics for function calling.",
                "key_aspects": ["benchmarks", "metrics", "tool use"],
            }
        )


def test_extract_topics_uses_no_retry_chat_guard():
    chat_agent = FakeNoRetryChatAgent()
    clusterer = PaperClusterer(
        embed_agent=object(),
        chat_agent=chat_agent,
        algorithm="kmeans",
    )
    clusters = [
        ClusterInfo(
            cluster_id=0,
            paper_indices=[0],
            paper_titles=["Benchmarking Function Calling"],
        )
    ]
    papers = [
        {
            "title": "Benchmarking Function Calling",
            "abstract": "We evaluate tool-use and function-calling behavior.",
        }
    ]

    clusterer._extract_topics_with_llm(clusters, papers, "Function Calling")

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert clusters[0].title == "Function Calling Evaluation"
    assert clusters[0].key_aspects == ["benchmarks", "metrics", "tool use"]
