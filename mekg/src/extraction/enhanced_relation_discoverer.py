"""
MEKG V2 增强关系发现器 - 学术严谨版

关系类型体系（21种，分5大类）：

一、结构关系（Structural）- 基于引用网络
   - cites, cited_by, co_citation, bibliographic_coupling

二、语义关系（Semantic）- 基于内容分析，需要LLM
   - extends, improves, applies, compares, combines, reproduces, refutes, supports

三、概念关系（Conceptual）- 基于方法论
   - is_variant_of, is_instance_of, shares_methodology, shares_task, 
   - shares_dataset, shares_baseline, shares_architecture

四、时序关系（Temporal）- 基于时间演进
   - precedes, succeeds, concurrent

五、作者关系（Authorship）- 基于作者信息
   - same_author, same_group

注意：两篇论文可以同时存在多种不同类型的关系（如 cites + improves）
"""

import time
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from tqdm import tqdm

from mekg.src.storage.persistent_graph_db import PersistentGraphDB


class AcademicRelationType(Enum):
    """学术论文关系类型"""
    # 结构关系
    CITES = "cites"
    CITED_BY = "cited_by"
    CO_CITATION = "co_citation"
    BIBLIOGRAPHIC_COUPLING = "bibliographic_coupling"
    # 语义关系
    EXTENDS = "extends"
    IMPROVES = "improves"
    APPLIES = "applies"
    COMPARES = "compares"
    COMBINES = "combines"
    REPRODUCES = "reproduces"
    REFUTES = "refutes"
    SUPPORTS = "supports"
    # 概念关系
    IS_VARIANT_OF = "is_variant_of"
    IS_INSTANCE_OF = "is_instance_of"
    SHARES_METHODOLOGY = "shares_methodology"
    SHARES_TASK = "shares_task"
    SHARES_DATASET = "shares_dataset"
    SHARES_BASELINE = "shares_baseline"
    SHARES_ARCHITECTURE = "shares_architecture"
    # 时序关系
    PRECEDES = "precedes"
    SUCCEEDS = "succeeds"
    CONCURRENT = "concurrent"
    # 作者关系
    SAME_AUTHOR = "same_author"
    SAME_GROUP = "same_group"


RELATION_METADATA = {
    "cites": {"directed": True, "category": "structural", "requires_llm": False},
    "cited_by": {"directed": True, "category": "structural", "requires_llm": False},
    "co_citation": {"directed": False, "category": "structural", "requires_llm": False},
    "bibliographic_coupling": {"directed": False, "category": "structural", "requires_llm": False},
    "extends": {"directed": True, "category": "semantic", "requires_llm": True},
    "improves": {"directed": True, "category": "semantic", "requires_llm": True},
    "applies": {"directed": True, "category": "semantic", "requires_llm": True},
    "compares": {"directed": False, "category": "semantic", "requires_llm": True},
    "combines": {"directed": True, "category": "semantic", "requires_llm": True},
    "reproduces": {"directed": True, "category": "semantic", "requires_llm": True},
    "refutes": {"directed": True, "category": "semantic", "requires_llm": True},
    "supports": {"directed": True, "category": "semantic", "requires_llm": True},
    "is_variant_of": {"directed": True, "category": "conceptual", "requires_llm": True},
    "is_instance_of": {"directed": True, "category": "conceptual", "requires_llm": True},
    "shares_methodology": {"directed": False, "category": "conceptual", "requires_llm": False},
    "shares_task": {"directed": False, "category": "conceptual", "requires_llm": False},
    "shares_dataset": {"directed": False, "category": "conceptual", "requires_llm": False},
    "shares_baseline": {"directed": False, "category": "conceptual", "requires_llm": False},
    "shares_architecture": {"directed": False, "category": "conceptual", "requires_llm": True},
    "precedes": {"directed": True, "category": "temporal", "requires_llm": False},
    "succeeds": {"directed": True, "category": "temporal", "requires_llm": False},
    "concurrent": {"directed": False, "category": "temporal", "requires_llm": False},
    "same_author": {"directed": False, "category": "authorship", "requires_llm": False},
    "same_group": {"directed": False, "category": "authorship", "requires_llm": False},
}


@dataclass
class DiscoveredRelation:
    """发现的关系"""
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    evidence: str = ""
    discovery_method: str = ""
    category: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id, "target_id": self.target_id,
            "relation_type": self.relation_type, "confidence": self.confidence,
            "evidence": self.evidence, "discovery_method": self.discovery_method,
            "category": self.category
        }


@dataclass
class DiscoveryResult:
    """发现结果"""
    relations: List[DiscoveredRelation] = field(default_factory=list)
    pairs_analyzed: int = 0
    time_elapsed: float = 0.0
    llm_calls: int = 0
    rule_discoveries: int = 0
    llm_discoveries: int = 0
    structural_count: int = 0
    semantic_count: int = 0
    conceptual_count: int = 0
    temporal_count: int = 0
    authorship_count: int = 0
    
    def __repr__(self):
        return f"DiscoveryResult(relations={len(self.relations)}, pairs={self.pairs_analyzed})"


RELATION_DISCOVERY_PROMPT = """你是学术论文关系分析专家。分析以下两篇论文的关系。

论文A: {title_a} ({year_a})
摘要: {abstract_a}
方法: {methods_a}

论文B: {title_b} ({year_b})
摘要: {abstract_b}
方法: {methods_b}

请分析这两篇论文之间可能存在的学术关系。只要有合理的关联就应该输出（置信度>0.4即可）。

可选关系类型：
- extends: A扩展B的方法/理论（A比B新，在B基础上增加新功能/场景）
- improves: A改进B的性能/效果（A比B新，在相同任务上取得更好结果）
- applies: A将B的方法应用到新领域/任务
- compares: A和B进行实验对比（通常在同一篇论文中对比）
- combines: A结合B和其他方法
- reproduces: A复现B的实验
- refutes: A反驳B的结论
- supports: A验证/支持B的结论或方法
- is_variant_of: A是B方法的变体（如BERT和RoBERTa）
- is_instance_of: A是B方法类别的具体实例
- shares_architecture: A和B使用相似的模型架构或技术框架

注意：
1. 如果两篇论文研究相似主题，很可能存在 shares_architecture 或 supports 关系
2. 如果A引用了B，通常存在 extends/improves/applies 中的一种关系
3. 同一领域的论文通常至少有 shares_architecture 关系

输出JSON：
```json
{{"relations": [{{"type": "关系类型", "direction": "A->B或B->A或bidirectional", "confidence": 0.4-1.0, "evidence": "简短证据说明"}}]}}
```
如果确实没有任何关系，返回空列表。只输出JSON。"""


class EnhancedRelationDiscoverer:
    """增强关系发现器 - 50线程并发，21种关系类型"""
    
    def __init__(
        self,
        db: Optional[PersistentGraphDB] = None,
        chat_agent: Optional[Any] = None,
        use_llm: bool = True,
        use_rules: bool = True,
        max_workers: int = None
    ):
        from src.configs.config import RELATION_DISCOVERY_WORKERS
        
        self.db = db
        self.chat_agent = chat_agent
        self.use_llm = use_llm and chat_agent is not None
        self.use_rules = use_rules
        self.max_workers = max_workers if max_workers is not None else RELATION_DISCOVERY_WORKERS
        logger.info(f"EnhancedRelationDiscoverer: LLM={self.use_llm}, Rules={use_rules}, Workers={self.max_workers}")
    
    def discover_relations_for_pair(self, paper_a: Dict, paper_b: Dict) -> List[DiscoveredRelation]:
        """发现两篇论文间的所有关系"""
        relations = []
        if self.use_rules:
            relations.extend(self._discover_by_rules(paper_a, paper_b))
        if self.use_llm:
            relations.extend(self._discover_by_llm_sync(paper_a, paper_b))
        return self._merge_relations(relations)
    
    def _discover_by_rules(self, paper_a: Dict, paper_b: Dict) -> List[DiscoveredRelation]:
        """规则发现 - 增强版，支持多种字段名"""
        relations = []
        pid_a = paper_a.get("paper_id") or paper_a.get("id", "")
        pid_b = paper_b.get("paper_id") or paper_b.get("id", "")
        
        # 从数据库获取引用关系（如果可用）
        refs_a, refs_b = set(), set()
        if self.db:
            # 获取A引用的论文
            refs_a = set(self.db.get_citations(pid_a, direction="citing"))
            # 获取B引用的论文
            refs_b = set(self.db.get_citations(pid_b, direction="citing"))
        
        # 回退到论文字段（支持多种字段名）
        if not refs_a:
            refs_a = set(paper_a.get("referenced_works", []) or paper_a.get("references", []) or [])
        if not refs_b:
            refs_b = set(paper_b.get("referenced_works", []) or paper_b.get("references", []) or [])
        
        year_a = paper_a.get("year") or paper_a.get("publication_year") or 0
        year_b = paper_b.get("year") or paper_b.get("publication_year") or 0
        
        # 结构关系 - 引用
        if pid_b in refs_a:
            relations.append(DiscoveredRelation(pid_a, pid_b, "cites", 1.0, "Direct citation", "rule", "structural"))
        if pid_a in refs_b:
            relations.append(DiscoveredRelation(pid_a, pid_b, "cited_by", 1.0, "Cited by B", "rule", "structural"))
        
        # 书目耦合 - 降低阈值从3到2
        common_refs = refs_a & refs_b
        if len(common_refs) >= 2:
            relations.append(DiscoveredRelation(pid_a, pid_b, "bibliographic_coupling",
                min(len(common_refs)/8, 1.0), f"Share {len(common_refs)} refs", "rule", "structural"))
        
        # 概念关系 - 方法实体
        methods_a = set(paper_a.get("method_entities", []) or [])
        methods_b = set(paper_b.get("method_entities", []) or [])
        if methods_a and methods_b:
            common = methods_a & methods_b
            if common:
                score = len(common) / max(len(methods_a), len(methods_b))
                if score >= 0.2:  # 降低阈值从0.3到0.2
                    relations.append(DiscoveredRelation(pid_a, pid_b, "shares_methodology",
                        score, f"Methods: {', '.join(list(common)[:3])}", "rule", "conceptual"))
        
        # 概念关系 - 任务/领域
        tasks_a = set(paper_a.get("tasks", []) or paper_a.get("research_domains", []) or [])
        tasks_b = set(paper_b.get("tasks", []) or paper_b.get("research_domains", []) or [])
        if tasks_a and tasks_b:
            common = tasks_a & tasks_b
            if common:
                relations.append(DiscoveredRelation(pid_a, pid_b, "shares_task",
                    len(common)/max(len(tasks_a), len(tasks_b)), f"Tasks: {', '.join(list(common)[:2])}", "rule", "conceptual"))
        
        # 概念关系 - 数据集
        datasets_a = set(paper_a.get("datasets", []) or [])
        datasets_b = set(paper_b.get("datasets", []) or [])
        if datasets_a and datasets_b:
            common = datasets_a & datasets_b
            if common:
                relations.append(DiscoveredRelation(pid_a, pid_b, "shares_dataset", 0.9,
                    f"Datasets: {', '.join(list(common)[:2])}", "rule", "conceptual"))
        
        # 概念关系 - 基于OpenAlex concepts的相似性
        concepts_a = paper_a.get("concepts", []) or []
        concepts_b = paper_b.get("concepts", []) or []
        if concepts_a and concepts_b:
            # 提取概念名称
            concept_names_a = set(c.get("name", "").lower() for c in concepts_a if isinstance(c, dict))
            concept_names_b = set(c.get("name", "").lower() for c in concepts_b if isinstance(c, dict))
            common_concepts = concept_names_a & concept_names_b
            if len(common_concepts) >= 2:
                score = len(common_concepts) / max(len(concept_names_a), len(concept_names_b), 1)
                relations.append(DiscoveredRelation(pid_a, pid_b, "shares_task",
                    min(score + 0.3, 1.0), f"Concepts: {', '.join(list(common_concepts)[:3])}", "rule", "conceptual"))
        
        # 时序关系
        if year_a and year_b:
            if year_a < year_b and pid_a in refs_b:
                relations.append(DiscoveredRelation(pid_a, pid_b, "precedes", 0.9,
                    f"A({year_a}) precedes B({year_b})", "rule", "temporal"))
            elif year_b < year_a and pid_b in refs_a:
                relations.append(DiscoveredRelation(pid_a, pid_b, "succeeds", 0.9,
                    f"A({year_a}) succeeds B({year_b})", "rule", "temporal"))
            elif abs(year_a - year_b) <= 1 and len(common_refs) >= 3:  # 降低阈值从5到3
                relations.append(DiscoveredRelation(pid_a, pid_b, "concurrent", 0.7,
                    f"Same period ({year_a},{year_b})", "rule", "temporal"))
        
        # 作者关系 - 支持多种字段名
        authors_a = set(paper_a.get("author_ids", []) or [])
        authors_b = set(paper_b.get("author_ids", []) or [])
        # 也检查作者名字
        if not authors_a:
            authors_a = set(a.lower() for a in (paper_a.get("authors", []) or []) if isinstance(a, str))
        if not authors_b:
            authors_b = set(a.lower() for a in (paper_b.get("authors", []) or []) if isinstance(a, str))
        if authors_a and authors_b and (authors_a & authors_b):
            relations.append(DiscoveredRelation(pid_a, pid_b, "same_author", 1.0,
                f"Share {len(authors_a & authors_b)} author(s)", "rule", "authorship"))
        
        return relations
    
    def _discover_by_llm_sync(self, paper_a: Dict, paper_b: Dict) -> List[DiscoveredRelation]:
        """LLM发现语义关系"""
        if not self.chat_agent:
            return []
        
        pid_a = paper_a.get("paper_id") or paper_a.get("id", "")
        pid_b = paper_b.get("paper_id") or paper_b.get("id", "")
        
        # 获取方法实体，支持多种格式
        methods_a = paper_a.get("method_entities", []) or []
        methods_b = paper_b.get("method_entities", []) or []
        if not methods_a:
            # 尝试从concepts中提取
            concepts = paper_a.get("concepts", []) or []
            methods_a = [c.get("name", "") for c in concepts[:5] if isinstance(c, dict)]
        if not methods_b:
            concepts = paper_b.get("concepts", []) or []
            methods_b = [c.get("name", "") for c in concepts[:5] if isinstance(c, dict)]
        
        prompt = RELATION_DISCOVERY_PROMPT.format(
            title_a=paper_a.get("title", ""),
            abstract_a=(paper_a.get("abstract", "") or "")[:400],
            year_a=paper_a.get("year", "?"),
            methods_a=", ".join(methods_a[:5]) if methods_a else "N/A",
            title_b=paper_b.get("title", ""),
            abstract_b=(paper_b.get("abstract", "") or "")[:400],
            year_b=paper_b.get("year", "?"),
            methods_b=", ".join(methods_b[:5]) if methods_b else "N/A"
        )
        
        try:
            # 使用120秒超时
            response = self.chat_agent.remote_chat(prompt, temperature=0.3, timeout=120)
            return self._parse_llm_response(response, pid_a, pid_b)
        except Exception as e:
            logger.debug(f"LLM failed for {pid_a[:10]}-{pid_b[:10]}: {e}")
            return []
    
    def _parse_llm_response(self, response: str, pid_a: str, pid_b: str) -> List[DiscoveredRelation]:
        """解析LLM响应 - 更宽松的解析"""
        relations = []
        try:
            # 尝试多种JSON提取方式
            json_str = None
            match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                # 尝试直接解析
                match = re.search(r'\{.*"relations".*\}', response, re.DOTALL)
                if match:
                    json_str = match.group(0)
                else:
                    json_str = response
            
            data = json.loads(json_str)
            
            for rel in data.get("relations", []):
                rel_type = rel.get("type", "")
                if rel_type not in RELATION_METADATA:
                    continue
                # 允许所有关系类型，不仅仅是requires_llm的
                
                direction = rel.get("direction", "A->B")
                confidence = float(rel.get("confidence", 0.5))
                evidence = rel.get("evidence", "")
                category = RELATION_METADATA[rel_type]["category"]
                is_directed = RELATION_METADATA[rel_type]["directed"]
                
                # 降低置信度阈值从隐式的0.6到0.4
                if confidence < 0.4:
                    continue
                
                if is_directed:
                    if direction == "A->B":
                        src, tgt = pid_a, pid_b
                    elif direction == "B->A":
                        src, tgt = pid_b, pid_a
                    elif direction == "bidirectional":
                        # 双向关系，添加两条
                        relations.append(DiscoveredRelation(pid_a, pid_b, rel_type, confidence, evidence, "llm", category))
                        relations.append(DiscoveredRelation(pid_b, pid_a, rel_type, confidence, evidence, "llm", category))
                        continue
                    else:
                        # 默认A->B
                        src, tgt = pid_a, pid_b
                else:
                    src, tgt = sorted([pid_a, pid_b])
                
                relations.append(DiscoveredRelation(src, tgt, rel_type, confidence, evidence, "llm", category))
        except Exception as e:
            logger.debug(f"Parse failed: {e}, response: {response[:200]}")
        return relations
    
    def _merge_relations(self, relations: List[DiscoveredRelation]) -> List[DiscoveredRelation]:
        """去重合并"""
        grouped = {}
        for rel in relations:
            is_directed = RELATION_METADATA.get(rel.relation_type, {}).get("directed", True)
            if is_directed:
                key = (rel.source_id, rel.target_id, rel.relation_type)
            else:
                key = (min(rel.source_id, rel.target_id), max(rel.source_id, rel.target_id), rel.relation_type)
            if key not in grouped or rel.confidence > grouped[key].confidence:
                grouped[key] = rel
        return list(grouped.values())
    
    def batch_discover_concurrent(
        self, paper_ids: List[str], max_pairs: int = 1000,
        min_confidence: float = 0.4, save_to_db: bool = True
    ) -> DiscoveryResult:
        """批量发现 - 50线程并发，降低置信度阈值"""
        start = time.time()
        result = DiscoveryResult()
        
        if not self.db:
            logger.warning("No database provided, cannot batch discover")
            return result
        
        # 获取论文数据
        papers = {}
        for pid in paper_ids:
            paper = self.db.get_paper(pid)
            if paper:
                # 确保paper_id字段存在
                if 'paper_id' not in paper:
                    paper['paper_id'] = paper.get('id', pid)
                papers[pid] = paper
        
        if not papers:
            logger.warning("No papers found in database")
            return result
        
        candidates = self._generate_candidate_pairs(list(papers.keys()), max_pairs)
        logger.info(f"Batch discover: {len(papers)} papers, {len(candidates)} pairs, {self.max_workers} workers")
        
        if not candidates:
            logger.warning("No candidate pairs generated")
            return result
        
        tasks = [(papers[a], papers[b]) for a, b in candidates if a in papers and b in papers]
        all_relations = []
        
        # 用于统计（合并前）
        pre_merge_stats = {
            "structural": 0, "semantic": 0, "conceptual": 0,
            "temporal": 0, "authorship": 0, "rule": 0, "llm": 0
        }
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.discover_relations_for_pair, t[0], t[1]): i for i, t in enumerate(tasks)}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Discovering"):
                try:
                    rels = future.result()
                    result.pairs_analyzed += 1
                    if self.use_llm:
                        result.llm_calls += 1
                    for rel in rels:
                        if rel.confidence >= min_confidence:
                            all_relations.append(rel)
                            # 统计（合并前）
                            if rel.discovery_method == "llm":
                                pre_merge_stats["llm"] += 1
                            else:
                                pre_merge_stats["rule"] += 1
                            pre_merge_stats[rel.category] = pre_merge_stats.get(rel.category, 0) + 1
                except Exception as e:
                    logger.debug(f"Task failed: {e}")
        
        logger.info(f"Pre-merge stats: {len(all_relations)} relations")
        logger.info(f"  By method: rule={pre_merge_stats['rule']}, llm={pre_merge_stats['llm']}")
        logger.info(f"  By category: structural={pre_merge_stats['structural']}, semantic={pre_merge_stats['semantic']}, conceptual={pre_merge_stats['conceptual']}")
        
        # 合并关系
        result.relations = self._merge_relations(all_relations)
        
        # 统计合并后的结果
        for rel in result.relations:
            if rel.discovery_method == "llm":
                result.llm_discoveries += 1
            else:
                result.rule_discoveries += 1
            if rel.category == "structural":
                result.structural_count += 1
            elif rel.category == "semantic":
                result.semantic_count += 1
            elif rel.category == "conceptual":
                result.conceptual_count += 1
            elif rel.category == "temporal":
                result.temporal_count += 1
            elif rel.category == "authorship":
                result.authorship_count += 1
        
        logger.info(f"Post-merge: {len(result.relations)} unique relations")
        
        # 保存到数据库
        if save_to_db and self.db:
            saved = 0
            failed = 0
            for rel in result.relations:
                try:
                    if rel.relation_type == "cites":
                        if self.db.add_citation(rel.source_id, rel.target_id):
                            saved += 1
                        else:
                            failed += 1
                    else:
                        if self.db.add_relation(rel.source_id, rel.target_id, rel.relation_type,
                                               rel.confidence, evidence=rel.evidence):
                            saved += 1
                        else:
                            failed += 1
                except Exception as e:
                    logger.debug(f"Failed to save relation {rel.source_id}->{rel.target_id}: {e}")
                    failed += 1
            logger.info(f"Saved {saved} relations to DB (failed: {failed})")
        
        result.time_elapsed = time.time() - start
        logger.info(f"Discovery done: {result}")
        logger.info(f"  Structural: {result.structural_count}, Semantic: {result.semantic_count}")
        logger.info(f"  Conceptual: {result.conceptual_count}, Temporal: {result.temporal_count}")
        return result
    
    def _generate_candidate_pairs(self, paper_ids: List[str], max_pairs: int) -> List[Tuple[str, str]]:
        """生成候选对"""
        candidates = set()
        paper_set = set(paper_ids)
        
        if self.db:
            # 引用邻居
            for pid in paper_ids[:100]:
                for neighbor in self.db.get_neighbors(pid):
                    if neighbor in paper_set and neighbor != pid:
                        candidates.add(tuple(sorted([pid, neighbor])))
            
            # 同社区
            communities = {}
            for pid in paper_ids:
                paper = self.db.get_paper(pid)
                if paper and paper.get("community_id") is not None:
                    cid = paper["community_id"]
                    communities.setdefault(cid, []).append(pid)
            
            import itertools
            for comm_papers in communities.values():
                if len(comm_papers) > 1:
                    for pair in itertools.combinations(comm_papers[:20], 2):
                        candidates.add(tuple(sorted(pair)))
        
        # 补充随机对
        if len(candidates) < max_pairs:
            import itertools, random
            all_pairs = list(itertools.combinations(paper_ids[:200], 2))
            random.shuffle(all_pairs)
            for pair in all_pairs:
                if len(candidates) >= max_pairs:
                    break
                candidates.add(tuple(sorted(pair)))
        
        result = list(candidates)
        if len(result) > max_pairs:
            import random
            result = random.sample(result, max_pairs)
        return result
    
    # 兼容旧接口
    async def discover_relations(self, paper_a: Dict, paper_b: Dict) -> List[DiscoveredRelation]:
        return self.discover_relations_for_pair(paper_a, paper_b)
    
    async def batch_discover(self, paper_ids: List[str], max_pairs: int = 1000, min_confidence: float = 0.5) -> DiscoveryResult:
        return self.batch_discover_concurrent(paper_ids, max_pairs, min_confidence)
    
    def discover_relations_sync(self, paper_a: Dict, paper_b: Dict) -> List[DiscoveredRelation]:
        return self.discover_relations_for_pair(paper_a, paper_b)


if __name__ == "__main__":
    # 测试
    discoverer = EnhancedRelationDiscoverer(use_llm=False)
    paper_a = {"paper_id": "W001", "title": "BERT", "year": 2018, "references": ["W002"], 
               "method_entities": ["transformer", "attention"]}
    paper_b = {"paper_id": "W002", "title": "Attention Is All You Need", "year": 2017, 
               "method_entities": ["transformer", "attention"]}
    
    rels = discoverer.discover_relations_for_pair(paper_a, paper_b)
    print(f"Found {len(rels)} relations:")
    for r in rels:
        print(f"  {r.source_id} --[{r.relation_type}]--> {r.target_id} ({r.confidence:.2f}, {r.category})")