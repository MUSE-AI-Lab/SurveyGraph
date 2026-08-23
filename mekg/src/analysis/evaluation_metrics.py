"""
MEKG候选对生成的评估指标

包含学术论文常用的评估指标:
1. 基础指标: Precision, Recall, F1-Score
2. 图质量指标: Modularity, Clustering Coefficient, Connectivity
3. 效率指标: Cost, API Calls, Time
4. 统计显著性: t-test, Cohen's d
"""

import math
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict
import networkx as nx
from loguru import logger


class MEKGEvaluationMetrics:
    """MEKG评估指标计算器"""
    
    def __init__(self, papers: List[Dict[str, Any]]):
        """
        Args:
            papers: 论文列表
        """
        self.papers = papers
        self.n_papers = len(papers)
    
    def compute_pair_metrics(
        self,
        generated_pairs: List[Tuple[Dict, Dict]],
        ground_truth_pairs: List[Tuple[str, str]] = None
    ) -> Dict[str, float]:
        """
        计算候选对生成的基础指标
        
        如果有ground truth，计算Precision/Recall/F1
        否则只计算Coverage等描述性指标
        
        Args:
            generated_pairs: 生成的候选对
            ground_truth_pairs: 真实关系对(paper_id元组列表)
        
        Returns:
            指标字典
        """
        metrics = {}
        
        # 基础统计
        metrics['num_pairs'] = len(generated_pairs)
        metrics['density'] = len(generated_pairs) / (self.n_papers * (self.n_papers - 1) / 2)
        
        # 节点覆盖率
        covered_papers = set()
        for pa, pb in generated_pairs:
            covered_papers.add(pa['paper_id'])
            covered_papers.add(pb['paper_id'])
        metrics['coverage'] = len(covered_papers) / self.n_papers
        
        # 如果有ground truth，计算精确度指标
        if ground_truth_pairs:
            generated_set = {
                tuple(sorted([pa['paper_id'], pb['paper_id']]))
                for pa, pb in generated_pairs
            }
            gt_set = {tuple(sorted(pair)) for pair in ground_truth_pairs}
            
            tp = len(generated_set & gt_set)
            fp = len(generated_set - gt_set)
            fn = len(gt_set - generated_set)
            
            metrics['precision'] = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            metrics['recall'] = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            metrics['f1_score'] = (
                2 * metrics['precision'] * metrics['recall'] / 
                (metrics['precision'] + metrics['recall'])
                if (metrics['precision'] + metrics['recall']) > 0 else 0.0
            )
            metrics['true_positives'] = tp
            metrics['false_positives'] = fp
            metrics['false_negatives'] = fn
        
        return metrics
    
    def compute_graph_metrics(
        self,
        pairs: List[Tuple[Dict, Dict]]
    ) -> Dict[str, float]:
        """
        计算图质量指标
        
        包括:
        - 连通性
        - 聚类系数  
        - 模块度
        - 平均路径长度
        - 度分布
        
        Args:
            pairs: 论文对列表
        
        Returns:
            图指标字典
        """
        # 构建NetworkX图
        G = nx.Graph()
        for paper in self.papers:
            G.add_node(paper['paper_id'])
        for pa, pb in pairs:
            G.add_edge(pa['paper_id'], pb['paper_id'])
        
        metrics = {}
        
        # 1. 连通性
        metrics['num_components'] = nx.number_connected_components(G)
        if metrics['num_components'] > 0:
            largest_cc = max(nx.connected_components(G), key=len)
            metrics['largest_component_size'] = len(largest_cc)
            metrics['largest_component_ratio'] = len(largest_cc) / self.n_papers
        
        # 2. 聚类系数（小世界特性）
        try:
            metrics['avg_clustering'] = nx.average_clustering(G)
        except:
            metrics['avg_clustering'] = 0.0
        
        # 3. 平均最短路径（仅在连通时计算）
        if nx.is_connected(G):
            metrics['avg_shortest_path'] = nx.average_shortest_path_length(G)
        else:
            # 对最大连通分量计算
            if metrics['num_components'] > 0:
                largest_cc = max(nx.connected_components(G), key=len)
                subG = G.subgraph(largest_cc)
                metrics['avg_shortest_path'] = nx.average_shortest_path_length(subG)
        
        # 4. 度分布
        degrees = [G.degree(n) for n in G.nodes()]
        if degrees:
            metrics['avg_degree'] = sum(degrees) / len(degrees)
            metrics['max_degree'] = max(degrees)
            metrics['min_degree'] = min(degrees)
        
        # 5. 模块度（需要社区检测）
        try:
            from networkx.algorithms import community
            communities = community.greedy_modularity_communities(G)
            metrics['num_communities'] = len(communities)
            metrics['modularity'] = community.modularity(G, communities)
        except:
            logger.warning("社区检测失败，跳过modularity计算")
            metrics['num_communities'] = 0
            metrics['modularity'] = 0.0
        
        # 6. 密度
        metrics['graph_density'] = nx.density(G)
        
        return metrics
    
    def compute_efficiency_metrics(
        self,
        num_pairs: int,
        actual_edges: int = None,
        cost_per_call: float = 0.001
    ) -> Dict[str, float]:
        """
        计算效率指标
        
        Args:
            num_pairs: 候选对数量（LLM调用次数）
            actual_edges: 实际发现的边数
            cost_per_call: 每次LLM调用成本（美元）
        
        Returns:
            效率指标字典
        """
        metrics = {}
        
        metrics['num_llm_calls'] = num_pairs
        metrics['total_cost'] = num_pairs * cost_per_call
        
        if actual_edges is not None and actual_edges > 0:
            metrics['cost_per_edge'] = metrics['total_cost'] / actual_edges
            metrics['hit_rate'] = actual_edges / num_pairs
        
        # 与完全图对比的减少比例
        complete_graph_size = self.n_papers * (self.n_papers - 1) // 2
        metrics['reduction_ratio'] = 1.0 - (num_pairs / complete_graph_size)
        metrics['reduction_percentage'] = metrics['reduction_ratio'] * 100
        
        return metrics
    
    @staticmethod
    def compute_statistical_significance(
        scores_a: List[float],
        scores_b: List[float]
    ) -> Dict[str, float]:
        """
        计算统计显著性
        
        使用t-test和Cohen's d
        
        Args:
            scores_a: 方法A的分数列表
            scores_b: 方法B的分数列表
        
        Returns:
            统计指标字典
        """
        import numpy as np
        from scipy import stats
        
        results = {}
        
        # t-test
        t_stat, p_value = stats.ttest_ind(scores_a, scores_b)
        results['t_statistic'] = t_stat
        results['p_value'] = p_value
        results['significant'] = p_value < 0.05
        
        # Cohen's d (效应量)
        mean_a, mean_b = np.mean(scores_a), np.mean(scores_b)
        std_a, std_b = np.std(scores_a, ddof=1), np.std(scores_b, ddof=1)
        pooled_std = math.sqrt((std_a**2 + std_b**2) / 2)
        
        if pooled_std > 0:
            results['cohens_d'] = (mean_a - mean_b) / pooled_std
        else:
            results['cohens_d'] = 0.0
        
        # 效应量解释
        abs_d = abs(results['cohens_d'])
        if abs_d < 0.2:
            results['effect_size'] = 'negligible'
        elif abs_d < 0.5:
            results['effect_size'] = 'small'
        elif abs_d < 0.8:
            results['effect_size'] = 'medium'
        else:
            results['effect_size'] = 'large'
        
        return results
    
    def generate_comparison_report(
        self,
        method_results: Dict[str, Dict[str, float]]
    ) -> str:
        """
        生成对比报告（LaTeX表格格式）
        
        Args:
            method_results: {方法名: 指标字典}
        
        Returns:
            LaTeX表格字符串
        """
        # 选择关键指标
        key_metrics = [
            'num_pairs', 'precision', 'recall', 'f1_score',
            'coverage', 'avg_clustering', 'modularity',
            'total_cost', 'reduction_percentage'
        ]
        
        # 生成LaTeX表格
        latex = "\\begin{table}[htbp]\n"
        latex += "\\centering\n"
        latex += "\\caption{候选对生成方法对比}\n"
        latex += "\\begin{tabular}{l" + "c" * len(method_results) + "}\n"
        latex += "\\toprule\n"
        
        # 表头
        latex += "Metric & " + " & ".join(method_results.keys()) + " \\\\\n"
        latex += "\\midrule\n"
        
        # 数据行
        for metric in key_metrics:
            row = metric.replace('_', '\\_')
            for method, results in method_results.items():
                value = results.get(metric, 0.0)
                if isinstance(value, float):
                    row += f" & {value:.3f}"
                else:
                    row += f" & {value}"
            row += " \\\\\n"
            latex += row
        
        latex += "\\bottomrule\n"
        latex += "\\end{tabular}\n"
        latex += "\\end{table}\n"
        
        return latex


def comprehensive_evaluation(
    papers: List[Dict[str, Any]],
    method_pairs: Dict[str, List[Tuple[Dict, Dict]]],
    ground_truth_pairs: List[Tuple[str, str]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    对多种方法进行综合评估
    
    Args:
        papers: 论文列表
        method_pairs: {方法名: 候选对列表}
        ground_truth_pairs: 真实关系对（可选）
    
    Returns:
        {方法名: 评估结果}
    """
    evaluator = MEKGEvaluationMetrics(papers)
    results = {}
    
    logger.info(f"\n{'='*80}")
    logger.info("开始综合评估")
    logger.info(f"{'='*80}\n")
    
    for method_name, pairs in method_pairs.items():
        logger.info(f"评估方法: {method_name}")
        
        method_results = {}
        
        # 1. 候选对指标
        pair_metrics = evaluator.compute_pair_metrics(pairs, ground_truth_pairs)
        method_results.update(pair_metrics)
        
        # 2. 图质量指标
        graph_metrics = evaluator.compute_graph_metrics(pairs)
        method_results.update(graph_metrics)
        
        # 3. 效率指标
        efficiency_metrics = evaluator.compute_efficiency_metrics(len(pairs))
        method_results.update(efficiency_metrics)
        
        results[method_name] = method_results
        
        # 输出摘要
        logger.info(f"  候选对: {len(pairs)}")
        logger.info(f"  覆盖率: {pair_metrics.get('coverage', 0):.2%}")
        logger.info(f"  成本: ${efficiency_metrics['total_cost']:.2f}")
        if 'f1_score' in pair_metrics:
            logger.info(f"  F1分数: {pair_metrics['f1_score']:.3f}")
        logger.info("")
    
    logger.info(f"{'='*80}\n")
    
    return results