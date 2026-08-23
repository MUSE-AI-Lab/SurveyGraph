"""
多模态文档解析模块

提供PDF解析、图片分析、图片插入、动态视觉元素生成和AI生图功能。
"""

from src.modules.multimodal.mineru_parser import MinerUParser
from src.modules.multimodal.image_analyzer import ImageAnalyzer
from src.modules.multimodal.image_insertion import ImageInsertion
from src.modules.multimodal.dynamic_visual_generator import (
    DynamicVisualGenerator,
    VisualElementType,
    VisualElementDecision,
    ReferenceImage,
    ExistingVisualElement
)
from src.modules.multimodal.ai_image_generator import (
    AIImageGenerator,
    GeneratedImage,
    ImageGenerationDecision
)

__all__ = [
    "MinerUParser",
    "ImageAnalyzer",
    "ImageInsertion",
    "DynamicVisualGenerator",
    "VisualElementType",
    "VisualElementDecision",
    "ReferenceImage",
    "ExistingVisualElement",
    "AIImageGenerator",
    "GeneratedImage",
    "ImageGenerationDecision"
]