"""
MEKG Analysis Module - 图谱分析

包含:
- CommunityLabeler: 社区标注器 (Louvain/Leiden算法)
- CorePaperDiscoverer: 核心论文发现器
- CitationNetworkBuilder: 引用网络构建器
- IGraphAdapter: igraph适配器 (高性能图算法)
- EvaluationMetrics: 评估指标 (WCR, CC, SC)
"""

from mekg.src.analysis.community_labeler import CommunityLabeler
from mekg.src.analysis.core_paper_discoverer import CorePaperDiscoverer
from mekg.src.analysis.citation_network_builder import CitationNetworkBuilder
from mekg.src.analysis.evaluation_metrics import MEKGEvaluationMetrics as EvaluationMetrics

# 可选导入 (需要igraph)
try:
    from mekg.src.analysis.igraph_adapter import IGraphAdapter, IGRAPH_AVAILABLE
except ImportError:
    IGraphAdapter = None
    IGRAPH_AVAILABLE = False

__all__ = [
    "CommunityLabeler",
    "CorePaperDiscoverer",
    "CitationNetworkBuilder",
    "EvaluationMetrics",
    "IGraphAdapter",
    "IGRAPH_AVAILABLE",
]