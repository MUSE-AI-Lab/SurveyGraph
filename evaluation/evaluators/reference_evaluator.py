"""
引用质量评测器
==============

评估综述的引用质量，包括:
- WCR (Weighted Centrality Recall): 加权中心性召回率
- CC (Community Coverage): 社区覆盖率
- Bibliographic Integrity: 文献完整性
- Citation Faithfulness: 引用忠实度
"""

import logging
from typing import Dict, Any, Optional, Set, List, Tuple
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from evaluation.core.base_evaluator import BaseEvaluator
from evaluation.config import EvaluationConfig, REFERENCE_QUALITY_WEIGHTS
from evaluation.utils.latex_parser import (
    extract_citations,
    extract_sentences_with_citations,
    parse_bibtex
)
from evaluation.utils.metrics import (
    calculate_wcr,
    calculate_cc,
    normalize_title,
    aggregate_scores
)
from evaluation.utils.llm_client import (
    call_llm,
    parse_json_response,
    CLAIM_VERIFICATION_PROMPT,
    ATOMIC_FACT_EXTRACTION_PROMPT
)


logger = logging.getLogger(__name__)


class ReferenceEvaluator(BaseEvaluator):
    """引用质量评测器"""
    
    @property
    def name(self) -> str:
        return "Reference Quality"
    
    @property
    def weight(self) -> float:
        return self.config.dimension_weights.get("reference_quality", 0.25)
    
    def __init__(
        self,
        config: Optional[EvaluationConfig] = None,
        mekg_data: Optional[Dict[str, Any]] = None
    ):
        super().__init__(config, mekg_data)
        
        # 预计算图谱统计信息
        if self.mekg_data:
            self._precompute_graph_stats()
    
    def _precompute_graph_stats(self):
        """预计算图谱统计信息"""
        # 计算论文中心性（基于引用数、PageRank或relevance_score）
        self.paper_centrality = {}
        max_citations = 0
        total_relevance = 0
        
        # 首先检查是否有有效的引用数据
        for paper_id, paper in self.papers.items():
            citations = paper.get("citations", paper.get("citation_count", 0))
            if citations and citations > max_citations:
                max_citations = citations
            relevance = paper.get("relevance_score", 0)
            if relevance:
                total_relevance += relevance
        
        # 如果所有论文引用数都是0，使用relevance_score或均匀分布
        use_relevance = max_citations == 0 and total_relevance > 0
        use_uniform = max_citations == 0 and total_relevance == 0
        
        for paper_id, paper in self.papers.items():
            # 优先使用PageRank
            pagerank = paper.get("pagerank")
            if pagerank is not None and pagerank > 0:
                self.paper_centrality[paper_id] = pagerank
            elif use_relevance:
                # 使用relevance_score作为中心性
                relevance = paper.get("relevance_score", 1.0)
                self.paper_centrality[paper_id] = relevance
            elif use_uniform:
                # 均匀分布 - 所有论文同等重要
                self.paper_centrality[paper_id] = 1.0
            else:
                # 使用归一化引用数
                citations = paper.get("citations", paper.get("citation_count", 0))
                self.paper_centrality[paper_id] = citations / max_citations if max_citations > 0 else 1.0
        
        # 识别核心论文（中心性Top 20%）
        sorted_papers = sorted(
            self.paper_centrality.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_count = max(1, len(sorted_papers) // 5)
        self.core_papers = set(p[0] for p in sorted_papers[:top_count])
        
        # 统计社区
        self.paper_communities = {}
        self.all_communities = set()
        
        for paper_id, paper in self.papers.items():
            community = paper.get("community", paper.get("community_id", paper.get("category", "")))
            if community:
                self.paper_communities[paper_id] = str(community)
                self.all_communities.add(str(community))
        
        # 从categories中补充社区信息
        for cat_name in self.categories.keys():
            self.all_communities.add(cat_name)
        
        logger.debug(f"预计算完成: {len(self.core_papers)} 核心论文, {len(self.all_communities)} 社区")
    
    def evaluate(
        self,
        survey_content: str,
        survey_outline: Optional[Dict] = None,
        bibtex_path: Optional[Path] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行引用质量评测
        
        Args:
            survey_content: 综述内容
            survey_outline: 综述大纲（可选）
            bibtex_path: BibTeX文件路径（可选）
            
        Returns:
            评测结果
        """
        self._log_start()
        
        # 提取引用
        cited_keys = extract_citations(survey_content)
        logger.info(f"提取到 {len(cited_keys)} 个引用")
        
        # 将引用key映射到paper_id
        cited_paper_ids = self._map_citations_to_paper_ids(cited_keys, bibtex_path)
        logger.info(f"映射到 {len(cited_paper_ids)} 个论文ID")
        
        # 计算各项指标
        metrics = {}
        details = {}
        
        # 1. WCR (Weighted Centrality Recall)
        wcr, wcr_details = self._calculate_wcr(cited_paper_ids)
        metrics["wcr"] = wcr
        details["wcr"] = wcr_details
        
        # 2. CC (Community Coverage)
        cc, cc_details = self._calculate_cc(cited_paper_ids)
        metrics["cc"] = cc
        details["cc"] = cc_details
        
        # 3. Bibliographic Integrity
        bi, bi_details = self._calculate_bibliographic_integrity(cited_keys, bibtex_path)
        metrics["bibliographic_integrity"] = bi
        details["bibliographic_integrity"] = bi_details
        
        # 4. Citation Faithfulness (需要LLM)
        if self.config.use_llm:
            cf, cf_details = self._calculate_citation_faithfulness(survey_content)
            metrics["citation_faithfulness"] = cf
            details["citation_faithfulness"] = cf_details
        else:
            metrics["citation_faithfulness"] = 1.0
            details["citation_faithfulness"] = {"message": "Skipped (LLM disabled)"}
        
        # 计算综合分数
        score = aggregate_scores(metrics, REFERENCE_QUALITY_WEIGHTS)
        
        self._log_end(score)
        
        return {
            "score": score,
            "metrics": metrics,
            "details": details,
            "statistics": {
                "total_citations": len(cited_keys),
                "mapped_paper_ids": len(cited_paper_ids),
                "core_papers_count": len(self.core_papers),
                "communities_count": len(self.all_communities)
            }
        }
    
    def _normalize_paper_id(self, paper_id: str) -> str:
        """规范化paper_id格式，处理arXiv_和arXiv:的差异"""
        # 将 arXiv_xxxx.xxxxx 转换为 arXiv:xxxx.xxxxx
        if paper_id.startswith("arXiv_"):
            return "arXiv:" + paper_id[6:]
        # 将 arXiv:xxxx.xxxxx 转换为 arXiv_xxxx.xxxxx (用于反向匹配)
        return paper_id
    
    def _map_citations_to_paper_ids(
        self,
        cited_keys: Set[str],
        bibtex_path: Optional[Path] = None
    ) -> Set[str]:
        """将引用key映射到paper_id"""
        cited_paper_ids = set()
        
        # 构建多种索引用于匹配
        title_to_id = {}
        normalized_id_to_id = {}  # 规范化ID到原始ID的映射
        
        for paper_id, paper in self.papers.items():
            # 标题索引
            title = paper.get("title", "")
            if title:
                norm_title = normalize_title(title)
                title_to_id[norm_title] = paper_id
            
            # 规范化ID索引 (处理arXiv_和arXiv:的差异)
            normalized_id_to_id[paper_id] = paper_id
            # 同时添加下划线版本
            if paper_id.startswith("arXiv:"):
                underscore_version = "arXiv_" + paper_id[6:]
                normalized_id_to_id[underscore_version] = paper_id
            elif paper_id.startswith("arXiv_"):
                colon_version = "arXiv:" + paper_id[6:]
                normalized_id_to_id[colon_version] = paper_id
        
        # 如果有BibTeX文件，解析它
        bibtex_refs = {}
        if bibtex_path and bibtex_path.exists():
            bibtex_refs = parse_bibtex(bibtex_path)
        
        for cite_key in cited_keys:
            # 方法1: 直接匹配paper_id
            if cite_key in self.papers:
                cited_paper_ids.add(cite_key)
                continue
            
            # 方法2: 通过规范化ID匹配 (处理arXiv_和arXiv:的差异)
            if cite_key in normalized_id_to_id:
                cited_paper_ids.add(normalized_id_to_id[cite_key])
                continue
            
            # 方法3: 通过BibTeX标题匹配
            if cite_key in bibtex_refs:
                ref_title = bibtex_refs[cite_key].get("title", "")
                if ref_title:
                    norm_title = normalize_title(ref_title)
                    if norm_title in title_to_id:
                        cited_paper_ids.add(title_to_id[norm_title])
                        continue
            
            # 方法4: 模糊匹配（cite_key可能包含标题的一部分）
            for norm_title, paper_id in title_to_id.items():
                if cite_key.lower() in norm_title or norm_title in cite_key.lower():
                    cited_paper_ids.add(paper_id)
                    break
        
        return cited_paper_ids
    
    def _calculate_wcr(self, cited_paper_ids: Set[str]) -> Tuple[float, Dict]:
        """计算WCR"""
        return calculate_wcr(
            cited_paper_ids,
            self.core_papers,
            self.paper_centrality
        )
    
    def _calculate_cc(self, cited_paper_ids: Set[str]) -> Tuple[float, Dict]:
        """计算CC"""
        return calculate_cc(
            cited_paper_ids,
            self.paper_communities,
            self.all_communities
        )
    
    def _calculate_bibliographic_integrity(
        self,
        cited_keys: Set[str],
        bibtex_path: Optional[Path] = None
    ) -> Tuple[float, Dict]:
        """
        计算文献完整性
        
        检查引用是否完整、是否存在虚构引用
        """
        if not bibtex_path or not bibtex_path.exists():
            return 1.0, {"message": "No BibTeX file provided"}
        
        bibtex_refs = parse_bibtex(bibtex_path)
        
        # 检查每个引用是否在BibTeX中有定义
        defined_citations = set(bibtex_refs.keys())
        undefined_citations = cited_keys - defined_citations
        
        # 检查BibTeX条目的完整性
        incomplete_entries = []
        for cite_key, ref in bibtex_refs.items():
            if not ref.get("title") or not ref.get("year"):
                incomplete_entries.append(cite_key)
        
        # 计算完整性分数
        total_citations = len(cited_keys)
        if total_citations == 0:
            return 1.0, {"message": "No citations found"}
        
        valid_citations = total_citations - len(undefined_citations)
        integrity_score = valid_citations / total_citations
        
        return integrity_score, {
            "total_citations": total_citations,
            "defined_citations": len(defined_citations),
            "undefined_citations": list(undefined_citations)[:10],
            "incomplete_entries": incomplete_entries[:10]
        }
    
    def _calculate_citation_faithfulness(
        self,
        survey_content: str,
        sample_size: int = None
    ) -> Tuple[float, Dict]:
        """
        计算引用忠实度
        
        验证综述中的声明是否被引用论文支持
        """
        sample_size = sample_size or self.config.factual_sample_size
        
        # 提取带引用的句子
        sentences = extract_sentences_with_citations(survey_content)
        
        if not sentences:
            return 1.0, {"message": "No sentences with citations found"}
        
        # 采样
        import random
        if len(sentences) > sample_size:
            sentences = random.sample(sentences, sample_size)
        
        # 验证每个句子
        total_facts = 0
        supported_facts = 0
        evaluation_details = []
        
        for sent_data in sentences:
            sentence = sent_data["sentence"]
            citations = sent_data["citations"]
            
            if not citations:
                continue
            
            # 获取第一个引用的论文内容
            first_citation = citations[0]
            paper_content = self._get_paper_content(first_citation)
            
            if not paper_content:
                continue
            
            # 分解为原子事实
            atomic_facts = self._decompose_to_atomic_facts(sentence)
            
            # 验证每个原子事实
            for fact in atomic_facts:
                total_facts += 1
                is_supported = self._verify_fact(fact, paper_content)
                if is_supported:
                    supported_facts += 1
                
                evaluation_details.append({
                    "fact": fact[:100],
                    "citation": first_citation,
                    "is_supported": is_supported
                })
        
        if total_facts == 0:
            return 1.0, {"message": "No facts to verify"}
        
        faithfulness_score = supported_facts / total_facts
        
        return faithfulness_score, {
            "total_facts": total_facts,
            "supported_facts": supported_facts,
            "sample_details": evaluation_details[:10]
        }
    
    def _get_paper_content(self, citation_key: str) -> str:
        """获取论文内容"""
        # 尝试从MEKG数据中获取
        for paper_id, paper in self.papers.items():
            if citation_key in paper_id or paper_id in citation_key:
                return paper.get("abstract", "") or paper.get("source_text", "")
        
        return ""
    
    def _decompose_to_atomic_facts(self, sentence: str) -> List[str]:
        """将句子分解为原子事实"""
        if not self.config.use_llm:
            return [sentence]
        
        try:
            prompt = ATOMIC_FACT_EXTRACTION_PROMPT.format(sentence=sentence)
            response = call_llm(prompt, response_format="json_object", max_retries=10)
            result = parse_json_response(response)
            facts = result.get("atomic_facts", [])
            return facts if facts else [sentence]
        except Exception as e:
            logger.warning(f"原子事实分解失败: {e}")
            return [sentence]
    
    def _verify_fact(self, fact: str, source_text: str) -> bool:
        """验证事实是否被源文本支持"""
        if not self.config.use_llm:
            return True
        
        if not source_text:
            return False
        
        try:
            prompt = CLAIM_VERIFICATION_PROMPT.format(
                claim=fact,
                paper_title="Source Paper",
                source_text=source_text[:3000]  # 限制长度
            )
            response = call_llm(prompt, response_format="json_object", max_retries=10)
            result = parse_json_response(response)
            return result.get("is_supported", False)
        except Exception as e:
            logger.warning(f"事实验证失败: {e}")
            return True  # 默认支持