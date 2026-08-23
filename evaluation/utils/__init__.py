"""
工具函数模块
============

包含LaTeX解析、LLM调用、指标计算等工具函数。
"""

from evaluation.utils.latex_parser import (
    extract_citations,
    extract_text_from_latex,
    extract_outline_from_latex,
    extract_figures_and_tables,
    resolve_latex_inputs
)

from evaluation.utils.llm_client import (
    call_llm,
    parse_json_response,
    LLMClient
)

from evaluation.utils.metrics import (
    calculate_recall,
    calculate_precision,
    calculate_f1,
    normalize_title
)

__all__ = [
    # LaTeX解析
    "extract_citations",
    "extract_text_from_latex",
    "extract_outline_from_latex",
    "extract_figures_and_tables",
    "resolve_latex_inputs",
    
    # LLM调用
    "call_llm",
    "parse_json_response",
    "LLMClient",
    
    # 指标计算
    "calculate_recall",
    "calculate_precision",
    "calculate_f1",
    "normalize_title"
]