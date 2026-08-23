import json
import importlib.util
import sys
from pathlib import Path


def _load_outline_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "mekg"
        / "src"
        / "survey"
        / "outline_generator.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_outline_generator_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


outline_module = _load_outline_module()
MEKGOutlineGenerator = outline_module.MEKGOutlineGenerator
OutlineSection = outline_module.OutlineSection
SurveyOutline = outline_module.SurveyOutline


class FakeNoRetryChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by critic/refine"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        if len(self.no_retry_calls) == 1:
            return "1. Keep the scope tight.\n2. Improve the workflow ordering."
        return json.dumps(
            {
                "title": "Refined Survey",
                "sections": [
                    {"title": "Introduction", "desc": "Motivation and scope."},
                    {"title": "Methods", "desc": "Core technical methods."},
                    {"title": "Evaluation", "desc": "Benchmarks and metrics."},
                ],
            }
        )


def test_critic_refine_uses_no_retry_chat_guard():
    chat_agent = FakeNoRetryChatAgent()
    generator = MEKGOutlineGenerator(chat_agent=chat_agent)
    outline = SurveyOutline(
        title="Initial Survey",
        topic="Function Calling",
        sections=[
            OutlineSection(
                number="1",
                title="Introduction",
                description="Intro.",
                level=1,
            ),
            OutlineSection(
                number="2",
                title="Methods",
                description="Methods.",
                level=1,
            ),
            OutlineSection(
                number="3",
                title="Evaluation",
                description="Evaluation.",
                level=1,
            ),
        ],
    )

    refined = generator._critic_and_refine(outline, "Function Calling")

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 2
    assert chat_agent.no_retry_calls[0][1]["timeout"] == 180
    assert chat_agent.no_retry_calls[1][1]["timeout"] == 120
    assert refined.title == "Refined Survey"
    assert [section.title for section in refined.sections] == [
        "Introduction",
        "Methods",
        "Evaluation",
    ]


class FakeOutlineGenerationChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by outline generation"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return json.dumps(
            {
                "title": "No-Retry Outline",
                "sections": [
                    {"title": "Introduction", "desc": "Scope."},
                    {"title": "Methods", "desc": "Methods."},
                    {"title": "Evaluation", "desc": "Evaluation."},
                ],
            }
        )


def test_initial_outline_generation_uses_no_retry_chat_guard():
    chat_agent = FakeOutlineGenerationChatAgent()
    generator = MEKGOutlineGenerator(chat_agent=chat_agent)
    structure_info = {
        "communities": [
            {
                "name": "Benchmarks",
                "paper_count": 1,
                "subcategories": ["Function calling"],
            }
        ],
        "core_papers": [
            {
                "title": "Benchmarking Function Calling",
                "year": 2025,
                "citations": 10,
                "category": "Benchmarks",
                "subcategory": "Function calling",
            }
        ],
        "relation_stats": {"extends": 1},
        "year_distribution": {2025: 1},
        "total_papers": 1,
    }

    outline = generator._generate_with_llm("Function Calling", structure_info, 3)

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert outline.title == "No-Retry Outline"
    assert [section.title for section in outline.sections] == [
        "Introduction",
        "Methods",
        "Evaluation",
    ]


class FakeInvalidOutlineGenerationChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by outline generation"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return ""


def test_initial_outline_generation_falls_back_to_rules_when_llm_returns_empty_outline():
    chat_agent = FakeInvalidOutlineGenerationChatAgent()
    generator = MEKGOutlineGenerator(chat_agent=chat_agent)
    structure_info = {
        "communities": [
            {
                "name": "Function Schema and Tool Registration",
                "paper_count": 3,
                "subcategories": ["Schema induction", "Tool documentation"],
            },
            {
                "name": "Function Selection and Routing",
                "paper_count": 2,
                "subcategories": ["Intent detection", "Tool choice"],
            },
        ],
        "core_papers": [],
        "relation_stats": {"shares_task": 2},
        "year_distribution": {2024: 2, 2025: 3},
        "total_papers": 5,
    }

    outline = generator._generate_with_llm("Function Calling", structure_info, 4)

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert len(outline.sections) >= 3
    assert [section.title for section in outline.sections] == [
        "Introduction",
        "Function Schema and Tool Registration",
        "Function Selection and Routing",
        "Conclusion and Future Directions",
    ]


class FakeMountChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by threaded mounting"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return json.dumps(
            [
                {
                    "section_number": "1",
                    "key_info": "This paper evaluates function-calling behavior.",
                }
            ]
        )


def test_threaded_mounting_uses_no_retry_chat_guard():
    chat_agent = FakeMountChatAgent()
    generator = MEKGOutlineGenerator(chat_agent=chat_agent)
    papers = [
        {
            "id": "p1",
            "title": "Benchmarking Function Calling",
            "abstract": "We evaluate function-calling behavior.",
            "year": 2025,
            "citations": 10,
        }
    ]
    mount_prompt = (
        "Outline: {outline}\n"
        "Title: {title}\n"
        "Abstract: {abstract}\n"
        "Year: {year}\n"
        "Citations: {citations}"
    )

    mounts = generator._mount_papers_threaded(papers, "1. Introduction", mount_prompt)

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert mounts["p1"][0]["section_number"] == "1"
