"""
评测系统配置
============

包含API配置、模型配置、权重配置等。

多模型评测说明：
- 可视化相关评测（如图表质量）使用 advanced_model（多模态模型）
- 其他文本评测可使用多个 t2t 模型进行评测，然后融合结果
- 支持的融合策略：majority_vote（多数投票）、average（平均）、weighted_average（加权平均）
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from pathlib import Path
import os


def _normalize_openai_base_url(url: str) -> str:
    """
    Normalize an OpenAI-compatible base URL.

    - If the URL points to `/chat/completions`, strip that suffix.
    - Trim trailing slashes.

    The OpenAI Python SDK expects `base_url` like `http://host:port/v1`.
    """
    if not url:
        return url

    normalized = str(url).strip()
    normalized = normalized.rstrip("/")

    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]

    return normalized.rstrip("/")


# ==================== API 配置 ====================

# LLM API 配置
try:
    from src.configs.config import (
        REMOTE_URL as _PROJECT_REMOTE_URL,
        TOKEN as _PROJECT_TOKEN,
        DEFAULT_CHATAGENT_MODEL as _PROJECT_DEFAULT_MODEL,
        ADVANCED_CHATAGENT_MODEL as _PROJECT_ADVANCED_MODEL,
        EVAL_TEXT_MODEL as _PROJECT_EVAL_TEXT_MODEL,
    )
except Exception:
    _PROJECT_REMOTE_URL = ""
    _PROJECT_TOKEN = ""
    _PROJECT_DEFAULT_MODEL = ""
    _PROJECT_ADVANCED_MODEL = ""
    _PROJECT_EVAL_TEXT_MODEL = ""

REMOTE_URL = _normalize_openai_base_url(_PROJECT_REMOTE_URL) or "https://api.openai.com/v1"
API_KEY = _PROJECT_TOKEN  # 优先使用项目 src/configs/config.py 的 TOKEN

# 模型配置（与项目主流程保持一致）
DEFAULT_MODEL = _PROJECT_DEFAULT_MODEL or "gpt-4o-mini"
ADVANCED_MODEL = _PROJECT_ADVANCED_MODEL or DEFAULT_MODEL


def _split_model_list(raw: str) -> List[str]:
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _unique_keep_order(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _default_t2t_models() -> List[str]:
    explicit = os.getenv("EVALUATION_T2T_MODELS", "").strip()
    if explicit:
        return _unique_keep_order(_split_model_list(explicit))

    candidates = [
        _PROJECT_DEFAULT_MODEL,
        _PROJECT_ADVANCED_MODEL,
        _PROJECT_EVAL_TEXT_MODEL,
    ]
    models = _unique_keep_order([model for model in candidates if model])
    return models or [DEFAULT_MODEL]


def _default_model_weights(models: List[str]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for model in models:
        weight = 1.0
        lower = model.lower()
        if "thinking" in lower:
            weight = 1.2
        elif "glm" in lower:
            weight = 1.1
        weights[model] = weight
    return weights

# ==================== 多模型评测配置 ====================

# T2T（Text-to-Text）评测模型列表
# 这些模型只支持文本输入输出，用于非可视化评测
T2T_EVALUATION_MODELS = _default_t2t_models()

# 多模态评测模型（用于可视化相关评测，如图表质量评估）
# 保持使用 advanced_model，因为需要处理图像
MULTIMODAL_EVALUATION_MODEL = ADVANCED_MODEL

# 融合策略配置
class FusionStrategy:
    """融合策略枚举"""
    MAJORITY_VOTE = "majority_vote"      # 多数投票（适用于分类/布尔判断）
    AVERAGE = "average"                   # 简单平均（适用于数值评分）
    WEIGHTED_AVERAGE = "weighted_average" # 加权平均（根据模型可靠性加权）
    MEDIAN = "median"                     # 中位数（抗异常值）
    MAX_CONFIDENCE = "max_confidence"     # 选择置信度最高的结果

# 默认融合策略
DEFAULT_FUSION_STRATEGY = FusionStrategy.AVERAGE

# 模型权重配置（用于加权平均融合）
# 权重越高表示该模型的评测结果越可信
MODEL_WEIGHTS = _default_model_weights(T2T_EVALUATION_MODELS)

# 多模型评测的最小模型数量（低于此数量则回退到单模型）
MIN_MODELS_FOR_FUSION = 2

# 多模型评测超时配置（每个模型的超时时间）
MULTI_MODEL_TIMEOUT = 60  # 秒（从120秒降低到60秒，避免长时间等待）

# LLM 参数
TEMPERATURE = 0.0
MAX_RETRIES = 3
TIMEOUT = 180  # 评测环节LLM调用超时时间（秒）

# ==================== 评测权重配置 ====================

DEFAULT_DIMENSION_WEIGHTS = {
    "reference_quality": 0.25,
    "structural_soundness": 0.20,
    "content_integrity": 0.25,
    "ethics_integrity": 0.15,
    "rich_media_quality": 0.15
}

# 各维度内部指标权重
REFERENCE_QUALITY_WEIGHTS = {
    "wcr": 0.30,                    # Weighted Centrality Recall
    "cc": 0.25,                     # Community Coverage
    "bibliographic_integrity": 0.25, # 文献完整性
    "citation_faithfulness": 0.20   # 引用忠实度
}

STRUCTURAL_SOUNDNESS_WEIGHTS = {
    "sc": 0.40,                     # Structural Coherence
    "structural_completeness": 0.30, # 结构完整性
    "content_structure_fidelity": 0.30  # 内容-结构一致性
}

CONTENT_INTEGRITY_WEIGHTS = {
    "general_factualness": 0.20,    # 通用事实性
    "writing_quality": 0.20,        # 写作质量
    "scholarly_depth": 0.20,        # 学术深度
    "tc": 0.20,                     # Temporal Coverage
    "rubric_score": 0.20            # 基于评分细则的综合评估（参考 ARISE）
}

ETHICS_INTEGRITY_WEIGHTS = {
    "originality": 0.70,            # 原创性 - 提高权重，这是综述最核心的伦理要求
    "societal_impact": 0.15,        # 社会影响 - 降低权重，技术综述不强制要求
    "fairness": 0.15                # 公平性 - 降低权重，技术综述不强制要求
}

RICH_MEDIA_QUALITY_WEIGHTS = {
    "figure_quality": 0.30,         # 图片质量
    "table_quality": 0.30,          # 表格质量
    "visual_content_alignment": 0.25, # 视觉-内容对齐
    "resource_accessibility": 0.15  # 资源可访问性
}


@dataclass
class EvaluationConfig:
    """评测配置类"""
    
    # LLM 配置
    use_llm: bool = True
    llm_model: str = DEFAULT_MODEL
    advanced_model: str = ADVANCED_MODEL
    api_url: str = REMOTE_URL
    api_key: str = API_KEY
    temperature: float = TEMPERATURE
    max_retries: int = MAX_RETRIES
    timeout: int = TIMEOUT
    
    # 多模型评测配置
    use_multi_model: bool = True                    # 是否启用多模型评测
    t2t_models: List[str] = field(
        default_factory=lambda: T2T_EVALUATION_MODELS.copy()
    )
    multimodal_model: str = MULTIMODAL_EVALUATION_MODEL  # 多模态评测模型
    fusion_strategy: str = DEFAULT_FUSION_STRATEGY       # 融合策略
    model_weights: Dict[str, float] = field(
        default_factory=lambda: MODEL_WEIGHTS.copy()
    )
    min_models_for_fusion: int = MIN_MODELS_FOR_FUSION   # 最小融合模型数
    multi_model_timeout: int = MULTI_MODEL_TIMEOUT       # 多模型超时时间
    
    # 评测配置
    dimension_weights: Dict[str, float] = field(
        default_factory=lambda: DEFAULT_DIMENSION_WEIGHTS.copy()
    )
    
    # 采样配置
    factual_sample_size: int = 30      # 事实验证采样数
    content_sample_size: int = 5       # 内容评估采样数
    
    # 输出配置
    save_intermediate: bool = True     # 保存中间结果
    generate_report: bool = True       # 生成报告
    report_format: str = "markdown"    # 报告格式: markdown, json, html
    
    # 并发配置
    max_workers: int = 10              # 最大并发数
    
    # 调试配置
    verbose: bool = False              # 详细输出
    debug: bool = False                # 调试模式
    
    def validate(self) -> bool:
        """验证配置有效性"""
        # 检查权重和为1
        total_weight = sum(self.dimension_weights.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"维度权重之和应为1.0，当前为{total_weight}")
        
        # 检查API配置
        if self.use_llm and not self.api_key:
            import os
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
            if not self.api_key:
                raise ValueError("使用LLM时需要设置API_KEY")
        
        return True
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> "EvaluationConfig":
        """从字典创建配置"""
        return cls(**{
            k: v for k, v in config_dict.items()
            if k in cls.__dataclass_fields__
        })
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "use_llm": self.use_llm,
            "llm_model": self.llm_model,
            "advanced_model": self.advanced_model,
            "use_multi_model": self.use_multi_model,
            "t2t_models": self.t2t_models,
            "multimodal_model": self.multimodal_model,
            "fusion_strategy": self.fusion_strategy,
            "dimension_weights": self.dimension_weights,
            "factual_sample_size": self.factual_sample_size,
            "content_sample_size": self.content_sample_size,
            "max_workers": self.max_workers,
            "verbose": self.verbose
        }
    
    def get_available_t2t_models(self) -> List[str]:
        """获取可用的 T2T 模型列表"""
        return self.t2t_models if self.use_multi_model else [self.llm_model]
    
    def should_use_multi_model(self) -> bool:
        """判断是否应该使用多模型评测"""
        return (
            self.use_multi_model and
            self.use_llm and
            len(self.t2t_models) >= self.min_models_for_fusion
        )


# ==================== 预设配置 ====================

# 快速评测配置（不使用LLM）
FAST_CONFIG = EvaluationConfig(
    use_llm=False,
    use_multi_model=False,
    factual_sample_size=0,
    content_sample_size=0,
    verbose=False
)

# 完整评测配置（启用多模型）
FULL_CONFIG = EvaluationConfig(
    use_llm=True,
    use_multi_model=True,
    llm_model=ADVANCED_MODEL,
    fusion_strategy=FusionStrategy.WEIGHTED_AVERAGE,
    factual_sample_size=50,
    content_sample_size=10,
    verbose=True
)

# 单模型评测配置（不使用多模型融合）
SINGLE_MODEL_CONFIG = EvaluationConfig(
    use_llm=True,
    use_multi_model=False,
    llm_model=ADVANCED_MODEL,
    factual_sample_size=30,
    content_sample_size=5,
    verbose=False
)

# 开发测试配置
DEV_CONFIG = EvaluationConfig(
    use_llm=True,
    use_multi_model=True,
    llm_model=DEFAULT_MODEL,
    fusion_strategy=FusionStrategy.AVERAGE,
    factual_sample_size=10,
    content_sample_size=3,
    verbose=True,
    debug=True
)

# 多模型评测配置（使用所有 T2T 模型）
MULTI_MODEL_CONFIG = EvaluationConfig(
    use_llm=True,
    use_multi_model=True,
    fusion_strategy=FusionStrategy.WEIGHTED_AVERAGE,
    factual_sample_size=30,
    content_sample_size=5,
    verbose=True
)
