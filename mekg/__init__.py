"""
MEKG - Methods-Entity Knowledge Graph (方法实体知识图谱)

一个基于方法实体的学术知识图谱系统。

快速开始:
    from mekg import MEKGGraph, MEKGAnalyzer, SemanticEntityDB
    
    # 创建图谱
    graph = MEKGGraph()
    
    # 连接数据库
    db = SemanticEntityDB("./mekg.db")
    
    # 分析图谱
    analyzer = MEKGAnalyzer(graph)
"""

from mekg.src import (
    __version__,
    __author__,
    MEKGGraph,
    MEKGNode,
    MEKGEdge,
    RelationType,
    MEKGAnalyzer,
    SemanticEntityExtractor,
    SemanticEntity,
    SemanticEntityType,
    PaperSemanticEntities,
    SemanticEntityDB,
)

__all__ = [
    "__version__",
    "__author__",
    "MEKGGraph",
    "MEKGNode",
    "MEKGEdge",
    "RelationType",
    "MEKGAnalyzer",
    "SemanticEntityExtractor",
    "SemanticEntity",
    "SemanticEntityType",
    "PaperSemanticEntities",
    "SemanticEntityDB",
]