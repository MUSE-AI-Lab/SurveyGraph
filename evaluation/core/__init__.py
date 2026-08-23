"""
核心模块
========

包含评测器基类和结果数据结构。
"""

from evaluation.core.base_evaluator import BaseEvaluator
from evaluation.core.result import EvaluationResult, DimensionResult

__all__ = [
    "BaseEvaluator",
    "EvaluationResult",
    "DimensionResult"
]