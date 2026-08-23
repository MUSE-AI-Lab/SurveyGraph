"""
大纲生成模块
"""

from src.modules.outline.hybrid_outline_generator import (
    HybridOutlineGenerator,
    HybridOutline,
    OutlineSection,
    generate_hybrid_outline
)

__all__ = [
    "HybridOutlineGenerator",
    "HybridOutline",
    "OutlineSection",
    "generate_hybrid_outline"
]