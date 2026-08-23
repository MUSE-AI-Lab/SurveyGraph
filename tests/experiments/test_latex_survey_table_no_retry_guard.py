import importlib.util
import sys
import types
from pathlib import Path


def _load_table_builder_module():
    module_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "modules"
        / "latex_handler"
        / "latex_survey_table_builder.py"
    )
    spec = importlib.util.spec_from_file_location(
        "surveygraph_latex_survey_table_builder_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module

    stub_names = [
        "src.configs",
        "src.configs.config",
        "src.configs.logger",
        "src.models",
        "src.models.LLM",
        "src.modules",
        "src.modules.latex_handler",
        "src.modules.latex_handler.latex_base_table_builder",
        "src.modules.utils",
    ]
    originals = {name: sys.modules.get(name) for name in stub_names}

    config_stub = types.ModuleType("src.configs.config")
    logger_stub = types.ModuleType("src.configs.logger")
    llm_stub = types.ModuleType("src.models.LLM")
    base_table_stub = types.ModuleType("src.modules.latex_handler.latex_base_table_builder")
    module_utils_stub = types.ModuleType("src.modules.utils")

    config_stub.ADVANCED_CHATAGENT_MODEL = "advanced-test-model"
    config_stub.BASE_DIR = str(Path(__file__).resolve().parents[2])

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

    class LatexBaseTableBuilder:
        def __init__(self, *args, **kwargs):
            pass

    llm_stub.ChatAgent = ChatAgent
    base_table_stub.LatexBaseTableBuilder = LatexBaseTableBuilder
    module_utils_stub.load_prompt = lambda *args, **kwargs: "table prompt"
    module_utils_stub.load_file_as_string = lambda path: Path(path).read_text(
        encoding="utf-8"
    )
    module_utils_stub.load_single_file = lambda path: {}
    module_utils_stub.save_result = lambda content, path: Path(path).write_text(
        content, encoding="utf-8"
    )

    for package_name in [
        "src.configs",
        "src.models",
        "src.modules",
        "src.modules.latex_handler",
    ]:
        sys.modules[package_name] = types.ModuleType(package_name)
    sys.modules["src.configs.config"] = config_stub
    sys.modules["src.configs.logger"] = logger_stub
    sys.modules["src.models.LLM"] = llm_stub
    sys.modules["src.modules.latex_handler.latex_base_table_builder"] = base_table_stub
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


table_module = _load_table_builder_module()
LatexSurveyTableBuilder = table_module.LatexSurveyTableBuilder
SurveyTableType = table_module.SurveyTableType


class FakeNoRetryTableChatAgent:
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


def _minimal_builder(chat):
    builder = LatexSurveyTableBuilder.__new__(LatexSurveyTableBuilder)
    builder.chat_agent = chat
    builder.generated_tables = 0
    builder.MAX_SURVEY_TABLES = 4
    builder.table_router_prompt_path = Path("router.md")
    builder.survey_table_prompt_path = Path("survey_table.md")
    builder.main_body_path = Path("mainbody.tex")
    builder.outline_path = Path("outline.json")
    builder.survey_topic = "Function Calling"
    return builder


def test_route_table_types_uses_no_retry_and_defaults_on_error():
    chat = FakeNoRetryTableChatAgent("Error: Timeout after 180s")
    builder = _minimal_builder(chat)
    defaults = [
        {
            "table_type": "method_comparison",
            "target_section": "Core Methods",
            "description": "default method table",
            "priority": 1,
        }
    ]
    builder._extract_topic_from_outline = lambda: "Function Calling"
    builder._get_outline_summary = lambda: "outline"
    builder._get_content_summary = lambda: "content"
    builder._get_default_table_recommendations = lambda: defaults

    assert builder.route_table_types() == defaults
    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["model"] == "advanced-test-model"
    assert chat.no_retry_calls[0][1]["timeout"] <= 180


def test_generate_survey_table_uses_no_retry_and_returns_latex():
    chat = FakeNoRetryTableChatAgent(
        "\\begin{table}[t]\\centering\\caption{Methods}\\end{table}"
    )
    builder = _minimal_builder(chat)
    builder.extract_section_content = lambda path, section: "Section text \\cite{p1}."
    builder.extract_subsection_content = lambda path, section: None
    builder._extract_content_with_fallback = lambda section: None
    builder._extract_topic_from_outline = lambda: "Function Calling"
    builder._build_data_requirements = lambda section_content, table_type: "requirements"
    builder._extract_available_citations = lambda section_content: "\\cite{p1}"
    builder._get_style_for_table_type = lambda table_type: "professional"
    builder.extract_cite_name = lambda section_content: ["p1"]
    builder._extract_latex_from_response = lambda response: response
    builder._post_process_latex = lambda latex_code: latex_code
    builder._validate_and_fix_citations = lambda latex_code, citations: latex_code

    latex = builder.generate_survey_table(
        section_name="Core Methods",
        table_type=SurveyTableType.METHOD_COMPARISON,
    )

    assert chat.remote_calls == []
    assert len(chat.no_retry_calls) == 1
    assert chat.no_retry_calls[0][1]["model"] == "advanced-test-model"
    assert chat.no_retry_calls[0][1]["timeout"] <= 180
    assert "\\begin{table}" in latex
    assert builder.generated_tables == 1


def test_post_process_closes_malformed_multicolumn_header_rows():
    builder = _minimal_builder(FakeNoRetryTableChatAgent(""))
    bad = r"""
\begin{table}[h]
\centering
\begin{tabular}{lp{7.5cm}lc}
\toprule
\rowcolor{categorygreen} \multicolumn{4}{l}{\textbf{Foundational Challenges \& Motivation} \\
\midrule
A & B & C & D \\
\bottomrule
\end{tabular}
\end{table}
"""

    fixed = builder._post_process_latex(bad)

    assert r"\multicolumn{4}{l}{\textbf{Foundational Challenges \& Motivation}} \\" in fixed
    assert r"\textbf{Foundational Challenges \& Motivation} \\" not in fixed


def test_post_process_wraps_wide_tabular_in_resizebox():
    builder = _minimal_builder(FakeNoRetryTableChatAgent(""))
    wide = r"""
\begin{table}[h]
\centering
\caption{Wide table}
\begin{tabular}{lp{3.8cm}ccc p{4.2cm}c}
\toprule
A & B & C & D & E & F & G \\
\bottomrule
\end{tabular}
\end{table}
"""

    fixed = builder._post_process_latex(wide)

    assert r"\resizebox{\textwidth}{!}{%" in fixed
    assert fixed.count(r"\begin{tabular}") == 1
    assert r"\end{tabular}%" in fixed
