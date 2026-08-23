"""
MEKG数据结构定义

定义了方法实体知识图谱的核心数据结构
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import networkx as nx


class RelationType(Enum):
    """
    边关系类型枚举
    
    借鉴NLP-AKG的关系分类体系,分为三大类:
    1. 论文间引用关系 (Inter-paper Citation Relations)
    2. 方法演进关系 (Method Evolution Relations)
    3. 共享实体关系 (Shared Entity Relations)
    """
    
    # ==================== 论文间引用关系 ====================
    # 基于引用上下文分析,将引用关系细分为以下类型
    
    CITES = "cites"  # A cites B (基础引用关系)
    DIRECT_USE = "direct_use"  # A直接使用B的内容(数据集、模型、代码、定义等)
    # 典型上下文: "we use the dataset from [X]", "following [X]'s implementation"
    
    EXTENDS = "extends"  # A扩展/改进了B的方法
    # 典型上下文: "we extend [X] by", "building upon [X]", "improve upon [X]"
    
    COMPARES = "compares"  # A与B进行比较(通常作为baseline)
    # 典型上下文: "compared with [X]", "outperforms [X]", "better than [X]"
    
    TASK_RELATED = "task_related"  # A与B处理相似任务
    # 典型上下文: "similar to [X]", "[X] also addresses this task"
    
    BACKGROUND = "background"  # B作为A的背景知识引用
    # 典型上下文: "related work", "previous studies show"
    
    # ==================== 方法演进关系 ====================
    # 基于方法属性分析
    
    EMPLOYS = "employs"  # A employs B (A采用了B方法)
    EVOLVED_FROM = "evolved_from"  # A evolved from B (A是B的演进版本)
    IS_APPLIED_TO = "is_applied_to"  # A is applied to B (A被应用于B领域)
    IS_FINE_TUNED_WITH = "is_fine_tuned_with"  # A is fine-tuned with B (A用B进行微调)
    IS_A_TYPE_OF = "is_a_type_of"  # A is a type of B (A是B的一种类型)
    
    # ==================== 共享实体关系 ====================
    # 基于共享的语义实体(Task, Dataset, Method等)
    
    SHARES_TASK = "shares_task"  # A和B处理相同任务
    SHARES_DATASET = "shares_dataset"  # A和B使用相同数据集
    SHARES_METHOD = "shares_method"  # A和B使用相同方法/技术
    SHARES_BASELINE = "shares_baseline"  # A和B在相同benchmark上比较
    
    @classmethod
    def citation_relations(cls) -> list:
        """获取所有引用相关的关系类型"""
        return [cls.CITES, cls.DIRECT_USE, cls.EXTENDS, cls.COMPARES, cls.TASK_RELATED, cls.BACKGROUND]
    
    @classmethod
    def method_relations(cls) -> list:
        """获取所有方法演进相关的关系类型"""
        return [cls.EMPLOYS, cls.EVOLVED_FROM, cls.IS_APPLIED_TO, cls.IS_FINE_TUNED_WITH, cls.IS_A_TYPE_OF]
    
    @classmethod
    def shared_entity_relations(cls) -> list:
        """获取所有共享实体相关的关系类型"""
        return [cls.SHARES_TASK, cls.SHARES_DATASET, cls.SHARES_METHOD, cls.SHARES_BASELINE]


@dataclass
class MEKGNode:
    """
    MEKG节点（论文/方法实体）
    
    Attributes:
        paper_id: 论文唯一标识符（OpenAlex ID）
        title: 论文标题
        abstract: 摘要
        authors: 作者列表
        year: 发表年份
        venue: 发表期刊/会议
        
        # 文献计量学属性
        citation_count: 引用次数
        
        # 图结构属性（由MEKGAnalyzer计算）
        pagerank: PageRank中心性（初始为None）
        betweenness_centrality: 介数中心性
        community_id: 所属社区ID
        
        # 方法实体属性（由LLM提取）
        method_entities: 论文中的核心方法/技术实体列表
        research_domain: 研究领域/应用场景
        
        # 额外元数据
        pdf_path: PDF文件路径
        md_path: Markdown解析结果路径
        doi: DOI
        url: 论文链接
    """
    
    # 基本标识
    paper_id: str
    title: str
    
    # 基本元数据
    abstract: str = ""
    authors: str = ""
    year: int = 0
    venue: str = ""
    
    # 文献计量学
    citation_count: int = 0
    
    # 图结构属性（初始为None，由analyzer计算）
    pagerank: Optional[float] = None
    betweenness_centrality: Optional[float] = None
    community_id: Optional[int] = None
    
    # 方法实体（由LLM提取）
    method_entities: List[str] = field(default_factory=list)
    research_domain: List[str] = field(default_factory=list)
    
    # 文件路径
    pdf_path: Optional[str] = None
    md_path: Optional[str] = None
    
    # 链接
    doi: Optional[str] = None
    url: Optional[str] = None
    
    # 其他元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "paper_id": self.paper_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "citation_count": self.citation_count,
            "pagerank": self.pagerank,
            "betweenness_centrality": self.betweenness_centrality,
            "community_id": self.community_id,
            "method_entities": self.method_entities,
            "research_domain": self.research_domain,
            "pdf_path": self.pdf_path,
            "md_path": self.md_path,
            "doi": self.doi,
            "url": self.url,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MEKGNode":
        """从字典创建节点"""
        return cls(
            paper_id=data["paper_id"],
            title=data["title"],
            abstract=data.get("abstract", ""),
            authors=data.get("authors", ""),
            year=data.get("year", 0),
            venue=data.get("venue", ""),
            citation_count=data.get("citation_count", 0),
            pagerank=data.get("pagerank"),
            betweenness_centrality=data.get("betweenness_centrality"),
            community_id=data.get("community_id"),
            method_entities=data.get("method_entities", []),
            research_domain=data.get("research_domain", []),
            pdf_path=data.get("pdf_path"),
            md_path=data.get("md_path"),
            doi=data.get("doi"),
            url=data.get("url"),
            metadata=data.get("metadata", {})
        )


@dataclass
class MEKGEdge:
    """
    MEKG边（方法间关系）
    
    Attributes:
        source: 源节点ID（paper_id）
        target: 目标节点ID（paper_id）
        relation_type: 关系类型
        confidence: 置信度 (0.0-1.0)
        
        # 融合信号
        llm_confidence: LLM推理的置信度
        citation_signal: 引用网络信号（是否有引用关系）
        bc_score: Betweenness Centrality Score（基于中介中心性）
        cc_score: Community Coherence Score（社区一致性）
        
        # 证据
        evidence: 支持该关系的文本证据（从论文中提取）
        extracted_from: 从哪篇论文中提取的关系
    """
    
    source: str
    target: str
    relation_type: RelationType
    
    # 置信度（融合后的最终置信度）
    confidence: float = 0.0
    
    # 分项置信度信号
    llm_confidence: float = 0.0
    citation_signal: float = 0.0  # 0.0或1.0（是否存在引用关系）
    bc_score: float = 0.0  # 基于介数中心性的分数
    cc_score: float = 0.0  # 基于社区的分数
    
    # 证据
    evidence: str = ""
    extracted_from: Optional[str] = None
    
    # 其他元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type.value,
            "confidence": self.confidence,
            "llm_confidence": self.llm_confidence,
            "citation_signal": self.citation_signal,
            "bc_score": self.bc_score,
            "cc_score": self.cc_score,
            "evidence": self.evidence,
            "extracted_from": self.extracted_from,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MEKGEdge":
        """从字典创建边"""
        return cls(
            source=data["source"],
            target=data["target"],
            relation_type=RelationType(data["relation_type"]),
            confidence=data.get("confidence", 0.0),
            llm_confidence=data.get("llm_confidence", 0.0),
            citation_signal=data.get("citation_signal", 0.0),
            bc_score=data.get("bc_score", 0.0),
            cc_score=data.get("cc_score", 0.0),
            evidence=data.get("evidence", ""),
            extracted_from=data.get("extracted_from"),
            metadata=data.get("metadata", {})
        )
    
    def calculate_confidence(
        self,
        llm_weight: float = 0.5,
        citation_weight: float = 0.2,
        bc_weight: float = 0.15,
        cc_weight: float = 0.15
    ) -> float:
        """
        融合多个信号计算最终置信度
        
        Args:
            llm_weight: LLM置信度权重
            citation_weight: 引用信号权重
            bc_weight: 介数中心性权重
            cc_weight: 社区一致性权重
        
        Returns:
            融合后的置信度 (0.0-1.0)
        """
        self.confidence = (
            llm_weight * self.llm_confidence +
            citation_weight * self.citation_signal +
            bc_weight * self.bc_score +
            cc_weight * self.cc_score
        )
        return self.confidence


class MEKGGraph:
    """
    MEKG图谱容器
    
    使用NetworkX DiGraph作为底层存储
    """
    
    def __init__(self):
        """初始化图谱"""
        self.graph = nx.DiGraph()
        self.nodes: Dict[str, MEKGNode] = {}
        self.edges: List[MEKGEdge] = []
    
    def add_node(self, node: MEKGNode):
        """添加节点"""
        self.nodes[node.paper_id] = node
        self.graph.add_node(
            node.paper_id,
            **node.to_dict()
        )
    
    def add_edge(self, edge: MEKGEdge):
        """添加边"""
        self.edges.append(edge)
        self.graph.add_edge(
            edge.source,
            edge.target,
            **edge.to_dict()
        )
    
    def get_node(self, paper_id: str) -> Optional[MEKGNode]:
        """获取节点"""
        return self.nodes.get(paper_id)
    
    def get_edges_from(self, paper_id: str) -> List[MEKGEdge]:
        """获取从指定节点出发的边"""
        return [
            edge for edge in self.edges
            if edge.source == paper_id
        ]
    
    def get_edges_to(self, paper_id: str) -> List[MEKGEdge]:
        """获取指向指定节点的边"""
        return [
            edge for edge in self.edges
            if edge.target == paper_id
        ]
    
    def get_neighbors(self, paper_id: str) -> Set[str]:
        """获取邻居节点ID集合（不考虑方向）"""
        predecessors = set(self.graph.predecessors(paper_id))
        successors = set(self.graph.successors(paper_id))
        return predecessors | successors
    
    def node_count(self) -> int:
        """节点数量"""
        return len(self.nodes)
    
    def edge_count(self) -> int:
        """边数量"""
        return len(self.edges)
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典格式"""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "statistics": {
                "node_count": self.node_count(),
                "edge_count": self.edge_count()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MEKGGraph":
        """从字典加载图谱"""
        graph = cls()
        
        # 加载节点
        for node_data in data.get("nodes", []):
            node = MEKGNode.from_dict(node_data)
            graph.add_node(node)
        
        # 加载边
        for edge_data in data.get("edges", []):
            edge = MEKGEdge.from_dict(edge_data)
            graph.add_edge(edge)
        
        return graph
    
    def save_to_file(self, filepath: str):
        """保存图谱到JSON文件"""
        import json
        from pathlib import Path
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> "MEKGGraph":
        """从JSON文件加载图谱"""
        import json
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return cls.from_dict(data)