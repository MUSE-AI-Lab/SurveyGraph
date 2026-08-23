"""
MEKG - Methods-Entity Knowledge Graph (方法实体知识图谱)

一个基于方法实体的学术知识图谱系统，用于替代传统的RAG向量召回方案，
通过结构化的知识图谱分析来生成更有逻辑性的综述大纲。

核心功能:
- 大规模论文处理 (1000-2000篇)
- 深度语义理解 (8大类论文属性)
- 结构化大纲生成 (基于社区发现和演进路径)
- 高效并发处理 (50线程并发)

模块结构:
- core: 核心数据结构和分析器
- extraction: 实体和关系抽取
- processing: 数据处理 (PDF解析、实体清洗等)
- storage: 存储层 (SQLite、Memgraph、Kuzu)
- analysis: 图谱分析 (社区发现、中心性计算等)
- automation: 自动化构建
- visualization: 可视化
"""

__version__ = "3.0.0"
__author__ = "MEKG Team"

# 核心模块导出
from mekg.src.core.data_structures import (
    MEKGGraph,
    MEKGNode,
    MEKGEdge,
    RelationType,
)
from mekg.src.core.analyzer import MEKGAnalyzer

# 抽取模块导出
from mekg.src.extraction.semantic_entity_extractor import (
    SemanticEntityExtractor,
    SemanticEntity,
    SemanticEntityType,
    PaperSemanticEntities,
)

# 存储模块导出
from mekg.src.storage.semantic_entity_db import SemanticEntityDB

# Survey生成模块导出
from mekg.src.survey.outline_generator import (
    MEKGOutlineGenerator,
    SurveyOutline,
    OutlineSection,
)
from mekg.src.survey.content_generator import (
    MEKGContentGenerator,
    PaperInfo,
)
from mekg.src.survey.evaluator import (
    MEKGEvaluator,
    EvaluationResult,
)
from mekg.src.survey.pipeline import (
    MEKGSurveyPipeline,
    PipelineConfig,
    PipelineResult,
    run_pipeline,
    create_pipeline,
)

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    # 核心类
    "MEKGGraph",
    "MEKGNode",
    "MEKGEdge",
    "RelationType",
    "MEKGAnalyzer",
    # 抽取类
    "SemanticEntityExtractor",
    "SemanticEntity",
    "SemanticEntityType",
    "PaperSemanticEntities",
    # 存储类
    "SemanticEntityDB",
    # Survey生成类
    "MEKGOutlineGenerator",
    "SurveyOutline",
    "OutlineSection",
    "MEKGContentGenerator",
    "PaperInfo",
    "MEKGEvaluator",
    "EvaluationResult",
    "MEKGSurveyPipeline",
    "PipelineConfig",
    "PipelineResult",
    "run_pipeline",
    "create_pipeline",
]