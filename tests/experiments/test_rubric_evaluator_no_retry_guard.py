import importlib.util
import sys
import types
from pathlib import Path


def _load_rubric_evaluator_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "post_refine"
        / "rubric_evaluator.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_rubric_evaluator_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    stub_names = [
        "src",
        "src.configs",
        "src.configs.logger",
        "src.models",
        "src.models.LLM",
    ]
    originals = {name: sys.modules.get(name) for name in stub_names}

    logger_stub = types.ModuleType("src.configs.logger")
    llm_stub = types.ModuleType("src.models.LLM")

    class FakeLogger:
        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

    class ChatAgent:
        pass

    logger_stub.get_logger = lambda _name: FakeLogger()
    llm_stub.ChatAgent = ChatAgent

    for package_name in ["src", "src.configs", "src.models"]:
        sys.modules[package_name] = types.ModuleType(package_name)
    sys.modules["src.configs.logger"] = logger_stub
    sys.modules["src.models.LLM"] = llm_stub

    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


rubric_module = _load_rubric_evaluator_module()
RubricEvaluator = rubric_module.RubricEvaluator


class FakeNoRetryRubricChatAgent:
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


def _minimal_evaluator(chat):
    evaluator = RubricEvaluator.__new__(RubricEvaluator)
    evaluator.chat_agent = chat
    evaluator.use_llm = True
    return evaluator


def test_llm_evaluate_subcriterion_uses_no_retry_with_bounded_timeout():
    chat = FakeNoRetryRubricChatAgent(
        '{"score": 4, "feedback": "The survey is coherent and well supported."}'
    )
    evaluator = _minimal_evaluator(chat)
    levels = {"5": "excellent", "4": "good", "3": "acceptable"}

    score, feedback = evaluator._llm_evaluate_subcriterion(
        survey_content="This survey covers function calling methods with citations.",
        category_name="Coverage",
        subcriterion_name="Breadth",
        levels=levels,
        topic="Function Calling",
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["temperature"] == 0.3
    assert chat.no_retry_calls[0][1]["timeout"] <= 180
    assert score == 4.0
    assert feedback == "The survey is coherent and well supported."


def test_llm_evaluate_subcriterion_falls_back_on_no_retry_error_response():
    chat = FakeNoRetryRubricChatAgent("Error: Timeout after 120s")
    evaluator = _minimal_evaluator(chat)

    score, feedback = evaluator._llm_evaluate_subcriterion(
        survey_content="A partial survey draft.",
        category_name="Writing",
        subcriterion_name="Clarity",
        levels={"5": "excellent", "3": "acceptable", "1": "poor"},
        topic="Function Calling",
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert score == 3.0
    assert "评估失败" in feedback or "fallback" in feedback.lower()
