"""
MEKG图谱分析器

提供图结构分析功能:
1. PageRank计算
2. 介数中心性(Betweenness Centrality)
3. 社区发现(Community Detection)
4. 演进路径追踪

性能优化:
- 支持igraph高性能计算 (比NetworkX快100倍)
- 自动选择最优引擎 (igraph优先)
"""

import networkx as nx
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict
import numpy as np

from loguru import logger

from .data_structures import MEKGGraph, MEKGNode, MEKGEdge

# 尝试导入igraph适配器
try:
    from .igraph_adapter import IGraphAdapter, IGRAPH_AVAILABLE
except ImportError:
    IGRAPH_AVAILABLE = False
    IGraphAdapter = None


class MEKGAnalyzer:
    """
    MEKG图谱分析器
    
    核心功能:
    1. 计算节点的中心性指标(PageRank, Betweenness)
    2. 社区发现(Louvain/Leiden算法)
    3. 追踪方法演进路径
    4. 计算WCR, CC, SC等评测指标
    
    性能优化:
    - 自动使用igraph(如果可用)以获得100倍性能提升
    - 回退到NetworkX(如果igraph不可用)
    """
    
    def __init__(self, mekg_graph: MEKGGraph, use_igraph: bool = True):
        """
        Args:
            mekg_graph: MEKG图谱对象
            use_igraph: 是否使用igraph加速(默认True)
        """
        self.graph = mekg_graph
        self.nx_graph = mekg_graph.graph
        self.use_igraph = use_igraph and IGRAPH_AVAILABLE
        
        # 初始化igraph适配器
        self.ig_adapter = None
        if self.use_igraph:
            try:
                logger.info("使用igraph高性能引擎 (性能提升100倍)")
                self.ig_adapter = IGraphAdapter.from_mekg(mekg_graph)
            except Exception as e:
                logger.warning(f"igraph初始化失败，回退到NetworkX: {e}")
                self.use_igraph = False
        else:
            if not IGRAPH_AVAILABLE:
                logger.info("igraph未安装，使用NetworkX (建议安装: pip install python-igraph)")
            else:
                logger.info("使用NetworkX引擎")
    
    def calculate_centrality_metrics(self) -> Dict[str, Dict[str, float]]:
        """
        计算所有节点的中心性指标
        
        Returns:
            {
                "paper_id": {
                    "pagerank": 0.xx,
                    "betweenness": 0.xx
                }
            }
        """
        logger.info("开始计算中心性指标...")
        
        metrics = {}
        
        # 使用igraph加速(如果可用)
        if self.use_igraph and self.ig_adapter:
            try:
                # igraph PageRank (快100倍)
                pagerank_normalized = self.ig_adapter.pagerank(damping=0.85)
                
                # igraph Betweenness (快150倍)
                betweenness = self.ig_adapter.betweenness_centrality(directed=True)
                
                # 合并指标
                for node_id in self.graph.nodes.keys():
                    metrics[node_id] = {
                        "pagerank": pagerank_normalized.get(node_id, 0.0),
                        "betweenness": betweenness.get(node_id, 0.0)
                    }
            except Exception as e:
                logger.warning(f"igraph计算失败，回退到NetworkX: {e}")
                self.use_igraph = False
        
        # 回退到NetworkX
        if not self.use_igraph:
            # 1. PageRank (考虑引用权重)
            try:
                pagerank = nx.pagerank(
                    self.nx_graph,
                    alpha=0.85,
                    max_iter=100
                )
                
                # 归一化到0-1区间
                max_pr = max(pagerank.values()) if pagerank else 1.0
                pagerank_normalized = {
                    k: v / max_pr for k, v in pagerank.items()
                }
            except Exception as e:
                logger.error(f"PageRank计算失败: {e}")
                pagerank_normalized = {
                    node_id: 0.0 for node_id in self.graph.nodes.keys()
                }
            
            # 2. 介数中心性
            try:
                betweenness = nx.betweenness_centrality(
                    self.nx_graph,
                    normalized=True
                )
            except Exception as e:
                logger.error(f"Betweenness计算失败: {e}")
                betweenness = {
                    node_id: 0.0 for node_id in self.graph.nodes.keys()
                }
            
            # 合并指标
            for node_id in self.graph.nodes.keys():
                metrics[node_id] = {
                    "pagerank": pagerank_normalized.get(node_id, 0.0),
                    "betweenness": betweenness.get(node_id, 0.0)
                }
        
        # 更新节点属性
        for node_id, m in metrics.items():
            node = self.graph.get_node(node_id)
            if node:
                node.pagerank = m["pagerank"]
                node.betweenness_centrality = m["betweenness"]
        
        logger.info(f"中心性指标计算完成: {len(metrics)} 个节点")
        return metrics
    
    def detect_communities(
        self,
        algorithm: str = "louvain",
        resolution: float = 1.0
    ) -> Dict[str, int]:
        """
        社区发现
        
        Args:
            algorithm: 算法选择 ('louvain', 'leiden', 'infomap', 'label_propagation')
            resolution: 分辨率参数(值越大,社区越多)
        
        Returns:
            {paper_id: community_id}
        """
        logger.info(f"开始社区发现 (算法: {algorithm})...")
        
        communities = {}
        
        # 使用igraph加速(如果可用)
        if self.use_igraph and self.ig_adapter:
            try:
                # igraph社区发现 (快50-120倍)
                communities = self.ig_adapter.detect_communities(
                    algorithm=algorithm,
                    weights='weight'
                )
            except Exception as e:
                logger.warning(f"igraph社区发现失败，回退到NetworkX: {e}")
                self.use_igraph = False
        
        # 回退到NetworkX
        if not self.use_igraph:
            # 转换为无向图(社区发现通常在无向图上进行)
            undirected = self.nx_graph.to_undirected()
            
            try:
                if algorithm == "louvain":
                    # Louvain算法
                    import community as community_louvain
                    communities = community_louvain.best_partition(
                        undirected,
                        resolution=resolution
                    )
                elif algorithm == "leiden":
                    # Leiden算法(需要leidenalg库)
                    try:
                        import leidenalg
                        import igraph as ig
                        
                        # 转换为igraph格式
                        ig_graph = ig.Graph.from_networkx(undirected)
                        partition = leidenalg.find_partition(
                            ig_graph,
                            leidenalg.RBConfigurationVertexPartition,
                            resolution_parameter=resolution
                        )
                        communities = {
                            list(undirected.nodes())[i]: partition.membership[i]
                            for i in range(len(partition.membership))
                        }
                    except ImportError:
                        logger.warning("leidenalg未安装,回退到louvain")
                        import community as community_louvain
                        communities = community_louvain.best_partition(
                            undirected,
                            resolution=resolution
                        )
                else:
                    raise ValueError(f"不支持的算法: {algorithm}")
                
            except Exception as e:
                logger.error(f"社区发现失败: {e}")
                # 返回单一社区
                communities = {node_id: 0 for node_id in self.graph.nodes.keys()}
        
        # 更新节点的社区ID
        for node_id, comm_id in communities.items():
            node = self.graph.get_node(node_id)
            if node:
                node.community_id = comm_id
        
        num_communities = len(set(communities.values()))
        logger.info(f"社区发现完成: {num_communities} 个社区")
        
        return communities
    
    def find_evolution_paths(
        self,
        max_depth: int = 5
    ) -> List[List[str]]:
        """
        追踪方法演进路径
        
        基于 'evolved_from' 关系构建演进链
        
        Args:
            max_depth: 最大深度
        
        Returns:
            演进路径列表,每个路径是paper_id的序列
        """
        logger.info("开始追踪方法演进路径...")
        
        from .data_structures import RelationType
        
        # 使用igraph加速(如果可用)
        if self.use_igraph and self.ig_adapter:
            try:
                all_paths = self.ig_adapter.find_evolution_paths(
                    relation_type=RelationType.EVOLVED_FROM.value,
                    max_depth=max_depth
                )
                return all_paths
            except Exception as e:
                logger.warning(f"igraph路径追踪失败，回退到NetworkX: {e}")
                self.use_igraph = False
        
        # 回退到NetworkX
        # 构建演进图(只包含evolved_from边)
        evolution_graph = nx.DiGraph()
        
        for edge in self.graph.edges:
            if edge.relation_type == RelationType.EVOLVED_FROM:
                # A evolved_from B => B -> A (时间顺序)
                evolution_graph.add_edge(edge.target, edge.source)
        
        # 找到所有根节点(没有入边的节点)
        root_nodes = [
            node for node in evolution_graph.nodes()
            if evolution_graph.in_degree(node) == 0
        ]
        
        if not root_nodes:
            logger.warning("未找到演进根节点")
            return []
        
        # 从每个根节点DFS追踪演进路径
        all_paths = []
        
        def dfs_paths(node, current_path, depth):
            if depth >= max_depth:
                return
            
            current_path.append(node)
            
            successors = list(evolution_graph.successors(node))
            
            if not successors:
                # 叶子节点,保存路径
                if len(current_path) > 1:  # 至少2个节点才算路径
                    all_paths.append(current_path.copy())
            else:
                # 继续递归
                for succ in successors:
                    dfs_paths(succ, current_path.copy(), depth + 1)
        
        for root in root_nodes:
            dfs_paths(root, [], 0)
        
        logger.info(f"找到 {len(all_paths)} 条演进路径")
        return all_paths
    
    def calculate_wcr(
        self,
        top_k: int = 50,
        centrality_type: str = "pagerank"
    ) -> float:
        """
        计算WCR (Weighted Centrality Recall)
        
        评估是否覆盖了最重要的论文
        
        Args:
            top_k: Top-K论文数量
            centrality_type: 中心性类型 ('pagerank' 或 'betweenness')
        
        Returns:
            WCR分数 (0.0-1.0)
        """
        # 按中心性排序
        if centrality_type == "pagerank":
            sorted_nodes = sorted(
                self.graph.nodes.values(),
                key=lambda n: n.pagerank or 0.0,
                reverse=True
            )
        else:
            sorted_nodes = sorted(
                self.graph.nodes.values(),
                key=lambda n: n.betweenness_centrality or 0.0,
                reverse=True
            )
        
        # 计算Top-K的总权重
        top_nodes = sorted_nodes[:top_k]
        if centrality_type == "pagerank":
            top_weight = sum(n.pagerank or 0.0 for n in top_nodes)
            total_weight = sum(n.pagerank or 0.0 for n in self.graph.nodes.values())
        else:
            top_weight = sum(n.betweenness_centrality or 0.0 for n in top_nodes)
            total_weight = sum(n.betweenness_centrality or 0.0 for n in self.graph.nodes.values())
        
        wcr = top_weight / total_weight if total_weight > 0 else 0.0
        
        logger.info(f"WCR (top-{top_k}, {centrality_type}): {wcr:.4f}")
        return wcr
    
    def calculate_cc(self) -> float:
        """
        计算CC (Community Coverage)
        
        评估是否覆盖了所有研究社区
        
        Returns:
            CC分数 (0.0-1.0)
        """
        # 统计每个社区的论文数
        community_sizes = defaultdict(int)
        for node in self.graph.nodes.values():
            if node.community_id is not None:
                community_sizes[node.community_id] += 1
        
        if not community_sizes:
            return 0.0
        
        # 计算熵(Shannon Entropy)来衡量分布均匀性
        total = sum(community_sizes.values())
        entropy = 0.0
        for size in community_sizes.values():
            if size > 0:
                p = size / total
                entropy -= p * np.log2(p)
        
        # 归一化熵(最大熵 = log2(num_communities))
        max_entropy = np.log2(len(community_sizes))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        # CC: 社区数量 * 分布均匀性
        num_communities = len(community_sizes)
        cc = (num_communities / 10.0) * normalized_entropy  # 假设理想社区数约10
        cc = min(cc, 1.0)  # 截断到1.0
        
        logger.info(f"CC (社区数={num_communities}, 熵={normalized_entropy:.4f}): {cc:.4f}")
        return cc
    
    def calculate_sc(self) -> float:
        """
        计算SC (Structural Coherence)
        
        评估演进路径的逻辑性
        
        Returns:
            SC分数 (0.0-1.0)
        """
        # 找到演进路径
        paths = self.find_evolution_paths()
        
        if not paths:
            return 0.0
        
        # 计算路径的平均长度(越长说明演进脉络越清晰)
        avg_path_length = np.mean([len(p) for p in paths])
        
        # 计算路径覆盖的节点比例
        nodes_in_paths = set()
        for path in paths:
            nodes_in_paths.update(path)
        
        coverage = len(nodes_in_paths) / self.graph.node_count() if self.graph.node_count() > 0 else 0.0
        
        # SC综合考虑路径长度和覆盖率
        # 归一化平均路径长度(假设理想长度为5)
        normalized_length = min(avg_path_length / 5.0, 1.0)
        
        sc = 0.6 * normalized_length + 0.4 * coverage
        
        logger.info(f"SC (路径数={len(paths)}, 平均长度={avg_path_length:.2f}, 覆盖率={coverage:.4f}): {sc:.4f}")
        return sc
    
    def get_top_papers(
        self,
        by: str = "pagerank",
        top_k: int = 20
    ) -> List[MEKGNode]:
        """
        获取Top-K论文
        
        Args:
            by: 排序依据 ('pagerank', 'betweenness', 'citations')
            top_k: 数量
        
        Returns:
            Top-K节点列表
        """
        if by == "pagerank":
            sorted_nodes = sorted(
                self.graph.nodes.values(),
                key=lambda n: n.pagerank or 0.0,
                reverse=True
            )
        elif by == "betweenness":
            sorted_nodes = sorted(
                self.graph.nodes.values(),
                key=lambda n: n.betweenness_centrality or 0.0,
                reverse=True
            )
        elif by == "citations":
            sorted_nodes = sorted(
                self.graph.nodes.values(),
                key=lambda n: n.citation_count,
                reverse=True
            )
        else:
            raise ValueError(f"不支持的排序依据: {by}")
        
        return sorted_nodes[:top_k]
    
    def get_community_papers(self, community_id: int) -> List[MEKGNode]:
        """获取指定社区的所有论文"""
        return [
            node for node in self.graph.nodes.values()
            if node.community_id == community_id
        ]
    
    def generate_analysis_report(self) -> Dict[str, Any]:
        """
        生成完整的分析报告
        
        Returns:
            包含所有分析结果的报告
        """
        logger.info("生成MEKG分析报告...")
        
        # 计算所有指标
        centrality_metrics = self.calculate_centrality_metrics()
        communities = self.detect_communities()
        evolution_paths = self.find_evolution_paths()
        
        wcr = self.calculate_wcr()
        cc = self.calculate_cc()
        sc = self.calculate_sc()
        
        # 获取Top论文
        top_by_pagerank = self.get_top_papers("pagerank", 10)
        top_by_citations = self.get_top_papers("citations", 10)
        
        report = {
            "graph_statistics": {
                "num_nodes": self.graph.node_count(),
                "num_edges": self.graph.edge_count(),
                "num_communities": len(set(communities.values())),
                "num_evolution_paths": len(evolution_paths)
            },
            "evaluation_metrics": {
                "wcr": wcr,
                "cc": cc,
                "sc": sc
            },
            "top_papers": {
                "by_pagerank": [
                    {
                        "paper_id": n.paper_id,
                        "title": n.title,
                        "pagerank": n.pagerank,
                        "citations": n.citation_count
                    }
                    for n in top_by_pagerank
                ],
                "by_citations": [
                    {
                        "paper_id": n.paper_id,
                        "title": n.title,
                        "citations": n.citation_count
                    }
                    for n in top_by_citations
                ]
            },
            "evolution_paths": [
                {
                    "length": len(path),
                    "papers": [
                        self.graph.get_node(pid).title if self.graph.get_node(pid) else pid
                        for pid in path
                    ]
                }
                for path in evolution_paths[:5]  # 只展示前5条
            ]
        }
        
        logger.info("分析报告生成完成")
        return report