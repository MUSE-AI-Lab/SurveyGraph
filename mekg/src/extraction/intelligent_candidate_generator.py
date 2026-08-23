"""
智能候选对生成器

第三阶段核心组件：高效生成需要LLM判断的候选论文对
结合RAG（内容相似性）和网络结构（引用关系）

主要功能：
1. 核心-核心候选对生成
2. 非核心论文锚定到核心论文
3. 基于同被引/文献耦合的补充连接
4. 时间和社区规则剪枝
"""

from typing import List, Dict, Any, Set, Tuple, Optional
from collections import defaultdict
import math

import networkx as nx
from loguru import logger

# 尝试导入向量化库
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logger.warning("sentence-transformers未安装，将使用基于关键词的相似度")


class IntelligentCandidateGenerator:
    """
    智能候选对生成器
    
    通过分层策略生成候选论文对，大幅减少LLM调用：
    - 层1: 核心论文完全连接
    - 层2: 非核心论文锚定到相似核心论文（RAG + 结构）
    - 层3: 基于文献耦合/同被引的补充连接
    """
    
    def __init__(
        self,
        papers_index: Dict[str, Dict[str, Any]],
        citation_graph: nx.DiGraph,
        core_papers: List[str],
        reference_map: Dict[str, Set[str]],
        cited_by_map: Dict[str, Set[str]]
    ):
        """
        初始化生成器
        
        Args:
            papers_index: 论文索引 {paper_id: paper_data}
            citation_graph: 引文网络
            core_papers: 核心论文ID列表
            reference_map: 引用映射 {paper: papers it cites}
            cited_by_map: 被引映射 {paper: papers that cite it}
        """
        self.papers_index = papers_index
        self.citation_graph = citation_graph
        self.core_papers = set(core_papers)
        self.reference_map = reference_map
        self.cited_by_map = cited_by_map
        
        # 非核心论文
        all_papers = set(papers_index.keys())
        self.regular_papers = all_papers - self.core_papers
        
        # 向量化模型（延迟加载）
        self.embedder = None
        self.embeddings: Dict[str, Any] = {}
        
        logger.info(
            f"初始化候选对生成器: "
            f"{len(self.core_papers)} 核心论文, "
            f"{len(self.regular_papers)} 普通论文"
        )
    
    def _ensure_embeddings(self):
        """确保已计算文本嵌入向量"""
        if self.embeddings:
            return
        
        if not HAS_SENTENCE_TRANSFORMERS:
            logger.warning("无法使用向量嵌入，将使用关键词匹配")
            return
        
        logger.info("初始化向量嵌入模型...")
        
        try:
            # 使用轻量级模型
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
            
            # 为所有论文生成嵌入
            texts = []
            paper_ids = []
            
            for paper_id, paper in self.papers_index.items():
                # 使用标题+摘要前500字符
                title = paper.get('title', '')
                abstract = paper.get('abstract', '')[:500]
                text = f"{title}. {abstract}"
                texts.append(text)
                paper_ids.append(paper_id)
            
            logger.info(f"生成 {len(texts)} 篇论文的向量嵌入...")
            embeddings_array = self.embedder.encode(
                texts,
                show_progress_bar=True,
                batch_size=32
            )
            
            for i, paper_id in enumerate(paper_ids):
                self.embeddings[paper_id] = embeddings_array[i]
            
            logger.info(f"向量嵌入完成: {len(self.embeddings)} 篇论文")
            
        except Exception as e:
            logger.error(f"向量嵌入失败: {e}")
            self.embedder = None
    
    def generate_core_core_pairs(self) -> List[Tuple[str, str]]:
        """
        层1：生成核心论文之间的候选对
        
        核心论文之间完全连接，但应用时间剪枝
        
        Returns:
            候选对列表
        """
        logger.info("层1: 生成核心-核心候选对")
        
        pairs = []
        core_list = list(self.core_papers)
        
        for i, paper_a in enumerate(core_list):
            paper_a_data = self.papers_index.get(paper_a, {})
            year_a = paper_a_data.get('year', 2024)
            
            for paper_b in core_list[i+1:]:
                paper_b_data = self.papers_index.get(paper_b, {})
                year_b = paper_b_data.get('year', 2024)
                
                # 时间剪枝：跳过年份相差超过10年的（可能不太相关）
                if abs(year_a - year_b) <= 10:
                    pairs.append((paper_a, paper_b))
        
        logger.info(f"  生成 {len(pairs)} 个核心-核心候选对")
        return pairs
    
    def generate_regular_to_core_pairs(
        self,
        top_k: int = 5,
        use_embeddings: bool = True
    ) -> List[Tuple[str, str]]:
        """
        层2：为普通论文找到最相关的核心论文
        
        使用混合锚定策略：
        - 内容锚定（RAG）：向量相似度
        - 结构锚定：引文网络中的邻居
        
        Args:
            top_k: 每篇普通论文连接的核心论文数量
            use_embeddings: 是否使用向量嵌入
        
        Returns:
            候选对列表
        """
        logger.info(f"层2: 生成普通论文到核心论文的候选对 (top_k={top_k})")
        
        pairs = []
        
        if use_embeddings and HAS_SENTENCE_TRANSFORMERS:
            self._ensure_embeddings()
        
        for paper_id in self.regular_papers:
            # 方法1: 基于内容相似度（RAG）
            similar_cores = self._find_similar_cores_by_embedding(paper_id, top_k * 2)
            
            # 方法2: 基于引用结构
            structural_cores = self._find_cores_by_structure(paper_id, top_k)
            
            # 合并并选择Top-K
            combined = {}
            
            # 内容相似度得分
            for core_id, sim_score in similar_cores:
                combined[core_id] = combined.get(core_id, 0) + sim_score * 0.6
            
            # 结构邻近度得分
            for core_id in structural_cores:
                combined[core_id] = combined.get(core_id, 0) + 0.4
            
            # 按综合分数排序，取Top-K
            sorted_cores = sorted(combined.items(), key=lambda x: x[1], reverse=True)
            selected_cores = [core_id for core_id, _ in sorted_cores[:top_k]]
            
            # 生成候选对
            for core_id in selected_cores:
                pairs.append((paper_id, core_id))
        
        logger.info(f"  生成 {len(pairs)} 个普通-核心候选对")
        return pairs
    
    def _find_similar_cores_by_embedding(
        self,
        paper_id: str,
        top_k: int
    ) -> List[Tuple[str, float]]:
        """
        使用向量嵌入找到最相似的核心论文
        
        Returns:
            [(core_id, similarity_score), ...]
        """
        if not self.embeddings or paper_id not in self.embeddings:
            return self._find_similar_cores_by_keywords(paper_id, top_k)
        
        paper_emb = self.embeddings[paper_id]
        similarities = []
        
        for core_id in self.core_papers:
            if core_id in self.embeddings:
                core_emb = self.embeddings[core_id]
                # 余弦相似度
                sim = float(np.dot(paper_emb, core_emb) / (
                    np.linalg.norm(paper_emb) * np.linalg.norm(core_emb) + 1e-8
                ))
                similarities.append((core_id, sim))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def _find_similar_cores_by_keywords(
        self,
        paper_id: str,
        top_k: int
    ) -> List[Tuple[str, float]]:
        """
        使用关键词匹配找到相似的核心论文（回退方案）
        """
        paper = self.papers_index.get(paper_id, {})
        paper_text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
        paper_words = set(paper_text.split())
        
        similarities = []
        
        for core_id in self.core_papers:
            core = self.papers_index.get(core_id, {})
            core_text = f"{core.get('title', '')} {core.get('abstract', '')}".lower()
            core_words = set(core_text.split())
            
            # Jaccard相似度
            intersection = len(paper_words & core_words)
            union = len(paper_words | core_words)
            similarity = intersection / union if union > 0 else 0
            
            similarities.append((core_id, similarity))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def _find_cores_by_structure(
        self,
        paper_id: str,
        top_k: int
    ) -> List[str]:
        """
        基于引用结构找到相关的核心论文
        
        考虑：
        - 该论文引用的核心论文
        - 引用该论文的核心论文
        - 共同引用/被引的核心论文
        """
        related_cores = set()
        
        # 该论文引用的核心论文
        if paper_id in self.reference_map:
            for ref in self.reference_map[paper_id]:
                if ref in self.core_papers:
                    related_cores.add(ref)
        
        # 引用该论文的核心论文
        if paper_id in self.cited_by_map:
            for citer in self.cited_by_map[paper_id]:
                if citer in self.core_papers:
                    related_cores.add(citer)
        
        # 如果不够，找共同引用的核心论文
        if len(related_cores) < top_k:
            paper_refs = self.reference_map.get(paper_id, set())
            for core_id in self.core_papers:
                if core_id in related_cores:
                    continue
                core_refs = self.reference_map.get(core_id, set())
                # 共同引用数
                common = len(paper_refs & core_refs)
                if common >= 2:  # 至少2个共同引用
                    related_cores.add(core_id)
                if len(related_cores) >= top_k:
                    break
        
        return list(related_cores)[:top_k]
    
    def generate_bibliographic_coupling_pairs(
        self,
        min_coupling_strength: int = 3,
        max_pairs: int = 1000
    ) -> List[Tuple[str, str]]:
        """
        层3：基于文献耦合的补充候选对
        
        如果两篇论文引用了很多相同的参考文献，它们很可能相关
        
        Args:
            min_coupling_strength: 最小共同引用数
            max_pairs: 最大返回对数
        
        Returns:
            候选对列表
        """
        logger.info(f"层3: 生成文献耦合候选对 (阈值={min_coupling_strength})")
        
        coupling_pairs = []
        all_papers = list(self.papers_index.keys())
        
        # 只在非核心论文之间和非核心到核心之间查找
        # 核心-核心已经在层1处理
        
        for i, paper_a in enumerate(all_papers):
            refs_a = self.reference_map.get(paper_a, set())
            if len(refs_a) < min_coupling_strength:
                continue
            
            for paper_b in all_papers[i+1:]:
                # 跳过已经处理过的核心-核心对
                if paper_a in self.core_papers and paper_b in self.core_papers:
                    continue
                
                refs_b = self.reference_map.get(paper_b, set())
                if len(refs_b) < min_coupling_strength:
                    continue
                
                # 共同引用数
                common_refs = refs_a & refs_b
                if len(common_refs) >= min_coupling_strength:
                    coupling_pairs.append((paper_a, paper_b))
                
                if len(coupling_pairs) >= max_pairs:
                    break
            
            if len(coupling_pairs) >= max_pairs:
                break
        
        logger.info(f"  生成 {len(coupling_pairs)} 个文献耦合候选对")
        return coupling_pairs
    
    def generate_cocitation_pairs(
        self,
        min_cocitation_strength: int = 3,
        max_pairs: int = 1000
    ) -> List[Tuple[str, str]]:
        """
        层3补充：基于同被引的候选对
        
        如果两篇论文经常一起被引用，它们很可能存在某种关系
        
        Args:
            min_cocitation_strength: 最小同被引强度
            max_pairs: 最大返回对数
        
        Returns:
            候选对列表
        """
        logger.info(f"层3: 生成同被引候选对 (阈值={min_cocitation_strength})")
        
        cocitation_pairs = []
        papers_with_citers = [
            p for p in self.papers_index.keys()
            if len(self.cited_by_map.get(p, set())) >= min_cocitation_strength
        ]
        
        for i, paper_a in enumerate(papers_with_citers):
            citers_a = self.cited_by_map.get(paper_a, set())
            
            for paper_b in papers_with_citers[i+1:]:
                # 跳过核心-核心对
                if paper_a in self.core_papers and paper_b in self.core_papers:
                    continue
                
                citers_b = self.cited_by_map.get(paper_b, set())
                
                # 共同施引论文数
                common_citers = citers_a & citers_b
                if len(common_citers) >= min_cocitation_strength:
                    cocitation_pairs.append((paper_a, paper_b))
                
                if len(cocitation_pairs) >= max_pairs:
                    break
            
            if len(cocitation_pairs) >= max_pairs:
                break
        
        logger.info(f"  生成 {len(cocitation_pairs)} 个同被引候选对")
        return cocitation_pairs
    
    def apply_pruning_rules(
        self,
        candidate_pairs: List[Tuple[str, str]],
        max_year_diff: int = 15,
        require_same_domain: bool = False
    ) -> List[Tuple[str, str]]:
        """
        应用剪枝规则过滤候选对
        
        Args:
            candidate_pairs: 候选对列表
            max_year_diff: 最大年份差异
            require_same_domain: 是否要求相同研究领域
        
        Returns:
            剪枝后的候选对列表
        """
        logger.info(f"应用剪枝规则: {len(candidate_pairs)} 对")
        
        pruned_pairs = []
        
        for paper_a, paper_b in candidate_pairs:
            # 获取论文数据
            data_a = self.papers_index.get(paper_a, {})
            data_b = self.papers_index.get(paper_b, {})
            
            # 规则1: 时间剪枝
            year_a = data_a.get('year', 2024)
            year_b = data_b.get('year', 2024)
            
            if abs(year_a - year_b) > max_year_diff:
                continue
            
            # 规则2: 领域剪枝（如果启用）
            if require_same_domain:
                # 从属性中获取研究领域
                attrs_a = data_a.get('attributes', {})
                attrs_b = data_b.get('attributes', {})
                domains_a = set(attrs_a.get('research_domains', []))
                domains_b = set(attrs_b.get('research_domains', []))
                
                if domains_a and domains_b and not (domains_a & domains_b):
                    continue
            
            pruned_pairs.append((paper_a, paper_b))
        
        pruned_count = len(candidate_pairs) - len(pruned_pairs)
        logger.info(f"  剪枝移除 {pruned_count} 对，保留 {len(pruned_pairs)} 对")
        
        return pruned_pairs
    
    def generate_all_candidates(
        self,
        core_core_enabled: bool = True,
        regular_to_core_k: int = 5,
        bibliographic_coupling_min: int = 3,
        cocitation_min: int = 3,
        apply_pruning: bool = True
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        生成所有层级的候选对
        
        Args:
            core_core_enabled: 是否生成核心-核心对
            regular_to_core_k: 每篇普通论文连接的核心论文数
            bibliographic_coupling_min: 文献耦合最小阈值
            cocitation_min: 同被引最小阈值
            apply_pruning: 是否应用剪枝规则
        
        Returns:
            按层级分类的候选对字典
        """
        logger.info("=" * 60)
        logger.info("开始智能候选对生成")
        logger.info("=" * 60)
        
        all_candidates = {
            'layer1_core_core': [],
            'layer2_regular_to_core': [],
            'layer3_bibliographic_coupling': [],
            'layer3_cocitation': [],
            'total_count': 0,
            'unique_pairs': set()
        }
        
        # 层1: 核心-核心
        if core_core_enabled:
            core_core_pairs = self.generate_core_core_pairs()
            all_candidates['layer1_core_core'] = core_core_pairs
            for pair in core_core_pairs:
                all_candidates['unique_pairs'].add(tuple(sorted(pair)))
        
        # 层2: 普通-核心
        regular_to_core_pairs = self.generate_regular_to_core_pairs(
            top_k=regular_to_core_k
        )
        all_candidates['layer2_regular_to_core'] = regular_to_core_pairs
        for pair in regular_to_core_pairs:
            all_candidates['unique_pairs'].add(tuple(sorted(pair)))
        
        # 层3: 文献耦合
        if bibliographic_coupling_min > 0:
            bib_coupling_pairs = self.generate_bibliographic_coupling_pairs(
                min_coupling_strength=bibliographic_coupling_min
            )
            # 去除已存在的对
            new_bib_pairs = [
                p for p in bib_coupling_pairs
                if tuple(sorted(p)) not in all_candidates['unique_pairs']
            ]
            all_candidates['layer3_bibliographic_coupling'] = new_bib_pairs
            for pair in new_bib_pairs:
                all_candidates['unique_pairs'].add(tuple(sorted(pair)))
        
        # 层3: 同被引
        if cocitation_min > 0:
            cocitation_pairs = self.generate_cocitation_pairs(
                min_cocitation_strength=cocitation_min
            )
            # 去除已存在的对
            new_cocitation_pairs = [
                p for p in cocitation_pairs
                if tuple(sorted(p)) not in all_candidates['unique_pairs']
            ]
            all_candidates['layer3_cocitation'] = new_cocitation_pairs
            for pair in new_cocitation_pairs:
                all_candidates['unique_pairs'].add(tuple(sorted(pair)))
        
        # 应用剪枝
        if apply_pruning:
            all_pairs = list(all_candidates['unique_pairs'])
            pruned_pairs = self.apply_pruning_rules(all_pairs)
            all_candidates['unique_pairs'] = set(tuple(sorted(p)) for p in pruned_pairs)
        
        all_candidates['total_count'] = len(all_candidates['unique_pairs'])
        
        logger.info("=" * 60)
        logger.info(f"候选对生成完成:")
        logger.info(f"  - 层1 核心-核心: {len(all_candidates['layer1_core_core'])}")
        logger.info(f"  - 层2 普通-核心: {len(all_candidates['layer2_regular_to_core'])}")
        logger.info(f"  - 层3 文献耦合: {len(all_candidates['layer3_bibliographic_coupling'])}")
        logger.info(f"  - 层3 同被引: {len(all_candidates['layer3_cocitation'])}")
        logger.info(f"  - 总计唯一候选对: {all_candidates['total_count']}")
        logger.info("=" * 60)
        
        return all_candidates