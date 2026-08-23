"""
核心论文发现器

第二阶段核心组件：基于引文网络自动发现领域核心论文
不依赖任何"权威综述"，完全由数据驱动

主要功能：
1. 在引文网络上运行PageRank算法
2. 结合引用数、新鲜度等计算综合核心分数
3. 自适应识别核心论文集合
"""

import math
from typing import List, Dict, Any, Set, Tuple, Optional
from collections import defaultdict

import networkx as nx
from loguru import logger


class CorePaperDiscoverer:
    """
    核心论文发现器
    
    基于网络科学算法（PageRank）和文献计量学指标，
    自动识别领域的核心骨架论文，不依赖任何先验知识。
    """
    
    def __init__(
        self,
        citation_graph: nx.DiGraph,
        papers_index: Dict[str, Dict[str, Any]]
    ):
        """
        初始化发现器
        
        Args:
            citation_graph: 引文网络（有向图）
            papers_index: 论文索引 {paper_id: paper_data}
        """
        self.citation_graph = citation_graph
        self.papers_index = papers_index
        self.core_scores: Dict[str, float] = {}
        self.pagerank_scores: Dict[str, float] = {}
        self.core_papers: List[str] = []
        
    def compute_pagerank(
        self,
        alpha: float = 0.85,
        max_iter: int = 100
    ) -> Dict[str, float]:
        """
        在引文网络上计算PageRank
        
        Args:
            alpha: 阻尼因子（标准为0.85）
            max_iter: 最大迭代次数
        
        Returns:
            PageRank分数字典
        """
        logger.info(f"计算PageRank（alpha={alpha}）...")
        
        if self.citation_graph.number_of_nodes() == 0:
            logger.warning("引文网络为空，无法计算PageRank")
            return {}
        
        try:
            # NetworkX的PageRank实现
            # 注意：在引文网络中，如果A引用B，则存在A->B的边
            # PageRank会给被引用多的、被重要论文引用的论文更高分数
            self.pagerank_scores = nx.pagerank(
                self.citation_graph,
                alpha=alpha,
                max_iter=max_iter,
                tol=1e-6
            )
            
            # 归一化到0-1范围
            if self.pagerank_scores:
                max_pr = max(self.pagerank_scores.values())
                min_pr = min(self.pagerank_scores.values())
                pr_range = max_pr - min_pr if max_pr != min_pr else 1.0
                
                for paper_id in self.pagerank_scores:
                    self.pagerank_scores[paper_id] = (
                        (self.pagerank_scores[paper_id] - min_pr) / pr_range
                    )
            
            logger.info(f"PageRank计算完成: {len(self.pagerank_scores)} 个节点")
            
            # 显示Top-10
            top_10 = sorted(
                self.pagerank_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
            
            logger.info("Top-10 PageRank:")
            for i, (paper_id, score) in enumerate(top_10, 1):
                paper = self.papers_index.get(paper_id, {})
                title = paper.get('title', 'Unknown')[:50]
                logger.info(f"  {i}. {title}... (PR={score:.4f})")
            
        except Exception as e:
            logger.error(f"PageRank计算失败: {e}")
            self.pagerank_scores = {}
        
        return self.pagerank_scores
    
    def compute_core_scores(
        self,
        pagerank_weight: float = 0.4,
        citation_weight: float = 0.3,
        recency_weight: float = 0.2,
        degree_weight: float = 0.1,
        current_year: int = 2024
    ) -> Dict[str, float]:
        """
        计算综合核心分数
        
        综合考虑多个因素：
        - PageRank分数：网络结构重要性
        - 引用数：学术影响力
        - 新鲜度：时效性（支持发现新突破）
        - 度中心性：连接活跃度
        
        Args:
            pagerank_weight: PageRank权重
            citation_weight: 引用数权重
            recency_weight: 新鲜度权重
            degree_weight: 度中心性权重
            current_year: 当前年份（用于计算新鲜度）
        
        Returns:
            核心分数字典
        """
        logger.info("计算综合核心分数...")
        
        # 确保已计算PageRank
        if not self.pagerank_scores:
            self.compute_pagerank()
        
        # 收集统计信息用于归一化
        all_citations = []
        all_years = []
        all_degrees = []
        
        for paper_id in self.citation_graph.nodes():
            paper = self.papers_index.get(paper_id, {})
            citations = paper.get('citations', paper.get('citation_count', 0))
            year = paper.get('year', current_year)
            
            if isinstance(citations, (int, float)) and citations >= 0:
                all_citations.append(citations)
            
            if isinstance(year, int) and 1900 < year <= current_year:
                all_years.append(year)
            
            # 计算度（入度+出度）
            degree = (
                self.citation_graph.in_degree(paper_id) +
                self.citation_graph.out_degree(paper_id)
            )
            all_degrees.append(degree)
        
        # 计算归一化参数
        max_citation = max(all_citations) if all_citations else 1
        min_year = min(all_years) if all_years else current_year - 10
        max_year = max(all_years) if all_years else current_year
        year_range = max_year - min_year if max_year > min_year else 1
        max_degree = max(all_degrees) if all_degrees else 1
        
        # 计算每篇论文的核心分数
        for paper_id in self.citation_graph.nodes():
            paper = self.papers_index.get(paper_id, {})
            
            # 1. PageRank分数（已归一化）
            pr_score = self.pagerank_scores.get(paper_id, 0.0)
            
            # 2. 引用数分数（log scale归一化，避免极端值主导）
            citations = paper.get('citations', paper.get('citation_count', 0))
            if not isinstance(citations, (int, float)) or citations < 0:
                citations = 0
            citation_score = math.log1p(citations) / math.log1p(max_citation) if max_citation > 0 else 0
            
            # 3. 新鲜度分数（越新越高）
            year = paper.get('year', current_year)
            if not isinstance(year, int) or year < 1900 or year > current_year:
                year = current_year
            recency_score = (year - min_year) / year_range if year_range > 0 else 0.5
            
            # 4. 度中心性分数
            degree = (
                self.citation_graph.in_degree(paper_id) +
                self.citation_graph.out_degree(paper_id)
            )
            degree_score = degree / max_degree if max_degree > 0 else 0
            
            # 综合分数
            core_score = (
                pagerank_weight * pr_score +
                citation_weight * citation_score +
                recency_weight * recency_score +
                degree_weight * degree_score
            )
            
            self.core_scores[paper_id] = core_score
        
        logger.info(f"核心分数计算完成: {len(self.core_scores)} 篇论文")
        
        return self.core_scores
    
    def identify_core_papers(
        self,
        core_ratio: float = 0.1,
        min_core_count: int = 10,
        max_core_count: int = 200,
        use_adaptive_threshold: bool = True
    ) -> List[str]:
        """
        识别核心论文集合
        
        Args:
            core_ratio: 核心论文比例（默认10%）
            min_core_count: 最小核心论文数量
            max_core_count: 最大核心论文数量
            use_adaptive_threshold: 是否使用自适应阈值（找分布的"肘部"）
        
        Returns:
            核心论文ID列表
        """
        logger.info("识别核心论文...")
        
        # 确保已计算核心分数
        if not self.core_scores:
            self.compute_core_scores()
        
        # 按核心分数排序
        sorted_papers = sorted(
            self.core_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # 计算核心论文数量
        total_papers = len(sorted_papers)
        target_count = int(total_papers * core_ratio)
        
        # 应用上下限约束
        target_count = max(min_core_count, min(target_count, max_core_count, total_papers))
        
        if use_adaptive_threshold:
            # 使用自适应阈值（找分数下降的"肘部"）
            adaptive_count = self._find_elbow_point(sorted_papers, target_count)
            if adaptive_count > 0:
                target_count = adaptive_count
                logger.info(f"自适应阈值调整: {target_count} 篇核心论文")
        
        # 选择核心论文
        self.core_papers = [paper_id for paper_id, _ in sorted_papers[:target_count]]
        
        # 统计信息
        core_paper_data = [
            self.papers_index.get(pid, {})
            for pid in self.core_papers
        ]
        
        avg_citations = sum(
            p.get('citations', p.get('citation_count', 0))
            for p in core_paper_data
        ) / len(core_paper_data) if core_paper_data else 0
        
        avg_year = sum(
            p.get('year', 2024)
            for p in core_paper_data
        ) / len(core_paper_data) if core_paper_data else 0
        
        logger.info(
            f"核心论文识别完成: {len(self.core_papers)} 篇 "
            f"(占比={len(self.core_papers)/total_papers*100:.1f}%, "
            f"平均引用={avg_citations:.0f}, "
            f"平均年份={avg_year:.1f})"
        )
        
        # 显示Top-10核心论文
        logger.info("Top-10 核心论文:")
        for i, paper_id in enumerate(self.core_papers[:10], 1):
            paper = self.papers_index.get(paper_id, {})
            title = paper.get('title', 'Unknown')[:50]
            score = self.core_scores.get(paper_id, 0)
            citations = paper.get('citations', paper.get('citation_count', 0))
            year = paper.get('year', 'N/A')
            logger.info(
                f"  {i}. {title}... "
                f"(Score={score:.4f}, Cites={citations}, Year={year})"
            )
        
        return self.core_papers
    
    def _find_elbow_point(
        self,
        sorted_papers: List[Tuple[str, float]],
        default_count: int
    ) -> int:
        """
        找到分数分布的"肘部"点
        
        使用简单的二阶差分方法找到下降最快的点
        
        Args:
            sorted_papers: 按分数降序排列的论文列表
            default_count: 默认数量
        
        Returns:
            建议的核心论文数量
        """
        if len(sorted_papers) < 10:
            return default_count
        
        scores = [score for _, score in sorted_papers]
        
        # 计算一阶差分（分数下降率）
        first_diff = []
        for i in range(1, len(scores)):
            first_diff.append(scores[i-1] - scores[i])
        
        if not first_diff:
            return default_count
        
        # 计算二阶差分（下降率的变化率）
        second_diff = []
        for i in range(1, len(first_diff)):
            second_diff.append(first_diff[i-1] - first_diff[i])
        
        if not second_diff:
            return default_count
        
        # 找到二阶差分最大的点（下降最急剧的地方）
        max_second_diff = max(second_diff)
        if max_second_diff <= 0:
            return default_count
        
        elbow_index = second_diff.index(max_second_diff) + 2  # +2 因为两次差分
        
        # 确保在合理范围内
        min_count = max(10, len(sorted_papers) // 20)  # 至少5%
        max_count = min(200, len(sorted_papers) // 5)   # 至多20%
        
        return max(min_count, min(elbow_index, max_count))
    
    def get_core_papers(self) -> List[str]:
        """获取核心论文ID列表"""
        return self.core_papers
    
    def get_core_scores(self) -> Dict[str, float]:
        """获取所有论文的核心分数"""
        return self.core_scores
    
    def get_pagerank_scores(self) -> Dict[str, float]:
        """获取所有论文的PageRank分数"""
        return self.pagerank_scores
    
    def is_core_paper(self, paper_id: str) -> bool:
        """判断论文是否为核心论文"""
        return paper_id in self.core_papers
    
    def get_paper_tier(self, paper_id: str) -> str:
        """
        获取论文的层级
        
        Returns:
            "core": 核心论文
            "influential": 有影响力的论文（Top 25%）
            "regular": 普通论文
        """
        if paper_id in self.core_papers:
            return "core"
        
        if not self.core_scores:
            return "regular"
        
        score = self.core_scores.get(paper_id, 0)
        sorted_scores = sorted(self.core_scores.values(), reverse=True)
        
        if not sorted_scores:
            return "regular"
        
        # Top 25% 为有影响力论文
        threshold_idx = int(len(sorted_scores) * 0.25)
        threshold_score = sorted_scores[threshold_idx] if threshold_idx < len(sorted_scores) else 0
        
        if score >= threshold_score:
            return "influential"
        
        return "regular"
    
    def generate_discovery_report(self) -> Dict[str, Any]:
        """
        生成核心发现报告
        
        Returns:
            包含发现过程详细信息的报告
        """
        report = {
            "total_papers": len(self.core_scores),
            "core_papers_count": len(self.core_papers),
            "core_ratio": len(self.core_papers) / len(self.core_scores) if self.core_scores else 0,
            "score_distribution": {
                "min": min(self.core_scores.values()) if self.core_scores else 0,
                "max": max(self.core_scores.values()) if self.core_scores else 0,
                "mean": sum(self.core_scores.values()) / len(self.core_scores) if self.core_scores else 0,
            },
            "top_20_core_papers": []
        }
        
        # 添加Top-20核心论文详情
        for paper_id in self.core_papers[:20]:
            paper = self.papers_index.get(paper_id, {})
            report["top_20_core_papers"].append({
                "paper_id": paper_id,
                "title": paper.get('title', 'Unknown'),
                "year": paper.get('year', 0),
                "citations": paper.get('citations', paper.get('citation_count', 0)),
                "core_score": self.core_scores.get(paper_id, 0),
                "pagerank_score": self.pagerank_scores.get(paper_id, 0)
            })
        
        return report