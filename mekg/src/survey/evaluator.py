"""
MEKG Evaluator
==============

基于MEKG知识图谱的综述质量评估模块。

评估指标:
1. WCR (Weighted Centrality Recall): 加权中心性召回率
2. CC (Community Coverage): 社区覆盖率
3. SC (Structural Coherence): 结构一致性
4. RA (Relation Accuracy): 关系准确性
5. TC (Temporal Coverage): 时间覆盖率
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict
import math

import sys
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class EvaluationResult:
    """评估结果"""
    # 核心指标
    wcr: float = 0.0  # Weighted Centrality Recall
    cc: float = 0.0   # Community Coverage
    sc: float = 0.0   # Structural Coherence
    ra: float = 0.0   # Relation Accuracy
    tc: float = 0.0   # Temporal Coverage
    
    # 综合得分
    overall_score: float = 0.0
    
    # 详细信息
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "wcr": self.wcr,
            "cc": self.cc,
            "sc": self.sc,
            "ra": self.ra,
            "tc": self.tc,
            "overall_score": self.overall_score,
            "details": self.details
        }
    
    def __str__(self) -> str:
        return f"""
MEKG Evaluation Results
=======================
WCR (Weighted Centrality Recall): {self.wcr:.4f}
CC  (Community Coverage):         {self.cc:.4f}
SC  (Structural Coherence):       {self.sc:.4f}
RA  (Relation Accuracy):          {self.ra:.4f}
TC  (Temporal Coverage):          {self.tc:.4f}
-----------------------
Overall Score:                    {self.overall_score:.4f}
"""


class MEKGEvaluator:
    """
    基于MEKG知识图谱的综述评估器
    
    评估维度:
    1. 核心论文覆盖: 综述是否引用了领域内的核心论文
    2. 社区覆盖: 综述是否覆盖了所有主要研究方向
    3. 结构一致性: 综述结构是否与知识图谱结构一致
    4. 关系准确性: 综述中描述的论文关系是否准确
    5. 时间覆盖: 综述是否覆盖了完整的时间范围
    """
    
    def __init__(
        self,
        mekg_data: Dict[str, Any],
        weights: Optional[Dict[str, float]] = None
    ):
        """
        初始化评估器
        
        Args:
            mekg_data: MEKG数据
            weights: 各指标权重，默认均等
        """
        self.mekg_data = mekg_data

        # NOTE: SurveyGraph/SurveyX 在生成 references.bib 时会对 paper_id 做 Windows 兼容清理
        #（例如 arXiv:2505.20192 -> arXiv_2505.20192），因此评估阶段必须对齐同一套 key。
        self.paper_by_canonical_id: Dict[str, Dict[str, Any]] = {}
        self.key_to_canonical_id: Dict[str, str] = {}

        for paper in mekg_data.get("papers", []):
            raw_id = paper.get("id") or paper.get("paper_id") or ""
            if not raw_id:
                continue

            canonical_id = self._sanitize_key(raw_id)
            self.paper_by_canonical_id[canonical_id] = paper

            aliases = {raw_id, canonical_id}
            bib_name = paper.get("bib_name")
            if bib_name:
                aliases.add(str(bib_name))

            for alias in aliases:
                if not alias:
                    continue
                self.key_to_canonical_id[str(alias)] = canonical_id

        # 兼容旧字段名：后续逻辑都使用 canonical_id
        self.papers = self.paper_by_canonical_id
        self.relations = mekg_data.get("relations", [])
        self.categories = mekg_data.get("categories", {})
        
        # 默认权重
        self.weights = weights or {
            "wcr": 0.25,
            "cc": 0.25,
            "sc": 0.20,
            "ra": 0.15,
            "tc": 0.15
        }
        
        # 预计算图谱统计信息
        self._precompute_graph_stats()

    @staticmethod
    def _sanitize_key(key: str) -> str:
        """与 pipeline._sanitize_filename 保持一致，用于对齐 BibTeX key。"""
        return re.sub(r'[\\/:*?"<>|]', '_', str(key))

    def _canonicalize_key(self, key: str) -> Optional[str]:
        """将任意形式的引用 key 映射为 canonical_id。"""
        if not key:
            return None
        return self.key_to_canonical_id.get(str(key))

    def _precompute_graph_stats(self):
        """预计算图谱统计信息"""
        # 1) 计算论文中心性
        # 优先：引用数（如果缺失较多则退化为图结构 PageRank/度中心性）
        self.paper_centrality: Dict[str, float] = {}

        citation_values = []
        for paper in self.papers.values():
            citations = paper.get("citations", 0)
            if isinstance(citations, (int, float)) and citations > 0:
                citation_values.append(float(citations))

        if citation_values:
            max_citations = max(citation_values) or 1.0
            for paper_id, paper in self.papers.items():
                citations = paper.get("citations", 0) or 0
                try:
                    citations = float(citations)
                except Exception:
                    citations = 0.0
                self.paper_centrality[paper_id] = citations / max_citations if max_citations > 0 else 0.0
        elif self.relations:
            # 没有可靠 citations 时，用关系图 PageRank（可用）或度中心性回退
            try:
                import networkx as nx  # type: ignore

                graph = nx.DiGraph()
                for pid in self.papers.keys():
                    graph.add_node(pid)

                for rel in self.relations:
                    src = self._canonicalize_key(rel.get("source", ""))
                    tgt = self._canonicalize_key(rel.get("target", ""))
                    if src and tgt:
                        graph.add_edge(src, tgt)

                pagerank = nx.pagerank(graph)
                max_pr = max(pagerank.values()) if pagerank else 1.0
                for pid in self.papers.keys():
                    self.paper_centrality[pid] = (pagerank.get(pid, 0.0) / max_pr) if max_pr > 0 else 0.0
            except Exception:
                # 度中心性回退（无外部依赖）
                degree = {pid: 0 for pid in self.papers.keys()}
                for rel in self.relations:
                    src = self._canonicalize_key(rel.get("source", ""))
                    tgt = self._canonicalize_key(rel.get("target", ""))
                    if src and tgt:
                        degree[src] = degree.get(src, 0) + 1
                        degree[tgt] = degree.get(tgt, 0) + 1
                max_deg = max(degree.values()) if degree else 1
                for pid, deg in degree.items():
                    self.paper_centrality[pid] = (deg / max_deg) if max_deg > 0 else 0.0
        else:
            # 极端回退：均匀中心性
            for pid in self.papers.keys():
                self.paper_centrality[pid] = 1.0
        
        # 识别核心论文（中心性Top 20%）
        sorted_papers = sorted(
            self.paper_centrality.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_count = max(1, len(sorted_papers) // 5)
        self.core_papers = set(p[0] for p in sorted_papers[:top_count])
        
        # 统计社区
        self.communities = set()
        for cat in self.categories.keys():
            self.communities.add(cat)
        
        # 统计年份范围
        years: List[int] = []
        for paper in self.papers.values():
            year = paper.get("year")
            if isinstance(year, int):
                years.append(year)
            elif isinstance(year, str) and year.isdigit():
                years.append(int(year))
        self.year_range = (min(years), max(years)) if years else (2020, 2024)
        
        # 构建关系索引
        self.relation_index = defaultdict(list)
        for rel in self.relations:
            source = self._canonicalize_key(rel.get("source", ""))
            target = self._canonicalize_key(rel.get("target", ""))
            if not source or not target:
                continue
            self.relation_index[(source, target)].append(rel)
            self.relation_index[(target, source)].append(rel)
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None
    ) -> EvaluationResult:
        """
        评估综述质量
        
        Args:
            survey_content: 综述内容（LaTeX格式）
            survey_outline: 综述大纲（可选）
            
        Returns:
            EvaluationResult对象
        """
        # 提取综述中引用的论文
        cited_papers, unknown_citations = self._extract_citations(survey_content)
        
        # 计算各项指标
        wcr, wcr_details = self._calculate_wcr(cited_papers)
        cc, cc_details = self._calculate_cc(cited_papers)
        sc, sc_details = self._calculate_sc(cited_papers, survey_outline)
        ra, ra_details = self._calculate_ra(survey_content, cited_papers)
        tc, tc_details = self._calculate_tc(cited_papers)
        
        # 计算综合得分
        overall_score = (
            self.weights["wcr"] * wcr +
            self.weights["cc"] * cc +
            self.weights["sc"] * sc +
            self.weights["ra"] * ra +
            self.weights["tc"] * tc
        )
        
        return EvaluationResult(
            wcr=wcr,
            cc=cc,
            sc=sc,
            ra=ra,
            tc=tc,
            overall_score=overall_score,
            details={
                "wcr": wcr_details,
                "cc": cc_details,
                "sc": sc_details,
                "ra": ra_details,
                "tc": tc_details,
                "cited_papers_count": len(cited_papers),
                "unknown_citations_count": len(unknown_citations),
                "unknown_citations_sample": unknown_citations[:10],
                "total_papers_count": len(self.papers),
                "core_papers_count": len(self.core_papers)
            }
        )
    
    def _extract_citations(self, content: str) -> Tuple[Set[str], List[str]]:
        """从内容中提取引用的论文（返回 canonical_id 集合 + 未识别 key 列表）"""
        if not content:
            return set(), []

        # 兼容 natbib: \citep[see][]{a,b} / \citet{a}
        pattern = re.compile(r'\\[cC]ite\w*(?:\[[^\]]*\])*\{([^}]+)\}')
        raw_keys: List[str] = []
        for match in pattern.findall(content):
            # 处理多引用: \cite{paper1, paper2}
            for key in match.split(','):
                key = key.strip()
                if key:
                    raw_keys.append(key)

        cited: Set[str] = set()
        unknown: List[str] = []
        for key in raw_keys:
            canonical = self._canonicalize_key(key)
            if canonical:
                cited.add(canonical)
            else:
                unknown.append(key)

        return cited, unknown
    
    def _calculate_wcr(self, cited_papers: Set[str]) -> Tuple[float, Dict]:
        """
        计算加权中心性召回率 (Weighted Centrality Recall)
        
        WCR = Σ(centrality(p) for p in cited ∩ core) / Σ(centrality(p) for p in core)
        
        衡量综述是否覆盖了高影响力的核心论文
        """
        if not self.core_papers:
            return 1.0, {"message": "No core papers identified"}
        
        # 计算被引用的核心论文的中心性总和
        cited_core = cited_papers & self.core_papers
        cited_centrality_sum = sum(
            self.paper_centrality.get(p, 0) for p in cited_core
        )
        
        # 计算所有核心论文的中心性总和
        total_centrality_sum = sum(
            self.paper_centrality.get(p, 0) for p in self.core_papers
        )
        
        wcr = cited_centrality_sum / total_centrality_sum if total_centrality_sum > 0 else 0
        
        return wcr, {
            "cited_core_papers": len(cited_core),
            "total_core_papers": len(self.core_papers),
            "cited_centrality_sum": cited_centrality_sum,
            "total_centrality_sum": total_centrality_sum,
            "missing_core_papers": list(self.core_papers - cited_papers)[:10]
        }
    
    def _calculate_cc(self, cited_papers: Set[str]) -> Tuple[float, Dict]:
        """
        计算社区覆盖率 (Community Coverage)
        
        CC = |covered_communities| / |total_communities|
        
        衡量综述是否覆盖了所有主要研究方向
        """
        if not self.communities:
            return 1.0, {"message": "No communities identified"}
        
        # 找出被引用论文所属的社区
        covered_communities = set()
        for paper_id in cited_papers:
            paper = self.papers.get(paper_id, {})
            category = paper.get("category", "")
            if category:
                covered_communities.add(category)
        
        cc = len(covered_communities) / len(self.communities)
        
        return cc, {
            "covered_communities": list(covered_communities),
            "total_communities": list(self.communities),
            "missing_communities": list(self.communities - covered_communities)
        }
    
    def _calculate_sc(
        self,
        cited_papers: Set[str],
        survey_outline: Optional[Dict]
    ) -> Tuple[float, Dict]:
        """
        计算结构一致性 (Structural Coherence)
        
        衡量综述结构是否与知识图谱结构一致
        """
        if not survey_outline:
            return 0.5, {"message": "No outline provided for SC calculation"}
        
        # 分析大纲章节与社区的对应关系
        sections = survey_outline.get("sections", [])
        if not sections:
            return 0.5, {"message": "Empty outline"}
        
        # 计算每个章节覆盖的社区
        section_community_coverage = []
        for section in sections:
            # 兼容两种格式: "title" (MEKG内部格式) 和 "section title" (SurveyX格式)
            section_title = section.get("section title", section.get("title", "")).lower()
            
            # 检查章节标题是否与某个社区相关
            matched_communities = []
            for community in self.communities:
                if community.lower() in section_title or section_title in community.lower():
                    matched_communities.append(community)
            
            section_community_coverage.append({
                "section": section.get("section title", section.get("title", "")),
                "matched_communities": matched_communities
            })
        
        # 计算覆盖的社区数
        all_matched = set()
        for item in section_community_coverage:
            all_matched.update(item["matched_communities"])
        
        sc = len(all_matched) / len(self.communities) if self.communities else 0.5
        
        return sc, {
            "section_coverage": section_community_coverage,
            "matched_communities": list(all_matched)
        }
    
    def _calculate_ra(
        self,
        content: str,
        cited_papers: Set[str]
    ) -> Tuple[float, Dict]:
        """
        计算关系准确性 (Relation Accuracy)
        
        衡量综述中描述的论文关系是否与图谱一致
        """
        # 从文本中抽取“关系描述句”并验证句内引用对是否在 MEKG 关系集中。
        # 近似策略：句子里同时出现 (>=2 个 citation) + (关系触发词) 即视为“提到了关系”。
        triggers = [
            "extend", "extends", "extended",
            "improve", "improves", "improved",
            "based on", "build on", "builds on", "build upon", "builds upon",
            "outperform", "outperforms", "outperformed",
            "follow", "follows", "following",
        ]

        if not content:
            return 0.5, {"message": "Empty content"}

        # 句子切分（粗略）
        sentences = re.split(r"(?<=[.!?])\s+", content)
        found_relations: List[Dict[str, Any]] = []
        correct_relations = 0
        total_relations = 0

        cite_pattern = re.compile(r'\\[cC]ite\w*(?:\[[^\]]*\])*\{([^}]+)\}')

        for sent in sentences:
            low = sent.lower()
            if not any(t in low for t in triggers):
                continue

            # 提取句内 citations 并 canonicalize
            raw_keys: List[str] = []
            for match in cite_pattern.findall(sent):
                for key in match.split(","):
                    key = key.strip()
                    if key:
                        raw_keys.append(key)

            cited_in_sentence: List[str] = []
            for key in raw_keys:
                canonical = self._canonicalize_key(key)
                if canonical:
                    cited_in_sentence.append(canonical)

            # 至少两个引用才可能表达“论文间关系”
            uniq = []
            for cid in cited_in_sentence:
                if cid not in uniq:
                    uniq.append(cid)
            if len(uniq) < 2:
                continue

            # 限制组合爆炸：最多取前 4 个引用做两两组合
            uniq = uniq[:4]
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    a, b = uniq[i], uniq[j]
                    total_relations += 1
                    is_correct = (a, b) in self.relation_index
                    if is_correct:
                        correct_relations += 1
                    if len(found_relations) < 20:
                        found_relations.append(
                            {
                                "source": a,
                                "target": b,
                                "sentence_snippet": sent.strip()[:200],
                                "in_mekg": is_correct,
                            }
                        )

        # 如果文本里几乎没有“关系句”，RA 不应默认满分（否则会虚高）
        ra = (correct_relations / total_relations) if total_relations > 0 else 0.5

        return ra, {
            "found_relations": found_relations,
            "correct_relations": correct_relations,
            "total_relations": total_relations,
            "note": "Heuristic: relation-trigger sentence with >=2 citations"
        }
    
    def _calculate_tc(self, cited_papers: Set[str]) -> Tuple[float, Dict]:
        """
        计算时间覆盖率 (Temporal Coverage)
        
        衡量综述是否覆盖了完整的时间范围
        """
        if not cited_papers:
            return 0.0, {"message": "No papers cited"}
        
        # 获取被引用论文的年份（统一为 int）
        cited_years: List[int] = []
        for paper_id in cited_papers:
            paper = self.papers.get(paper_id, {})
            year = paper.get("year")
            if isinstance(year, int):
                cited_years.append(year)
            elif isinstance(year, str) and year.isdigit():
                cited_years.append(int(year))
        
        if not cited_years:
            return 0.5, {"message": "No year information in cited papers"}
        
        # 计算时间覆盖
        min_cited = min(cited_years)
        max_cited = max(cited_years)
        
        expected_min, expected_max = self.year_range
        
        # 计算覆盖率
        expected_range = expected_max - expected_min + 1
        actual_range = max_cited - min_cited + 1
        
        # 检查是否覆盖了最新年份
        recency_bonus = 1.0 if max_cited >= expected_max - 1 else 0.8
        
        tc = min(1.0, (actual_range / expected_range) * recency_bonus)
        
        return tc, {
            "cited_year_range": (min_cited, max_cited),
            "expected_year_range": (expected_min, expected_max),
            "year_distribution": dict(sorted(
                {y: cited_years.count(y) for y in set(cited_years)}.items()
            ))
        }
    
    def generate_report(
        self,
        result: EvaluationResult,
        output_path: Optional[Path] = None
    ) -> str:
        """
        生成评估报告
        
        Args:
            result: 评估结果
            output_path: 输出路径（可选）
            
        Returns:
            报告内容
        """
        report = f"""
# MEKG Survey Evaluation Report

## Overview

| Metric | Score | Description |
|--------|-------|-------------|
| WCR | {result.wcr:.4f} | Weighted Centrality Recall - 核心论文覆盖率 |
| CC | {result.cc:.4f} | Community Coverage - 社区覆盖率 |
| SC | {result.sc:.4f} | Structural Coherence - 结构一致性 |
| RA | {result.ra:.4f} | Relation Accuracy - 关系准确性 |
| TC | {result.tc:.4f} | Temporal Coverage - 时间覆盖率 |
| **Overall** | **{result.overall_score:.4f}** | 综合得分 |

## Detailed Analysis

### 1. Weighted Centrality Recall (WCR)

- Cited core papers: {result.details.get('wcr', {}).get('cited_core_papers', 'N/A')}
- Total core papers: {result.details.get('wcr', {}).get('total_core_papers', 'N/A')}

Missing core papers (top 10):
{self._format_list(result.details.get('wcr', {}).get('missing_core_papers', []))}

### 2. Community Coverage (CC)

Covered communities:
{self._format_list(result.details.get('cc', {}).get('covered_communities', []))}

Missing communities:
{self._format_list(result.details.get('cc', {}).get('missing_communities', []))}

### 3. Structural Coherence (SC)

Section-Community mapping:
{self._format_section_coverage(result.details.get('sc', {}).get('section_coverage', []))}

### 4. Relation Accuracy (RA)

- Found relations: {result.details.get('ra', {}).get('total_relations', 0)}
- Correct relations: {result.details.get('ra', {}).get('correct_relations', 0)}

### 5. Temporal Coverage (TC)

- Cited year range: {result.details.get('tc', {}).get('cited_year_range', 'N/A')}
- Expected year range: {result.details.get('tc', {}).get('expected_year_range', 'N/A')}

Year distribution:
{self._format_year_distribution(result.details.get('tc', {}).get('year_distribution', {}))}

## Summary

- Total papers in MEKG: {result.details.get('total_papers_count', 'N/A')}
- Papers cited in survey: {result.details.get('cited_papers_count', 'N/A')}
- Core papers identified: {result.details.get('core_papers_count', 'N/A')}
- Unknown citation keys in survey: {result.details.get('unknown_citations_count', 0)}

Unknown citation sample (top 10):
{self._format_list(result.details.get('unknown_citations_sample', []))}

## Recommendations

{self._generate_recommendations(result)}
"""
        
        if output_path:
            output_path.write_text(report, encoding='utf-8')
            print(f"✅ 评估报告已保存到: {output_path}")
        
        return report
    
    def _format_list(self, items: List) -> str:
        if not items:
            return "- (none)"
        return "\n".join([f"- {item}" for item in items[:10]])
    
    def _format_section_coverage(self, coverage: List[Dict]) -> str:
        if not coverage:
            return "- (no data)"
        lines = []
        for item in coverage:
            section = item.get("section", "Unknown")
            communities = item.get("matched_communities", [])
            if communities:
                lines.append(f"- {section}: {', '.join(communities)}")
            else:
                lines.append(f"- {section}: (no match)")
        return "\n".join(lines)
    
    def _format_year_distribution(self, distribution: Dict) -> str:
        if not distribution:
            return "- (no data)"
        return "\n".join([f"- {year}: {count} papers" for year, count in distribution.items()])
    
    def _generate_recommendations(self, result: EvaluationResult) -> str:
        recommendations = []

        unknown_count = result.details.get("unknown_citations_count", 0) or 0
        if unknown_count > 0:
            sample = result.details.get("unknown_citations_sample", [])[:10]
            recommendations.append(
                "- **修复无效/未知引用**: 检测到综述中存在未在 MEKG 中出现的 citation key，"
                "建议检查是否为生成幻觉或 BibTeX key 不一致。"
                f"（示例: {', '.join(sample)}）"
            )

        if result.wcr < 0.7:
            recommendations.append(
                "- **提高核心论文覆盖率**: 建议引用更多高影响力的核心论文，"
                f"当前缺失的核心论文包括: {', '.join(result.details.get('wcr', {}).get('missing_core_papers', [])[:5])}"
            )
        
        if result.cc < 0.8:
            missing = result.details.get('cc', {}).get('missing_communities', [])
            if missing:
                recommendations.append(
                    f"- **扩展研究方向覆盖**: 建议增加对以下研究方向的讨论: {', '.join(missing[:3])}"
                )
        
        if result.sc < 0.6:
            recommendations.append(
                "- **优化综述结构**: 建议调整章节结构，使其更好地对应知识图谱中的社区划分"
            )
        
        if result.tc < 0.7:
            recommendations.append(
                "- **补充时间覆盖**: 建议引用更多近期论文，确保综述反映最新研究进展"
            )
        
        if not recommendations:
            recommendations.append("- 综述质量良好，各项指标均达到较高水平")
        
        return "\n".join(recommendations)


def evaluate_survey(
    mekg_json_path: Path,
    survey_content_path: Path,
    outline_path: Optional[Path] = None,
    output_path: Optional[Path] = None
) -> EvaluationResult:
    """
    评估综述质量
    
    Args:
        mekg_json_path: MEKG数据JSON文件路径
        survey_content_path: 综述内容文件路径
        outline_path: 大纲文件路径（可选）
        output_path: 报告输出路径（可选）
        
    Returns:
        EvaluationResult对象
    """
    # 加载数据
    with open(mekg_json_path, 'r', encoding='utf-8') as f:
        mekg_data = json.load(f)
    
    survey_content = survey_content_path.read_text(encoding='utf-8')
    
    survey_outline = None
    if outline_path and outline_path.exists():
        with open(outline_path, 'r', encoding='utf-8') as f:
            survey_outline = json.load(f)
    
    # 评估
    evaluator = MEKGEvaluator(mekg_data)
    result = evaluator.evaluate(survey_content, survey_outline)
    
    # 生成报告
    if output_path:
        evaluator.generate_report(result, output_path)
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        mekg_path = Path(sys.argv[1])
        content_path = Path(sys.argv[2])
        outline_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        output_path = Path(sys.argv[4]) if len(sys.argv) > 4 else None
        
        result = evaluate_survey(mekg_path, content_path, outline_path, output_path)
        print(result)
    else:
        print("Usage: python evaluator.py <mekg_json> <survey_content> [outline_json] [output_report]")
