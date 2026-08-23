"""
分析模块
"""

from src.modules.analysis.evolutionary_analyzer import (
    EvolutionaryAnalyzer,
    EvolutionaryAnalysis,
    Milestone,
    EvolutionPhase,
    TrendPrediction,
    analyze_evolution
)

__all__ = [
    "EvolutionaryAnalyzer",
    "EvolutionaryAnalysis",
    "Milestone",
    "EvolutionPhase",
    "TrendPrediction",
    "analyze_evolution"
]