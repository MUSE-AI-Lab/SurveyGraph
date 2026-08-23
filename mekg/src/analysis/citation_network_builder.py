"""
引文网络构建器

第一阶段核心组件：构建基于直接引用关系的引文网络
不依赖LLM，使用结构化的API数据（OpenAlex）

主要功能：
1. 从论文池中提取引用关系
2. 构建有向引文网络图
3. 计算同被引强度和文献耦合度
"""

import asyncio
from typing import List, Dict, Any, Set, Tuple, Optional
from collections import defaultdict
import math

import networkx as nx
from loguru import logger


class CitationNetworkBuilder:
    """
    引文网络构建器
    
    基于OpenAlex等API提供的结构化引用数据，
    构建一个客观的、不依赖LLM的引文网络。
    """
    
    def __init__(self):
        """初始化构建器"""
        self.citation_graph = nx.DiGraph()  # 有向引文图
        self.papers_index: Dict[str, Dict[str, Any]] = {}  # paper_id -> paper_data
        self.reference_map: Dict[str, Set[str]] = defaultdict(set)  # paper -> papers it cites
        self.cited_by_map: Dict[str, Set[str]] = defaultdict(set)  # paper -> papers that cite it
        
    def build_from_papers(
        self,
        papers: List[Dict[str, Any]],
        include_external: bool = False
    ) -> nx.DiGraph:
        """
        从论文列表构建引文网络
        
        Args:
            papers: 论文列表，每篇论文需要包含references和cited_by字段
            include_external: 是否包含池外论文（仅引用，但不在我们的论文池中）
        
        Returns:
            有向引文网络图
        """
        logger.info(f"开始构建引文网络: {len(papers)} 篇论文")
        
        # 步骤1: 建立论文索引
        for paper in papers:
            paper_id = paper.get('paper_id') or paper.get('id')
            if paper_id:
                self.papers_index[paper_id] = paper
                
        logger.info(f"论文索引建立完成: {len(self.papers_index)} 篇")
        
        # 步骤2: 添加所有节点
        for paper_id, paper in self.papers_index.items():
            self.citation_graph.add_node(
                paper_id,
                title=paper.get('title', ''),
                year=paper.get('year', 0),
                citations=paper.get('citations', paper.get('citation_count', 0)),
                abstract=paper.get('abstract', '')[:500],  # 截断以节省内存
                venue=paper.get('venue', ''),
                in_pool=True  # 标记为池内论文
            )
        
        # 步骤3: 构建引用关系
        edges_added = 0
        external_nodes_added = 0
        
        for paper_id, paper in self.papers_index.items():
            # 提取该论文的参考文献
            references = self._extract_references(paper)
            
            for ref_id in references:
                # 检查参考文献是否在我们的论文池中
                if ref_id in self.papers_index:
                    # 池内引用：直接添加边
                    self.citation_graph.add_edge(paper_id, ref_id, weight=1.0)
                    self.reference_map[paper_id].add(ref_id)
                    self.cited_by_map[ref_id].add(paper_id)
                    edges_added += 1
                elif include_external:
                    # 池外引用：添加占位节点
                    if ref_id not in self.citation_graph:
                        self.citation_graph.add_node(
                            ref_id,
                            title='Unknown (External)',
                            year=0,
                            citations=0,
                            in_pool=False
                        )
                        external_nodes_added += 1
                    self.citation_graph.add_edge(paper_id, ref_id, weight=0.5)
                    self.reference_map[paper_id].add(ref_id)
                    self.cited_by_map[ref_id].add(paper_id)
                    edges_added += 1
        
        logger.info(
            f"引文网络构建完成: "
            f"节点={self.citation_graph.number_of_nodes()}, "
            f"边={edges_added}, "
            f"池内边密度={self._calculate_density():.6f}"
        )
        
        if external_nodes_added > 0:
            logger.info(f"添加了 {external_nodes_added} 个池外参考文献节点")
        
        return self.citation_graph
    
    def _extract_references(self, paper: Dict[str, Any]) -> List[str]:
        """
        从论文数据中提取参考文献ID列表
        
        支持多种格式：
        - OpenAlex格式: referenced_works = ["https://openalex.org/W123", ...]
        - 简化格式: references = ["W123", ...]
        - Semantic Scholar格式: references = [{"paperId": "xxx"}, ...]
        """
        references = []
        
        # 尝试OpenAlex格式
        if 'referenced_works' in paper:
            for ref in paper['referenced_works']:
                if isinstance(ref, str):
                    # 提取ID部分
                    if 'openalex.org/' in ref:
                        ref_id = ref.split('/')[-1]
                    else:
                        ref_id = ref
                    references.append(ref_id)
        
        # 尝试简化格式
        elif 'references' in paper:
            refs = paper['references']
            if isinstance(refs, list):
                for ref in refs:
                    if isinstance(ref, str):
                        references.append(ref)
                    elif isinstance(ref, dict):
                        # Semantic Scholar格式
                        ref_id = ref.get('paperId') or ref.get('paper_id') or ref.get('id')
                        if ref_id:
                            references.append(ref_id)
        
        return references
    
    def _calculate_density(self) -> float:
        """计算图的密度"""
        n = self.citation_graph.number_of_nodes()
        if n <= 1:
            return 0.0
        m = self.citation_graph.number_of_edges()
        return m / (n * (n - 1))
    
    def compute_bibliographic_coupling(
        self,
        min_coupling_strength: int = 2
    ) -> List[Tuple[str, str, int]]:
        """
        计算文献耦合度
        
        文献耦合：如果两篇论文引用了相同的参考文献，它们之间存在文献耦合。
        耦合强度 = 共同引用的参考文献数量
        
        Args:
            min_coupling_strength: 最小耦合强度阈值
        
        Returns:
            耦合对列表: [(paper_a, paper_b, strength), ...]
        """
        logger.info("计算文献耦合度...")
        
        coupling_pairs = []
        papers = list(self.reference_map.keys())
        
        for i, paper_a in enumerate(papers):
            refs_a = self.reference_map[paper_a]
            if not refs_a:
                continue
                
            for paper_b in papers[i+1:]:
                refs_b = self.reference_map[paper_b]
                if not refs_b:
                    continue
                
                # 计算共同引用数
                common_refs = refs_a & refs_b
                coupling_strength = len(common_refs)
                
                if coupling_strength >= min_coupling_strength:
                    coupling_pairs.append((paper_a, paper_b, coupling_strength))
        
        logger.info(f"发现 {len(coupling_pairs)} 对文献耦合（阈值={min_coupling_strength}）")
        return coupling_pairs
    
    def compute_cocitation_strength(
        self,
        min_cocitation_strength: int = 2
    ) -> List[Tuple[str, str, int]]:
        """
        计算同被引强度
        
        同被引：如果两篇论文同时被其他论文引用，它们之间存在同被引关系。
        同被引强度 = 共同的施引论文数量
        
        Args:
            min_cocitation_strength: 最小同被引强度阈值
        
        Returns:
            同被引对列表: [(paper_a, paper_b, strength), ...]
        """
        logger.info("计算同被引强度...")
        
        cocitation_pairs = []
        papers = list(self.cited_by_map.keys())
        
        for i, paper_a in enumerate(papers):
            citers_a = self.cited_by_map[paper_a]
            if not citers_a:
                continue
                
            for paper_b in papers[i+1:]:
                citers_b = self.cited_by_map[paper_b]
                if not citers_b:
                    continue
                
                # 计算共同施引论文数
                common_citers = citers_a & citers_b
                cocitation_strength = len(common_citers)
                
                if cocitation_strength >= min_cocitation_strength:
                    cocitation_pairs.append((paper_a, paper_b, cocitation_strength))
        
        logger.info(f"发现 {len(cocitation_pairs)} 对同被引（阈值={min_cocitation_strength}）")
        return cocitation_pairs
    
    def get_network_statistics(self) -> Dict[str, Any]:
        """
        获取引文网络的统计信息
        
        Returns:
            网络统计字典
        """
        if self.citation_graph.number_of_nodes() == 0:
            return {"error": "网络为空"}
        
        # 计算连通分量
        weakly_connected = list(nx.weakly_connected_components(self.citation_graph))
        strongly_connected = list(nx.strongly_connected_components(self.citation_graph))
        
        # 计算度分布
        in_degrees = [d for n, d in self.citation_graph.in_degree()]
        out_degrees = [d for n, d in self.citation_graph.out_degree()]
        
        stats = {
            "num_nodes": self.citation_graph.number_of_nodes(),
            "num_edges": self.citation_graph.number_of_edges(),
            "density": self._calculate_density(),
            "num_weakly_connected_components": len(weakly_connected),
            "largest_wcc_size": max(len(c) for c in weakly_connected) if weakly_connected else 0,
            "num_strongly_connected_components": len(strongly_connected),
            "largest_scc_size": max(len(c) for c in strongly_connected) if strongly_connected else 0,
            "avg_in_degree": sum(in_degrees) / len(in_degrees) if in_degrees else 0,
            "avg_out_degree": sum(out_degrees) / len(out_degrees) if out_degrees else 0,
            "max_in_degree": max(in_degrees) if in_degrees else 0,
            "max_out_degree": max(out_degrees) if out_degrees else 0,
            "avg_references_per_paper": sum(len(refs) for refs in self.reference_map.values()) / len(self.reference_map) if self.reference_map else 0,
        }
        
        return stats
    
    def get_citation_graph(self) -> nx.DiGraph:
        """获取构建的引文网络图"""
        return self.citation_graph
    
    def get_papers_index(self) -> Dict[str, Dict[str, Any]]:
        """获取论文索引"""
        return self.papers_index
    
    def get_reference_map(self) -> Dict[str, Set[str]]:
        """获取引用映射"""
        return self.reference_map
    
    def get_cited_by_map(self) -> Dict[str, Set[str]]:
        """获取被引映射"""
        return self.cited_by_map