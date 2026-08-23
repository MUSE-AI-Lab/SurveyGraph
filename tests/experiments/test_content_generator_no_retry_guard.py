import importlib.util
import sys
import types
from pathlib import Path


def _load_content_generator_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "models"
        / "generator"
        / "content_generator.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_content_generator_under_test",
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
        "src.models.monitor.token_monitor",
        "src.modules",
        "src.modules.preprocessor",
        "src.modules.preprocessor.utils",
        "src.modules.utils",
        "src.schemas",
        "src.schemas.base",
        "src.schemas.outlines",
    ]
    originals = {name: sys.modules.get(name) for name in stub_names}

    config_stub = types.ModuleType("src.configs.config")
    constants_stub = types.ModuleType("src.configs.constants")
    logger_stub = types.ModuleType("src.configs.logger")
    llm_stub = types.ModuleType("src.models.LLM")
    llm_utils_stub = types.ModuleType("src.models.LLM.utils")
    time_monitor_stub = types.ModuleType("src.models.monitor.time_monitor")
    token_monitor_stub = types.ModuleType("src.models.monitor.token_monitor")
    preprocessor_utils_stub = types.ModuleType("src.modules.preprocessor.utils")
    module_utils_stub = types.ModuleType("src.modules.utils")
    base_stub = types.ModuleType("src.schemas.base")
    outlines_stub = types.ModuleType("src.schemas.outlines")

    config_stub.ADVANCED_CHATAGENT_MODEL = "advanced-test-model"
    config_stub.BASE_DIR = str(Path(__file__).resolve().parents[2])
    config_stub.CHAT_AGENT_WORKERS = 1
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
        pass

    class TokenMonitor:
        pass

    class Base:
        def __init__(self, task_id):
            self.task_id = task_id
            self.topic = "Function Calling"

    class Outlines:
        def __str__(self):
            return "outline"

    class SingleOutline:
        pass

    llm_stub.ChatAgent = ChatAgent
    llm_utils_stub.load_prompt = lambda *args, **kwargs: "prompt"
    time_monitor_stub.TimeMonitor = TimeMonitor
    token_monitor_stub.TokenMonitor = TokenMonitor
    preprocessor_utils_stub.parse_arguments_for_integration_test = lambda: None
    module_utils_stub.clean_chat_agent_format = lambda content: content
    module_utils_stub.load_file_as_string = lambda path: Path(path).read_text(
        encoding="utf-8"
    )
    module_utils_stub.save_result = lambda content, path: Path(path).write_text(
        content, encoding="utf-8"
    )
    base_stub.Base = Base
    outlines_stub.Outlines = Outlines
    outlines_stub.SingleOutline = SingleOutline

    for package_name in [
        "src.configs",
        "src.models",
        "src.models.monitor",
        "src.modules",
        "src.modules.preprocessor",
        "src.schemas",
    ]:
        sys.modules[package_name] = types.ModuleType(package_name)
    sys.modules["src.configs.config"] = config_stub
    sys.modules["src.configs.constants"] = constants_stub
    sys.modules["src.configs.logger"] = logger_stub
    sys.modules["src.models.LLM"] = llm_stub
    sys.modules["src.models.LLM.utils"] = llm_utils_stub
    sys.modules["src.models.monitor.time_monitor"] = time_monitor_stub
    sys.modules["src.models.monitor.token_monitor"] = token_monitor_stub
    sys.modules["src.modules.preprocessor.utils"] = preprocessor_utils_stub
    sys.modules["src.modules.utils"] = module_utils_stub
    sys.modules["src.schemas.base"] = base_stub
    sys.modules["src.schemas.outlines"] = outlines_stub

    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


content_module = _load_content_generator_module()
ContentGenerator = content_module.ContentGenerator


class FakeOutlines:
    def __str__(self):
        return "outline"


class FakeNoRetryContentChatAgent:
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


class FakeMountChatAgent:
    def __init__(self):
        self.batch_calls = []

    def batch_remote_chat(self, *args, **kwargs):
        self.batch_calls.append((args, kwargs))
        raise AssertionError("mounting should reuse existing mount_outline")


def _generator():
    generator = ContentGenerator.__new__(ContentGenerator)
    generator.topic = "Function Calling"
    return generator


def test_write_content_iteratively_uses_no_retry_for_cost_capped_generation():
    chat = FakeNoRetryContentChatAgent(
        "A concise LaTeX-ready paragraph without markdown syntax."
    )

    result = _generator().write_content_iteratively(
        papers=["bib_name: p1\ninfo: method evidence"],
        outlines=FakeOutlines(),
        written_content="",
        last_written="",
        subsection_title="Evaluation",
        subsection_desc="Evaluation methods.",
        chat=chat,
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["model"] == "advanced-test-model"
    assert chat.no_retry_calls[0][1]["timeout"] >= 240
    assert result == "A concise LaTeX-ready paragraph without markdown syntax."


def test_write_content_iteratively_falls_back_to_last_written_on_no_retry_error():
    chat = FakeNoRetryContentChatAgent("Error: Timeout after 300s")

    result = _generator().write_content_iteratively(
        papers=["bib_name: p1\ninfo: method evidence"],
        outlines=FakeOutlines(),
        written_content="",
        last_written="Existing generated paragraph.",
        subsection_title="Evaluation",
        subsection_desc="Evaluation methods.",
        chat=chat,
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert result == "Existing generated paragraph."


def test_gen_single_section_words_uses_no_retry_and_inserts_answer():
    chat = FakeNoRetryContentChatAgent("<answer>Three concise section keywords.</answer>")

    result = _generator().gen_single_section_words(
        "\\section{Core Methods}\n<section_words>\nBody.",
        chat,
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["timeout"] >= 120
    assert "<section_words>" not in result
    assert "Three concise section keywords." in result


def test_gen_single_section_words_removes_placeholder_on_no_retry_error():
    chat = FakeNoRetryContentChatAgent("Error: Timeout after 180s")

    result = _generator().gen_single_section_words(
        "\\section{Core Methods}\n<section_words>\nBody.",
        chat,
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert "<section_words>" not in result
    assert "Body." in result


def test_gen_abstract_uses_no_retry_and_writes_abstract(tmp_path):
    chat = FakeNoRetryContentChatAgent(
        "<abstract>Function calling methods are surveyed.</abstract>"
    )
    mainbody_path = tmp_path / "mainbody.raw.tex"
    abstract_path = tmp_path / "abstract.tex"
    mainbody_path.write_text("Survey body.", encoding="utf-8")

    _generator().gen_abstract(str(mainbody_path), str(abstract_path), chat)

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["model"] == "advanced-test-model"
    assert chat.no_retry_calls[0][1]["timeout"] >= 120
    written = abstract_path.read_text(encoding="utf-8")
    assert "\\begin{abstract}" in written
    assert "Function calling methods are surveyed." in written


def test_gen_abstract_writes_fallback_on_no_retry_error(tmp_path):
    chat = FakeNoRetryContentChatAgent("Error: Timeout after 180s")
    mainbody_path = tmp_path / "mainbody.raw.tex"
    abstract_path = tmp_path / "abstract.tex"
    mainbody_path.write_text("Survey body.", encoding="utf-8")

    _generator().gen_abstract(str(mainbody_path), str(abstract_path), chat)

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    written = abstract_path.read_text(encoding="utf-8")
    assert "\\begin{abstract}" in written
    assert "survey synthesizes" in written


def test_mount_trees_on_outlines_skips_when_all_papers_already_mounted(tmp_path):
    paper_path = tmp_path / "paper.json"
    paper_path.write_text(
        '{"attri": {"title": "Paper"}, "mount_outline": [{"section number": "1", "key information": ["x"]}]}',
        encoding="utf-8",
    )
    chat = FakeMountChatAgent()

    _generator().mount_trees_on_outlines(tmp_path, FakeOutlines(), chat)

    assert chat.batch_calls == []
