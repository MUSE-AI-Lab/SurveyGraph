import importlib.util
import json
import sys
from pathlib import Path


def _load_reclassifier_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "mekg"
        / "src"
        / "processing"
        / "paper_reclassifier.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_paper_reclassifier_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.MAX_RETRIES = 0
    return module


reclassifier_module = _load_reclassifier_module()
PaperReclassifier = reclassifier_module.PaperReclassifier


class FakeTaxonomyChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by taxonomy generation"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return json.dumps(
            {
                "taxonomy": [
                    {
                        "category": "Methods",
                        "description": "Core methods.",
                        "subcategories": [
                            {"name": "Planning", "description": "Planning methods."}
                        ],
                    }
                ]
            }
        )


def test_generate_taxonomy_uses_no_retry_chat_guard():
    chat_agent = FakeTaxonomyChatAgent()
    reclassifier = PaperReclassifier(chat_agent=chat_agent, max_workers=1)
    outline_data = {
        "sections": [
            {
                "number": "2",
                "title": "Core Methods",
                "description": "Technical methods.",
                "subsections": [
                    {
                        "number": "2.1",
                        "title": "Planning",
                        "description": "Planning methods.",
                    }
                ],
            }
        ]
    }

    reclassifier._generate_taxonomy(outline_data, "Function Calling", verbose=False)

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert [node.name for node in reclassifier.taxonomy] == ["Methods"]
    assert reclassifier.taxonomy[0].subcategories[0]["name"] == "Planning"


class FakeClassificationChatAgent:
    def __init__(self):
        self.remote_calls = []
        self.no_retry_calls = []

    def remote_chat(self, *args, **kwargs):
        self.remote_calls.append((args, kwargs))
        return "retrying remote_chat should not be used by paper classification"

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return json.dumps(
            {
                "classifications": [
                    {
                        "category": "Methods",
                        "subcategory": "Planning",
                        "confidence": 0.9,
                        "reason": "The paper studies planning.",
                    }
                ]
            }
        )


def test_classify_paper_uses_no_retry_chat_guard():
    chat_agent = FakeClassificationChatAgent()
    reclassifier = PaperReclassifier(chat_agent=chat_agent, max_workers=1)
    reclassifier.taxonomy_text = "1. Methods\n  1.1 Planning"
    reclassifier.valid_categories = {"Methods"}
    reclassifier.valid_subcategories = {"Methods": {"Planning"}}
    paper = {
        "id": "p1",
        "title": "Planning for Function Calling",
        "abstract": "We study planning methods for tool and function calling.",
    }

    classification = reclassifier._classify_paper(paper)

    assert chat_agent.remote_calls == []
    assert len(chat_agent.no_retry_calls) == 1
    assert classification.paper_id == "p1"
    assert classification.classifications[0]["category"] == "Methods"
