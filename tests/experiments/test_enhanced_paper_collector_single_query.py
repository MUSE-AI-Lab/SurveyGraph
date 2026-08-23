import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "mekg" / "src" / "processing" / "enhanced_paper_collector.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "enhanced_paper_collector_single_query_test",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_disable_keyword_split_returns_raw_topic(monkeypatch):
    module = load_module()

    class FakeAgent:
        def remote_chat(self, *_args, **_kwargs):
            return (
                '{"need_split": true, '
                '"keywords": [{"keyword": "multi-agent LLM", "weight": 1.0}], '
                '"reason": "force split"}'
            )

    monkeypatch.setenv("SURVEYGRAPH_DISABLE_KEYWORD_SPLIT", "true")
    collector = module.EnhancedPaperCollector(chat_agent=FakeAgent())

    keywords = collector.split_keywords_with_llm("LLM-based Multi-Agent")

    assert keywords == [{"keyword": "LLM-based Multi-Agent", "weight": 1.0}]


def test_collect_papers_stops_after_raw_keyword_when_variants_disabled(monkeypatch):
    module = load_module()
    module.HAS_EMBEDDING = False

    monkeypatch.setenv("SURVEYGRAPH_DISABLE_KEYWORD_SPLIT", "true")
    monkeypatch.setenv("SURVEYGRAPH_DISABLE_KEYWORD_VARIANTS", "true")

    collector = module.EnhancedPaperCollector(chat_agent=None)

    called_queries = []

    async def fake_search(query, max_results, categories, year_start, year_end):
        called_queries.append(
            {
                "query": query,
                "max_results": max_results,
                "categories": categories,
                "year_start": year_start,
                "year_end": year_end,
            }
        )
        return []

    async def fail_generate_keyword_variants(_topic, _used_keywords):
        raise AssertionError("keyword variants should not be generated in single-query mode")

    collector.detect_arxiv_categories = lambda _topic: (["cs.AI"], "computer_science")
    collector.arxiv.search = fake_search
    collector._generate_keyword_variants = fail_generate_keyword_variants

    results = asyncio.run(
        collector.collect_papers(
            topic="LLM-based Multi-Agent",
            target_count=5,
            year_start=2023,
            year_end=2024,
            use_embedding_filter=False,
            use_llm_filter=False,
            download_pdf=False,
            max_retry_rounds=3,
        )
    )

    assert results == []
    assert [item["query"] for item in called_queries] == ["LLM-based Multi-Agent"]
