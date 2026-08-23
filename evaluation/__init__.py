"""
MEKG Survey Evaluation System
=============================

基于MEKG知识图谱的综述质量评估系统。

评测维度:
1. Reference Quality (引用质量) - 25%
2. Structural Soundness (结构完整性) - 20%
3. Content Integrity (内容完整性) - 25%
4. Ethics & Integrity (伦理与完整性) - 15%
5. Rich Media Quality (富媒体质量) - 15%

使用方法:
    from evaluation import MEKGSurveyEvaluator, EvaluationConfig
    
    evaluator = MEKGSurveyEvaluator(mekg_data, survey_path, config)
    result = evaluator.evaluate_all()
"""

from evaluation.config import EvaluationConfig
from evaluation.core.result import EvaluationResult
from evaluation.main import MEKGSurveyEvaluator

__all__ = [
    "EvaluationConfig",
    "EvaluationResult", 
    "MEKGSurveyEvaluator"
]

__version__ = "1.0.0"