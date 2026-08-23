import importlib.util
import sys
import types
from pathlib import Path


def _load_data_cleaner_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "preprocessor"
        / "data_cleaner.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_data_cleaner_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    stub_names = [
        "src.configs",
        "src.configs.config",
        "src.configs.constants",
        "src.configs.logger",
        "src.models",
        "src.models.LLM",
        "src.models.LLM.utils",
        "src.models.monitor",
        "src.models.monitor.time_monitor",
        "src.modules.utils",
    ]
    originals = {name: sys.modules.get(name) for name in stub_names}

    configs_stub = types.ModuleType("src.configs")
    config_stub = types.ModuleType("src.configs.config")
    constants_stub = types.ModuleType("src.configs.constants")
    logger_stub = types.ModuleType("src.configs.logger")
    models_stub = types.ModuleType("src.models")
    llm_stub = types.ModuleType("src.models.LLM")
    llm_utils_stub = types.ModuleType("src.models.LLM.utils")
    monitor_stub = types.ModuleType("src.models.monitor")
    time_monitor_stub = types.ModuleType("src.models.monitor.time_monitor")
    module_utils_stub = types.ModuleType("src.modules.utils")

    config_stub.BASE_DIR = str(Path(__file__).resolve().parents[2])
    config_stub.CHAT_AGENT_WORKERS = 1
    config_stub.PAPER_ATTRI_WORKERS = 1
    config_stub.MD_TEXT_LENGTH = 1024
    constants_stub.OUTPUT_DIR = str(Path(__file__).resolve().parents[2] / "outputs")

    class FakeLogger:
        def debug(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    logger_stub.get_logger = lambda _name: FakeLogger()

    class ChatAgent:
        pass

    class TimeMonitor:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, *args, **kwargs):
            pass

        def end(self, *args, **kwargs):
            pass

    llm_stub.ChatAgent = ChatAgent
    llm_utils_stub.cut_text_by_token = lambda text, _limit: text
    llm_utils_stub.load_prompt = lambda *args, **kwargs: ""
    time_monitor_stub.TimeMonitor = TimeMonitor
    module_utils_stub.clean_chat_agent_format = lambda content: content
    module_utils_stub.load_file_as_string = lambda path: Path(path).read_text(
        encoding="utf-8"
    )
    module_utils_stub.sanitize_filename = lambda name: name
    module_utils_stub.save_result = lambda content, path: Path(path).write_text(
        content, encoding="utf-8"
    )

    sys.modules["src.configs"] = configs_stub
    sys.modules["src.configs.config"] = config_stub
    sys.modules["src.configs.constants"] = constants_stub
    sys.modules["src.configs.logger"] = logger_stub
    sys.modules["src.models"] = models_stub
    sys.modules["src.models.LLM"] = llm_stub
    sys.modules["src.models.LLM.utils"] = llm_utils_stub
    sys.modules["src.models.monitor"] = monitor_stub
    sys.modules["src.models.monitor.time_monitor"] = time_monitor_stub
    sys.modules["src.modules.utils"] = module_utils_stub

    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


DataCleaner = _load_data_cleaner_module().DataCleaner


class FakeFixChatAgent:
    def __init__(self):
        self.no_retry_calls = []

    def remote_chat_no_retry(self, text_content, **kwargs):
        self.no_retry_calls.append((text_content, kwargs))
        return '{"idea": "this JSON fix call should not happen for transport errors"}'


def test_transport_error_response_skips_json_fix_llm_call():
    cleaner = DataCleaner(papers=[{"title": "Paper A"}])
    chat_agent = FakeFixChatAgent()

    processed = cleaner._DataCleaner__process_attri_response(
        "Error: RuntimeError: simulated batch request failure",
        paper_index=0,
        chat_agent=chat_agent,
    )

    assert processed is False
    assert chat_agent.no_retry_calls == []
    assert "attri" not in cleaner.papers[0]


class FakeAttriBatchChatAgent:
    def __init__(self):
        self.batch_calls = []

    def batch_remote_chat(self, prompts, **kwargs):
        self.batch_calls.append((prompts, kwargs))
        return ['{"idea": "cost-capped extraction", "method": "unit test"}']


def test_get_attri_uses_no_retry_batch_for_long_attribute_extraction():
    cleaner = DataCleaner(
        papers=[
            {
                "title": "Paper A",
                "paper_type": "method",
                "md_text": "The full paper text.",
            }
        ]
    )
    chat_agent = FakeAttriBatchChatAgent()

    cleaner.get_attri(chat_agent)

    assert len(chat_agent.batch_calls) == 1
    _prompts, kwargs = chat_agent.batch_calls[0]
    assert kwargs["use_retry"] is False
    assert kwargs["timeout"] >= 180
    assert cleaner.papers[0]["attri"]["idea"] == "cost-capped extraction"


class FakeFailingPaperTypeChatAgent:
    def __init__(self):
        self.batch_calls = []

    def batch_remote_chat(self, prompts, **kwargs):
        self.batch_calls.append((prompts, kwargs))
        return ["Error: Timeout after 120s" for _ in prompts]


def test_get_paper_type_defaults_to_method_after_retry_exhaustion():
    cleaner = DataCleaner(
        papers=[
            {
                "title": "Paper A",
                "abstract": "This paper proposes a function-calling method.",
            }
        ]
    )
    chat_agent = FakeFailingPaperTypeChatAgent()

    cleaner.get_paper_type(chat_agent)

    assert len(chat_agent.batch_calls) == 3
    assert cleaner.papers[0]["paper_type"] == "method"
