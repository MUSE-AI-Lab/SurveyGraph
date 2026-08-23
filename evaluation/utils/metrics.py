"""
指标计算工具
============

提供各种评测指标的计算函数。
"""

import re
import math
from typing import Set, List, Dict, Any, Tuple
from collections import defaultdict
import logging


logger = logging.getLogger(__name__)


def calculate_recall(generated: Set, gold_standard: Set) -> float:
    """
    计算召回率
    
    Args:
        generated: 生成的集合
        gold_standard: 金标准集合
        
    Returns:
        召回率 (0-1)
    """
    if not gold_standard:
        return 1.0
    
    intersection = generated & gold_standard
    return len(intersection) / len(gold_standard)


def calculate_precision(generated: Set, gold_standard: Set) -> float:
    """
    计算精确率
    
    Args:
        generated: 生成的集合
        gold_standard: 金标准集合
        
    Returns:
        精确率 (0-1)
    """
    if not generated:
        return 0.0
    
    intersection = generated & gold_standard
    return len(intersection) / len(generated)


def calculate_f1(precision: float, recall: float) -> float:
    """
    计算F1分数
    
    Args:
        precision: 精确率
        recall: 召回率
        
    Returns:
        F1分数
    """
    if precision + recall == 0:
        return 0.0
    
    return 2 * (precision * recall) / (precision + recall)


def normalize_title(title: str) -> str:
    """
    规范化论文标题以便匹配
    
    Args:
        title: 原始标题
        
    Returns:
        规范化后的标题
    """
    # 转小写
    title = title.lower()
    
    # 移除标点和特殊字符
    title = re.sub(r'[^\w\s]', '', title)
    
    # 规范化空白
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title


def calculate_wcr(
    cited_papers: Set[str],
    core_papers: Set[str],
    paper_centrality: Dict[str, float]
) -> Tuple[float, Dict]:
    """
    计算加权中心性召回率 (Weighted Centrality Recall)
    
    WCR = Σ(centrality(p) for p in cited ∩ core) / Σ(centrality(p) for p in core)
    
    Args:
        cited_papers: 被引用的论文ID集合
        core_papers: 核心论文ID集合
        paper_centrality: 论文中心性字典 {paper_id: centrality}
        
    Returns:
        (WCR分数, 详细信息)
    """
    if not core_papers:
        return 1.0, {"message": "No core papers identified"}
    
    # 计算被引用的核心论文的中心性总和
    cited_core = cited_papers & core_papers
    cited_centrality_sum = sum(
        paper_centrality.get(p, 0) for p in cited_core
    )
    
    # 计算所有核心论文的中心性总和
    total_centrality_sum = sum(
        paper_centrality.get(p, 0) for p in core_papers
    )
    
    wcr = cited_centrality_sum / total_centrality_sum if total_centrality_sum > 0 else 0
    
    return wcr, {
        "cited_core_papers": len(cited_core),
        "total_core_papers": len(core_papers),
        "cited_centrality_sum": cited_centrality_sum,
        "total_centrality_sum": total_centrality_sum,
        "missing_core_papers": list(core_papers - cited_papers)[:10]
    }


def calculate_cc(
    cited_papers: Set[str],
    paper_communities: Dict[str, str],
    all_communities: Set[str]
) -> Tuple[float, Dict]:
    """
    计算社区覆盖率 (Community Coverage)
    
    CC = |covered_communities| / |total_communities|
    
    Args:
        cited_papers: 被引用的论文ID集合
        paper_communities: 论文所属社区字典 {paper_id: community}
        all_communities: 所有社区集合
        
    Returns:
        (CC分数, 详细信息)
    """
    if not all_communities:
        return 1.0, {"message": "No communities identified"}
    
    # 找出被引用论文所属的社区
    covered_communities = set()
    for paper_id in cited_papers:
        community = paper_communities.get(paper_id)
        if community:
            covered_communities.add(community)
    
    cc = len(covered_communities) / len(all_communities)
    
    return cc, {
        "covered_communities": list(covered_communities),
        "total_communities": list(all_communities),
        "missing_communities": list(all_communities - covered_communities)
    }


def calculate_tc(
    cited_papers: Set[str],
    paper_years: Dict[str, int],
    expected_year_range: Tuple[int, int]
) -> Tuple[float, Dict]:
    """
    计算时间覆盖率 (Temporal Coverage)
    
    Args:
        cited_papers: 被引用的论文ID集合
        paper_years: 论文年份字典 {paper_id: year}
        expected_year_range: 期望的年份范围 (min_year, max_year)
        
    Returns:
        (TC分数, 详细信息)
    """
    if not cited_papers:
        return 0.0, {"message": "No papers cited"}
    
    # 获取被引用论文的年份
    cited_years = []
    for paper_id in cited_papers:
        year = paper_years.get(paper_id)
        if year:
            cited_years.append(year)
    
    if not cited_years:
        return 0.5, {"message": "No year information in cited papers"}
    
    min_cited = min(cited_years)
    max_cited = max(cited_years)
    
    expected_min, expected_max = expected_year_range
    
    # 计算覆盖率
    expected_range = expected_max - expected_min + 1
    actual_range = max_cited - min_cited + 1
    
    # 检查是否覆盖了最新年份
    recency_bonus = 1.0 if max_cited >= expected_max - 1 else 0.8
    
    tc = min(1.0, (actual_range / expected_range) * recency_bonus)
    
    # 年份分布
    year_distribution = defaultdict(int)
    for year in cited_years:
        year_distribution[year] += 1
    
    return tc, {
        "cited_year_range": (min_cited, max_cited),
        "expected_year_range": (expected_min, expected_max),
        "year_distribution": dict(sorted(year_distribution.items()))
    }


def calculate_recency_score(years: List[int], baseline_year: int = 2020) -> float:
    """
    计算文献新颖性分数
    
    Args:
        years: 年份列表
        baseline_year: 基准年份
        
    Returns:
        新颖性分数 (0-1)
    """
    if not years:
        return 0.0
    
    avg_year = sum(years) / len(years)
    max_bonus_years = 5
    
    if avg_year >= baseline_year:
        years_beyond = min(avg_year - baseline_year, max_bonus_years)
        score = 0.5 + (years_beyond / max_bonus_years) * 0.5
    else:
        years_before = baseline_year - avg_year
        penalty = min(years_before / 10, 0.5)
        score = 0.5 - penalty
    
    return max(0.0, min(1.0, score))


def calculate_diversity_score(
    papers: List[Dict],
    venue_key: str = "venue",
    type_key: str = "paper_type",
    year_key: str = "year"
) -> Tuple[float, Dict]:
    """
    计算文献多样性分数
    
    Args:
        papers: 论文列表
        venue_key: venue字段名
        type_key: 类型字段名
        year_key: 年份字段名
        
    Returns:
        (多样性分数, 详细信息)
    """
    venues = set()
    paper_types = set()
    year_distribution = defaultdict(int)
    
    for paper in papers:
        venue = paper.get(venue_key)
        if venue:
            venues.add(venue)
        
        paper_type = paper.get(type_key)
        if paper_type:
            paper_types.add(paper_type)
        
        year = paper.get(year_key)
        if year:
            year_distribution[year] += 1
    
    # 计算多样性指标
    venue_diversity = min(len(venues) / 20, 1.0)
    type_diversity = min(len(paper_types) / 5, 1.0)
    
    # 年份分布的熵
    total_papers = sum(year_distribution.values())
    if total_papers > 0:
        year_entropy = -sum(
            (count / total_papers) * math.log2(count / total_papers + 1e-10)
            for count in year_distribution.values() if count > 0
        )
        max_entropy = math.log2(len(year_distribution) + 1)
        year_diversity = min(year_entropy / max_entropy, 1.0) if max_entropy > 0 else 0.5
    else:
        year_diversity = 0.0
    
    diversity_score = (
        venue_diversity * 0.4 +
        type_diversity * 0.3 +
        year_diversity * 0.3
    )
    
    return diversity_score, {
        "venue_count": len(venues),
        "type_count": len(paper_types),
        "year_distribution": dict(sorted(year_distribution.items())),
        "venue_diversity": venue_diversity,
        "type_diversity": type_diversity,
        "year_diversity": year_diversity
    }


def _normalize_for_matching(text: str) -> str:
    """
    规范化文本用于匹配
    - 转小写
    - 将 & 替换为 and
    - 移除多余空格和标点
    """
    text = text.lower()
    # 替换常见的等价表达
    text = text.replace("&", " and ")
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    # 移除多余空格
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_keywords(text: str) -> Set[str]:
    """
    从文本中提取关键词
    """
    # 规范化
    text = _normalize_for_matching(text)
    # 分词
    words = text.split()
    # 过滤停用词
    stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'in', 'on', 'to', 'with', 'by'}
    keywords = {w for w in words if w not in stopwords and len(w) > 2}
    return keywords


# 定义社区名称到相关关键词的映射
COMMUNITY_KEYWORD_MAPPING = {
    "tool definition": ["definition", "representation", "api", "interface", "schema", "specification"],
    "tool execution": ["execution", "integration", "runtime", "invoke", "call", "implement"],
    "tool learning": ["learning", "adaptation", "training", "fine-tuning", "optimization"],
    "tool selection": ["selection", "planning", "routing", "decision", "choice", "strategy"],
    "evaluation": ["evaluation", "benchmark", "assessment", "metric", "test", "performance"],
    "applications": ["application", "use case", "domain", "deployment", "real-world"],
}


def _get_expanded_keywords(community: str) -> Set[str]:
    """
    获取社区的扩展关键词
    """
    keywords = _extract_keywords(community)
    
    # 添加映射的关键词
    community_lower = community.lower()
    for key, expanded in COMMUNITY_KEYWORD_MAPPING.items():
        if key in community_lower:
            keywords.update(expanded)
    
    return keywords


def calculate_structure_match_score(
    outline_sections: List[str],
    communities: List[str]
) -> Tuple[float, Dict]:
    """
    计算结构匹配分数
    
    Args:
        outline_sections: 大纲章节标题列表
        communities: 社区名称列表
        
    Returns:
        (匹配分数, 详细信息)
    """
    if not communities:
        return 0.5, {"message": "No communities to match"}
    
    matched_communities = set()
    section_matches = []
    
    # 预处理社区名称 - 使用扩展关键词
    community_keywords = {}
    for community in communities:
        community_keywords[community] = _get_expanded_keywords(community)
    
    # 合并所有章节内容用于整体匹配
    all_sections_text = " ".join(outline_sections)
    all_sections_normalized = _normalize_for_matching(all_sections_text)
    all_sections_keywords = _extract_keywords(all_sections_text)
    
    for section in outline_sections:
        section_normalized = _normalize_for_matching(section)
        section_keywords = _extract_keywords(section)
        matches = []
        
        for community in communities:
            community_normalized = _normalize_for_matching(community)
            comm_keywords = community_keywords[community]
            
            # 方法1: 直接包含匹配（规范化后）
            if community_normalized in section_normalized or section_normalized in community_normalized:
                matches.append(community)
                matched_communities.add(community)
                continue
            
            # 方法2: 关键词重叠匹配（使用扩展关键词）
            if comm_keywords and section_keywords:
                overlap = comm_keywords & section_keywords
                # 如果有任何关键词重叠，认为匹配
                if len(overlap) >= 1:
                    matches.append(community)
                    matched_communities.add(community)
                    continue
            
            # 方法3: 核心词匹配
            if comm_keywords:
                core_word = max(comm_keywords, key=len)
                if core_word in section_normalized:
                    matches.append(community)
                    matched_communities.add(community)
                    continue
        
        section_matches.append({
            "section": section,
            "matched_communities": matches
        })
    
    # 方法4: 全局匹配 - 检查社区关键词是否在任何章节中出现
    for community in communities:
        if community in matched_communities:
            continue
        
        comm_keywords = community_keywords[community]
        # 检查扩展关键词是否在所有章节文本中出现
        for keyword in comm_keywords:
            if keyword in all_sections_normalized:
                matched_communities.add(community)
                break
    
    score = len(matched_communities) / len(communities)
    
    return score, {
        "section_matches": section_matches,
        "matched_communities": list(matched_communities),
        "unmatched_communities": [c for c in communities if c not in matched_communities]
    }


def aggregate_scores(
    scores: Dict[str, float],
    weights: Dict[str, float]
) -> float:
    """
    聚合多个分数
    
    Args:
        scores: 分数字典 {metric_name: score}
        weights: 权重字典 {metric_name: weight}
        
    Returns:
        加权平均分数
    """
    total_score = 0.0
    total_weight = 0.0
    
    for metric, score in scores.items():
        weight = weights.get(metric, 0.0)
        total_score += score * weight
        total_weight += weight
    
    if total_weight == 0:
        return 0.0
    
    return total_score / total_weight


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全除法"""
    if denominator == 0:
        return default
    return numerator / denominator