"""
增量关系发现器 - IncrementalRelationDiscoverer (RAG增强版)

解决问题：新增论文时避免O(N²)的全量比对

核心策略：
1. 只比对新论文与"相关"旧论文，而非全部
2. 使用RAG向量检索快速找到语义相似的论文
3. 结合多种信号（引用、实体、语义）综合筛选

复杂度优化：
- 原始：O(N²) - 每篇新论文与所有旧论文比对
- 优化后：O(N * K) - 每篇新论文只与K篇候选论文比对（K << N）
- 节省比例：当N=2000, K=20时，节省99%的LLM调用
"""

import asyncio
from typing import List, Dict, Any, Set, Tuple, Optional
from collections import defaultdict
from pathlib import Path
from loguru import logger

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False

try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


class RAGPaperRetriever:
    """RAG论文检索器 - 使用向量数据库进行语义检索"""
    
    def __init__(self, persist_dir: str = None, model_name: str = "all-MiniLM-L6-v2"):
        self.persist_dir = persist_dir
        self.paper_data: Dict[str, Dict] = {}
        self.embeddings_cache: Dict[str, Any] = {}
        
        # 初始化嵌入模型
        self.embedder = None
        if HAS_EMBEDDINGS:
            try:
                self.embedder = SentenceTransformer(model_name)
                logger.info(f"加载嵌入模型: {model_name}")
            except Exception as e:
                logger.warning(f"嵌入模型加载失败: {e}")
        
        # 初始化Chroma
        self.collection = None
        if HAS_CHROMA and persist_dir:
            try:
                Path(persist_dir).mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=persist_dir)
                self.collection = client.get_or_create_collection("papers", metadata={"hnsw:space": "cosine"})
                logger.info(f"Chroma初始化: {persist_dir}")
            except Exception as e:
                logger.warning(f"Chroma初始化失败: {e}")
    
    def _build_text(self, paper: Dict) -> str:
        """构建增强文本"""
        parts = [paper.get('title', ''), paper.get('abstract', '')[:800]]
        attrs = paper.get('attributes', {})
        sem = paper.get('semantic_entities', {})
        
        if isinstance(attrs.get('method_info'), dict):
            parts.append(f"Method: {attrs['method_info'].get('method_name', '')}")
        for t in sem.get('task', [])[:2]:
            parts.append(f"Task: {t}")
        for m in sem.get('method', [])[:2]:
            parts.append(f"Technique: {m}")
        
        return "\n".join(filter(None, parts))
    
    def add_paper(self, paper: Dict) -> bool:
        """添加论文到索引"""
        paper_id = paper.get('paper_id') or paper.get('id')
        if not paper_id or not self.embedder:
            return False
        
        text = self._build_text(paper)
        self.paper_data[paper_id] = paper
        
        try:
            embedding = self.embedder.encode(text).tolist()
            
            if self.collection:
                self.collection.upsert(
                    ids=[paper_id],
                    embeddings=[embedding],
                    documents=[text[:1000]],
                    metadatas=[{"title": paper.get('title', '')[:200], "year": str(paper.get('year', 2024))}]
                )
            else:
                self.embeddings_cache[paper_id] = np.array(embedding)
            return True
        except Exception as e:
            logger.debug(f"添加论文失败: {e}")
            return False
    
    def add_papers_batch(self, papers: List[Dict]) -> int:
        """批量添加"""
        count = 0
        for p in papers:
            if self.add_paper(p):
                count += 1
        logger.info(f"RAG索引: {count}/{len(papers)} 篇论文")
        return count
    
    def retrieve_similar(self, query_paper: Dict, top_k: int = 20, min_score: float = 0.5) -> List[Tuple[str, float]]:
        """检索相似论文"""
        if not self.embedder:
            return []
        
        query_id = query_paper.get('paper_id') or query_paper.get('id')
        text = self._build_text(query_paper)
        
        try:
            query_emb = self.embedder.encode(text)
            
            if self.collection:
                results = self.collection.query(query_embeddings=[query_emb.tolist()], n_results=top_k + 1, include=["distances"])
                if results and results['ids']:
                    return [(pid, 1 - dist) for pid, dist in zip(results['ids'][0], results['distances'][0]) 
                            if pid != query_id and (1 - dist) >= min_score][:top_k]
            elif self.embeddings_cache:
                sims = []
                for pid, emb in self.embeddings_cache.items():
                    if pid != query_id:
                        sim = float(np.dot(query_emb, emb) / (np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8))
                        if sim >= min_score:
                            sims.append((pid, sim))
                return sorted(sims, key=lambda x: x[1], reverse=True)[:top_k]
        except Exception as e:
            logger.debug(f"检索失败: {e}")
        return []
    
    def get_paper(self, paper_id: str) -> Optional[Dict]:
        return self.paper_data.get(paper_id)


class IncrementalRelationDiscoverer:
    """
    增量关系发现器 (RAG增强版)
    
    候选筛选策略：
    1. 引用关系：新论文引用的旧论文（权重1.0）
    2. RAG语义：向量相似度Top-K（权重0.9）
    3. 共享实体：共享Method/Task/Dataset（权重0.7）
    4. 时间邻近：近3年高引论文（权重0.5）
    """
    
    def __init__(self, relation_extractor=None, max_candidates: int = 20, persist_dir: str = None):
        self.relation_extractor = relation_extractor
        self.max_candidates = max_candidates
        self.rag = RAGPaperRetriever(persist_dir)
        
        # 索引
        self.entity_index: Dict[str, Set[str]] = defaultdict(set)
        self.paper_entities: Dict[str, Set[str]] = defaultdict(set)
        self.paper_years: Dict[str, int] = {}
        self.paper_citations: Dict[str, int] = {}
        self.reference_map: Dict[str, Set[str]] = defaultdict(set)
        
        self.stats = {"indexed": 0, "relations": 0, "saved_calls": 0}
    
    def index_papers(self, papers: List[Dict]):
        """索引现有论文"""
        logger.info(f"索引 {len(papers)} 篇论文...")
        
        for p in papers:
            pid = p.get('paper_id') or p.get('id')
            if not pid:
                continue
            
            self.paper_years[pid] = p.get('year', 2024)
            self.paper_citations[pid] = p.get('citations', 0)
            self.reference_map[pid] = set(p.get('referenced_works', []))
            self._index_entities(pid, p)
        
        self.rag.add_papers_batch(papers)
        self.stats["indexed"] = len(self.paper_years)
        logger.info(f"索引完成: {self.stats['indexed']} 篇, {len(self.entity_index)} 实体")
    
    def _index_entities(self, pid: str, paper: Dict):
        """索引实体"""
        entities = set()
        attrs = paper.get('attributes', {})
        sem = paper.get('semantic_entities', {})
        
        if isinstance(attrs.get('method_info'), dict) and attrs['method_info'].get('method_name'):
            e = f"method:{attrs['method_info']['method_name'].lower()}"
            entities.add(e)
            self.entity_index[e].add(pid)
        
        for d in attrs.get('research_domains', []):
            e = f"domain:{d.lower()}"
            entities.add(e)
            self.entity_index[e].add(pid)
        
        for m in sem.get('method', []):
            e = f"method:{m.lower()}"
            entities.add(e)
            self.entity_index[e].add(pid)
        
        for t in sem.get('task', []):
            e = f"task:{t.lower()}"
            entities.add(e)
            self.entity_index[e].add(pid)
        
        for ds in sem.get('dataset', []):
            e = f"dataset:{ds.lower()}"
            entities.add(e)
            self.entity_index[e].add(pid)
        
        self.paper_entities[pid] = entities
    
    def add_paper(self, paper: Dict):
        """增量添加论文"""
        pid = paper.get('paper_id') or paper.get('id')
        if not pid:
            return
        
        self.paper_years[pid] = paper.get('year', 2024)
        self.paper_citations[pid] = paper.get('citations', 0)
        self.reference_map[pid] = set(paper.get('referenced_works', []))
        self._index_entities(pid, paper)
        self.rag.add_paper(paper)
        self.stats["indexed"] += 1
    
    def find_candidates(self, new_paper: Dict, existing_ids: Set[str] = None) -> List[Tuple[str, float, str]]:
        """
        为新论文找候选比对论文
        
        Returns: [(paper_id, score, source), ...]
        """
        new_id = new_paper.get('paper_id') or new_paper.get('id')
        if existing_ids is None:
            existing_ids = set(self.paper_years.keys())
        existing_ids = existing_ids - {new_id}
        
        scores: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # 1. 引用关系 (权重1.0)
        for ref in new_paper.get('referenced_works', []):
            if ref in existing_ids:
                scores[ref]["citation"] = 1.0
        
        # 2. RAG语义检索 (权重0.9)
        for pid, sim in self.rag.retrieve_similar(new_paper, self.max_candidates):
            if pid in existing_ids:
                scores[pid]["rag"] = sim * 0.9
        
        # 3. 共享实体 (权重0.7)
        new_entities = set()
        attrs = new_paper.get('attributes', {})
        sem = new_paper.get('semantic_entities', {})
        
        if isinstance(attrs.get('method_info'), dict):
            new_entities.add(f"method:{attrs['method_info'].get('method_name', '').lower()}")
        for d in attrs.get('research_domains', []):
            new_entities.add(f"domain:{d.lower()}")
        for m in sem.get('method', []):
            new_entities.add(f"method:{m.lower()}")
        for t in sem.get('task', []):
            new_entities.add(f"task:{t.lower()}")
        
        shared_counts: Dict[str, int] = defaultdict(int)
        for e in new_entities:
            for pid in self.entity_index.get(e, set()):
                if pid in existing_ids:
                    shared_counts[pid] += 1
        
        max_shared = max(shared_counts.values()) if shared_counts else 1
        for pid, cnt in shared_counts.items():
            scores[pid]["entity"] = (cnt / max_shared) * 0.7
        
        # 4. 时间邻近高引 (权重0.5)
        new_year = new_paper.get('year', 2024)
        for pid in existing_ids:
            if pid in scores:
                continue
            year = self.paper_years.get(pid, 2024)
            cites = self.paper_citations.get(pid, 0)
            if abs(new_year - year) <= 3 and cites > 50:
                scores[pid]["temporal"] = min(1.0, cites / 500) * 0.5
        
        # 融合分数
        results = []
        for pid, s in scores.items():
            total = sum(s.values())
            primary = max(s.items(), key=lambda x: x[1])[0] if s else "unknown"
            results.append((pid, total, primary))
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        # 统计
        saved = len(existing_ids) - min(len(results), self.max_candidates)
        self.stats["saved_calls"] += saved
        
        logger.info(f"新论文 {new_id}: {len(results)} 候选 (从 {len(existing_ids)} 篇中筛选, 节省 {saved} 次LLM调用)")
        
        return results[:self.max_candidates]
    
    async def discover_relations(
        self,
        new_papers: List[Dict],
        existing_papers: List[Dict] = None,
        max_concurrent: int = 20,
        progress_callback=None
    ) -> List[Dict]:
        """
        为新论文发现关系（高并发版本，支持实时进度）
        
        Args:
            new_papers: 新论文列表
            existing_papers: 现有论文列表（用于索引）
            max_concurrent: 最大并发数，默认20
            progress_callback: 进度回调函数 callback(completed, total, found_relations)
        
        Returns:
            发现的关系列表
        """
        if not self.relation_extractor:
            logger.error("未配置关系抽取器")
            return []
        
        if existing_papers:
            self.index_papers(existing_papers)
        
        existing_ids = set(self.paper_years.keys())
        all_relations = []
        
        original = len(new_papers) * len(existing_ids)
        logger.info(f"开始关系发现: {len(new_papers)} 新论文, 原始需 {original} 次比对, 并发数={max_concurrent}")
        
        # 全局信号量控制总并发数
        sem = asyncio.Semaphore(max_concurrent)
        
        # 进度追踪
        completed_count = 0
        found_count = 0
        total_tasks = 0
        progress_lock = asyncio.Lock()
        
        async def extract_single_relation(paper: Dict, cand_id: str, score: float, source: str):
            """提取单个论文对的所有关系（支持多关系）"""
            nonlocal completed_count, found_count
            
            async with sem:
                pid = paper.get('paper_id') or paper.get('id')
                cand_paper = self.rag.get_paper(cand_id)
                results = []
                
                if cand_paper:
                    try:
                        # 确保论文数据包含 paper_id 字段（兼容 id 字段）
                        paper_a = dict(paper)
                        paper_b = dict(cand_paper)
                        
                        if 'paper_id' not in paper_a and 'id' in paper_a:
                            paper_a['paper_id'] = paper_a['id']
                        if 'paper_id' not in paper_b and 'id' in paper_b:
                            paper_b['paper_id'] = paper_b['id']
                        
                        # 优先使用多关系提取方法
                        if hasattr(self.relation_extractor, 'extract_all_relations_between_papers'):
                            edges = await self.relation_extractor.extract_all_relations_between_papers(paper_a, paper_b)
                        else:
                            # 兼容旧版本
                            edge = await self.relation_extractor.extract_relation_between_papers(paper_a, paper_b)
                            edges = [edge] if edge else []
                        
                        for edge in edges:
                            if edge:
                                results.append({
                                    "source": edge.source if hasattr(edge, 'source') else pid,
                                    "target": edge.target if hasattr(edge, 'target') else cand_id,
                                    "type": edge.relation_type.value if hasattr(edge.relation_type, 'value') else str(edge.relation_type),
                                    "confidence": edge.llm_confidence,
                                    "evidence": edge.evidence,
                                    "candidate_source": source,
                                    "candidate_score": score
                                })
                    except Exception as e:
                        logger.debug(f"关系抽取失败 {pid}->{cand_id}: {e}")
                
                # 更新进度
                async with progress_lock:
                    completed_count += 1
                    if results:
                        found_count += len(results)
                    
                    # 每完成5%或每20个任务更新一次进度
                    if progress_callback and (completed_count % max(1, total_tasks // 20) == 0 or completed_count == total_tasks):
                        try:
                            progress_callback(completed_count, total_tasks, found_count)
                        except Exception as e:
                            logger.debug(f"进度回调失败: {e}")
                
                return results
        
        # 收集所有需要提取的论文对
        all_task_params = []
        for paper in new_papers:
            candidates = self.find_candidates(paper, existing_ids)
            for cand_id, score, source in candidates:
                all_task_params.append((paper, cand_id, score, source))
        
        total_tasks = len(all_task_params)
        logger.info(f"总共 {total_tasks} 个关系提取任务，{max_concurrent} 线程并发执行...")
        
        # 初始进度回调
        if progress_callback:
            try:
                progress_callback(0, total_tasks, 0)
            except:
                pass
        
        # 创建所有任务
        all_tasks = [extract_single_relation(p, c, s, src) for p, c, s, src in all_task_params]
        
        # 并发执行所有任务
        results = await asyncio.gather(*all_tasks)
        
        # 展平结果列表（每个任务可能返回多个关系）
        all_relations = []
        for result_list in results:
            if result_list:
                all_relations.extend(result_list)
        
        # 更新索引
        for paper in new_papers:
            self.add_paper(paper)
        
        logger.info(f"关系发现完成: {len(all_relations)} 条关系 (从 {total_tasks} 次比对中)")
        
        self.stats["relations"] += len(all_relations)
        return all_relations
    
    def get_stats(self) -> Dict:
        return {**self.stats, "rag_papers": len(self.rag.paper_data), "entities": len(self.entity_index)}


# 便捷函数
def create_discoverer(relation_extractor=None, max_candidates: int = 20, persist_dir: str = None):
    """创建增量关系发现器"""
    return IncrementalRelationDiscoverer(relation_extractor, max_candidates, persist_dir)


if __name__ == "__main__":
    # 测试
    papers = [{"paper_id": f"p{i}", "title": f"Paper {i}", "abstract": f"About ML {i}", "year": 2020+i%5, "citations": i*10,
               "referenced_works": [f"p{j}" for j in range(max(0,i-3), i)],
               "semantic_entities": {"method": [f"m{i%3}"], "task": [f"t{i%4}"]}} for i in range(50)]
    
    new = [{"paper_id": "new1", "title": "New ML Paper", "abstract": "Novel approach", "year": 2024,
            "referenced_works": ["p10", "p20"], "semantic_entities": {"method": ["m1"], "task": ["t2"]}}]
    
    d = IncrementalRelationDiscoverer(max_candidates=10)
    d.index_papers(papers)
    
    for p in new:
        cands = d.find_candidates(p)
        print(f"\n{p['paper_id']} 候选:")
        for pid, score, src in cands[:5]:
            print(f"  {pid}: {score:.2f} ({src})")
    
    print(f"\n统计: {d.get_stats()}")