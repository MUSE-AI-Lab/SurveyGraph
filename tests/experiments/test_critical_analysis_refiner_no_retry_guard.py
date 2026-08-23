import importlib.util
import sys
import types
from pathlib import Path


def _load_critical_analysis_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "post_refine"
        / "critical_analysis_refiner.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_critical_analysis_refiner_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    stub_names = [
        "src",
        "src.models",
        "src.models.LLM",
        "src.models.LLM.ChatAgent",
    ]
    originals = {name: sys.modules.get(name) for name in stub_names}

    for package_name in ["src", "src.models", "src.models.LLM"]:
        sys.modules[package_name] = types.ModuleType(package_name)

    chat_agent_stub = types.ModuleType("src.models.LLM.ChatAgent")

    class ChatAgent:
        pass

    chat_agent_stub.ChatAgent = ChatAgent
    sys.modules["src.models.LLM.ChatAgent"] = chat_agent_stub

    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


critical_module = _load_critical_analysis_module()
CriticalAnalysisRefiner = critical_module.CriticalAnalysisRefiner
AnalysisIssue = critical_module.AnalysisIssue


class FakeNoRetryCriticalChatAgent:
    def __init__(self, response):
        self.response = response
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        raise AssertionError("retry-stacked remote_chat should not be used")

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return self.response


def test_enhance_paragraph_uses_no_retry_for_optional_critical_analysis():
    chat = FakeNoRetryCriticalChatAgent(
        "Method A improves tool invocation over Method B by adding schema-aware validation while preserving the original citation \\cite{p1}."
    )
    refiner = CriticalAnalysisRefiner(chat_agent=chat)
    paragraph = "Method A significantly improves tool invocation over Method B in a proposed framework and system \\cite{p1}."
    issues = [
        AnalysisIssue(
            issue_type="missing_quantitative",
            location="段落 1",
            original_text="Method A significantly improves tool invocation over Method B",
            suggestion="Add bounded evidence or qualify the comparison.",
            severity="high",
        )
    ]

    enhanced = refiner._enhance_paragraph(paragraph, issues, {"paper": "p1"})

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["temperature"] == 0.3
    assert chat.no_retry_calls[0][1]["timeout"] <= 180
    assert "schema-aware validation" in enhanced


def test_enhance_paragraph_falls_back_to_original_on_no_retry_error():
    chat = FakeNoRetryCriticalChatAgent("Error: Timeout after 180s")
    refiner = CriticalAnalysisRefiner(chat_agent=chat)
    paragraph = "Method A significantly improves tool invocation over Method B in a proposed framework and system \\cite{p1}."
    issues = [
        AnalysisIssue(
            issue_type="missing_quantitative",
            location="段落 1",
            original_text="Method A significantly improves tool invocation over Method B",
            suggestion="Add bounded evidence or qualify the comparison.",
            severity="high",
        )
    ]

    enhanced = refiner._enhance_paragraph(paragraph, issues, None)

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert enhanced == paragraph

def test_constructor_respects_env_disable_for_llm_enhancement(monkeypatch):
    monkeypatch.setenv("CRITICAL_ANALYSIS_ENABLE_LLM", "false")
    chat = FakeNoRetryCriticalChatAgent("This response should not be requested.")

    refiner = CriticalAnalysisRefiner(chat_agent=chat)

    assert refiner.enable_enhancement is False


def test_analyze_content_does_not_call_llm_when_env_disables_enhancement(monkeypatch):
    monkeypatch.setenv("CRITICAL_ANALYSIS_ENABLE_LLM", "false")
    chat = FakeNoRetryCriticalChatAgent("This response should not be requested.")
    refiner = CriticalAnalysisRefiner(chat_agent=chat, min_paragraph_length=20)
    content = "Method Alpha significantly improves tool invocation over Method Beta in a proposed framework and system."

    result = refiner.analyze_content(content)

    assert result.issues_found
    assert result.refined_content == content
    assert result.improvements_made == []
    assert chat.remote_calls == []
    assert chat.no_retry_calls == []
