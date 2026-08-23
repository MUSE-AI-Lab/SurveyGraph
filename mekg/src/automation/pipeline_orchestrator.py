"""
MEKG Pipeline Orchestrator - 模块化知识图谱构建编排器

核心功能：
1. Topic管理：支持多Topic爬取和管理
2. 智能判断：自动判断是否需要爬取/增量更新
3. 模块化流水线：爬取→存储→PDF解析→属性提取→关系发现→社区发现
4. 社区命名：LLM自动为社区生成语义标签

使用方式：
    orchestrator = MEKGPipelineOrchestrator()
    
    # 方式1：直接输入Topic爬取
    await orchestrator.build_topic("Large Language Model Agents")
    
    # 方式2：批量爬取多个AI领域
    await orchestrator.build_topics(["LLM Agents", "RAG", "Multimodal AI"])
    
    # 方式3：智能判断后爬取（用于写综述）
    subgraph = await orchestrator.get_or_build_subgraph("LLM Tool Use", for_survey=True)
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
import json

from loguru import logger


class BuildAction(Enum):
    """构建动作类型"""
    SKIP = "skip"           # 数据充足，直接使用
    INCREMENTAL = "incremental"  # 增量更新
    FULL_BUILD = "full_build"    # 从头构建


@dataclass
class TopicStatus:
    """Topic状态"""
    name: str
    exists: bool = False
    paper_count: int = 0
    recent_paper_count: int = 0  # 近1年论文数
    last_updated: Optional[datetime] = None
    communities: List[int] = field(default_factory=list)
    recommended_action: BuildAction = BuildAction.FULL_BUILD
    reason: str = ""


@dataclass
class PipelineConfig:
    """流水线配置"""
    # 爬取配置
    target_paper_count: int = 500
    year_start: int = 2018
    year_end: int = 2024
    use_survey_strategy: bool = True
    
    # PDF处理配置
    enable_pdf_download: bool = True
    max_pdf_concurrent: int = 10
    
    # 属性提取配置
    enable_deep_extraction: bool = True  # 深层属性（创新点、不足等）
    max_llm_concurrent: int = 20  # 提高到20线程并发
    
    # 关系发现配置
    max_candidates_per_paper: int = 20
    enable_rag_retrieval: bool = True
    
    # 社区发现配置
    enable_community_detection: bool = True
    enable_community_naming: bool = True
    min_community_size: int = 5
    
    # 智能判断阈值
    sufficient_paper_count: int = 100  # 认为数据充足的论文数
    recent_paper_ratio: float = 0.3    # 近期论文占比阈值
    recent_months: int = 12            # "近期"的定义（月）


class MEKGPipelineOrchestrator:
    """
    MEKG流水线编排器
    
    负责协调各个模块完成知识图谱构建：
    1. PaperPoolCollector - 论文爬取
    2. MemgraphGraphDB - 图数据库存储
    3. PDFProcessor - PDF下载和解析
    4. SemanticEntityExtractor - 语义实体抽取
    5. PaperAttributeExtractor - 深层属性提取
    6. IncrementalRelationDiscoverer - 关系发现
    7. CommunityLabeler - 社区命名
    """
    
    def __init__(self, config: PipelineConfig = None, db=None):
        self.config = config or PipelineConfig()
        
        # 延迟导入避免循环依赖
        self._db = db
        self._collector = None
        self._pdf_processor = None
        self._entity_extractor = None
        self._attr_extractor = None
        self._relation_discoverer = None
        self._community_labeler = None
        self._rag_retriever = None
        self._citation_analyzer = None
        self._entity_disambiguator = None
        
        # 状态追踪
        self.current_topic: Optional[str] = None
        self.progress: Dict[str, Any] = {}
        self.logs: List[str] = []
        
        # 回调函数
        self._progress_callback = None
        self._log_callback = None
    
    def set_callbacks(self, progress_callback=None, log_callback=None):
        """设置回调函数"""
        self._progress_callback = progress_callback
        self._log_callback = log_callback
    
    def _log(self, message: str, level: str = "info"):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        
        if self._log_callback:
            self._log_callback(log_entry)
    
    def _update_progress(self, stage: str, progress: float, detail: str = ""):
        """更新进度"""
        self.progress = {
            "topic": self.current_topic,
            "stage": stage,
            "progress": progress,
            "detail": detail,
            "timestamp": datetime.now().isoformat()
        }
        
        if self._progress_callback:
            self._progress_callback(self.progress)
    
    @property
    def db(self):
        """获取数据库连接"""
        if self._db is None:
            from src.modules.mekg.storage.memgraph_graph_db import MemgraphGraphDB
            self._db = MemgraphGraphDB()
        return self._db
    
    @property
    def collector(self):
        """获取论文收集器"""
        if self._collector is None:
            from src.modules.mekg.paper_pool_collector import PaperPoolCollector
            self._collector = PaperPoolCollector()
        return self._collector
    
    @property
    def entity_extractor(self):
        """获取语义实体抽取器"""
        if self._entity_extractor is None:
            from src.modules.mekg.semantic_entity_extractor import SemanticEntityExtractor
            self._entity_extractor = SemanticEntityExtractor(max_workers=self.config.max_llm_concurrent)
        return self._entity_extractor
    
    @property
    def relation_discoverer(self):
        """获取关系发现器"""
        if self._relation_discoverer is None:
            from src.modules.mekg.incremental_relation_discoverer import IncrementalRelationDiscoverer
            from src.modules.mekg.attribute_based_relation_extractor import AttributeBasedRelationExtractor
            
            self._relation_discoverer = IncrementalRelationDiscoverer(
                relation_extractor=AttributeBasedRelationExtractor(),
                max_candidates=self.config.max_candidates_per_paper
            )
        return self._relation_discoverer
    
    @property
    def community_labeler(self):
        """获取社区命名器"""
        if self._community_labeler is None:
            from src.modules.mekg.community_labeler import CommunityLabeler
            self._community_labeler = CommunityLabeler()
        return self._community_labeler

    @property
    def citation_analyzer(self):
        """获取引用上下文分析器"""
        if self._citation_analyzer is None:
            from src.modules.mekg.citation_context_analyzer import CitationContextAnalyzer
            self._citation_analyzer = CitationContextAnalyzer()
        return self._citation_analyzer

    @property
    def entity_disambiguator(self):
        """获取实体消歧器"""
        if self._entity_disambiguator is None:
            from src.modules.mekg.entity_disambiguator import EntityDisambiguator
            self._entity_disambiguator = EntityDisambiguator()
        return self._entity_disambiguator
    
    # ==================== 核心API ====================
    
    async def analyze_topic(self, topic: str) -> TopicStatus:
        """
        分析Topic状态，智能判断需要采取的动作
        
        判断逻辑：
        1. 如果Topic不存在 → FULL_BUILD
        2. 如果论文数量不足 → INCREMENTAL 或 FULL_BUILD
        3. 如果近期论文占比不足 → INCREMENTAL
        4. 否则 → SKIP
        """
        self._log(f"📊 分析Topic状态: {topic}")
        
        status = TopicStatus(name=topic)
        
        # 1. 检查Topic是否存在
        db_status = self.db.get_topic_status(topic)
        status.exists = db_status.get('exists', False)
        status.paper_count = db_status.get('paper_count', 0)
        
        if db_status.get('last_updated'):
            try:
                status.last_updated = datetime.fromisoformat(db_status['last_updated'])
            except:
                pass
        
        if not status.exists:
            status.recommended_action = BuildAction.FULL_BUILD
            status.reason = "Topic不存在，需要从头构建"
            self._log(f"  → Topic不存在，推荐: FULL_BUILD")
            return status
        
        # 2. 检查论文数量
        if status.paper_count < self.config.sufficient_paper_count:
            if status.paper_count < 20:
                status.recommended_action = BuildAction.FULL_BUILD
                status.reason = f"论文数量过少({status.paper_count})，需要重新构建"
            else:
                status.recommended_action = BuildAction.INCREMENTAL
                status.reason = f"论文数量不足({status.paper_count}/{self.config.sufficient_paper_count})，需要增量更新"
            self._log(f"  → 论文数量: {status.paper_count}, 推荐: {status.recommended_action.value}")
            return status
        
        # 3. 检查近期论文占比
        recent_count = await self._count_recent_papers(topic)
        status.recent_paper_count = recent_count
        recent_ratio = recent_count / status.paper_count if status.paper_count > 0 else 0
        
        if recent_ratio < self.config.recent_paper_ratio:
            status.recommended_action = BuildAction.INCREMENTAL
            status.reason = f"近期论文占比不足({recent_ratio:.1%})，需要增量更新"
            self._log(f"  → 近期论文占比: {recent_ratio:.1%}, 推荐: INCREMENTAL")
            return status
        
        # 4. 数据充足
        status.recommended_action = BuildAction.SKIP
        status.reason = f"数据充足({status.paper_count}篇，近期{recent_count}篇)"
        self._log(f"  → 数据充足，推荐: SKIP")
        
        return status
    
    async def _count_recent_papers(self, topic: str) -> int:
        """统计近期论文数量"""
        cutoff_year = datetime.now().year - (self.config.recent_months // 12)
        
        try:
            results = self.db.execute_cypher(
                """
                MATCH (p:Paper)-[:BELONGS_TO]->(t:Topic {name: $topic})
                WHERE p.year >= $year
                RETURN count(p) AS cnt
                """,
                {"topic": topic, "year": cutoff_year}
            )
            return results[0]['cnt'] if results else 0
        except Exception as e:
            self._log(f"统计近期论文失败: {e}", "warning")
            return 0
    
    async def build_topic(
        self,
        topic: str,
        force_action: BuildAction = None
    ) -> Dict[str, Any]:
        """
        构建单个Topic的知识图谱
        
        Args:
            topic: Topic名称
            force_action: 强制执行的动作（None则自动判断）
        
        Returns:
            构建结果统计
        """
        self.current_topic = topic
        self._log(f"🚀 开始构建Topic: {topic}")
        
        result = {
            "topic": topic,
            "action": None,
            "papers_added": 0,
            "relations_discovered": 0,
            "communities_detected": 0,
            "duration_seconds": 0,
            "success": False
        }
        
        start_time = datetime.now()
        
        try:
            # 1. 分析状态，决定动作
            if force_action:
                action = force_action
                self._log(f"  强制执行: {action.value}")
            else:
                status = await self.analyze_topic(topic)
                action = status.recommended_action
            
            result["action"] = action.value
            
            if action == BuildAction.SKIP:
                self._log(f"✅ Topic数据充足，跳过构建")
                result["success"] = True
                return result
            
            # 2. 执行构建流水线
            if action == BuildAction.FULL_BUILD:
                papers = await self._stage_crawl(topic, incremental=False)
            else:  # INCREMENTAL
                papers = await self._stage_crawl(topic, incremental=True)
            
            result["papers_added"] = len(papers)
            
            if not papers:
                self._log("⚠️ 未爬取到新论文")
                result["success"] = True
                return result
            
            # 3. 存储到数据库
            await self._stage_store(topic, papers)
            
            # 4. PDF下载和解析（可选）
            if self.config.enable_pdf_download:
                papers = await self._stage_pdf_process(papers)
            
            # 5. 属性提取 (包含实体消歧)
            papers = await self._stage_extract_attributes(papers)
            
            # 6. 关系发现 (包含引用上下文分析)
            relations = await self._stage_discover_relations(papers)
            result["relations_discovered"] = len(relations)
            
            # 7. 社区发现和命名
            if self.config.enable_community_detection:
                communities = await self._stage_community_detection()
                result["communities_detected"] = len(communities)
            
            result["success"] = True
            
        except Exception as e:
            self._log(f"❌ 构建失败: {e}", "error")
            import traceback
            traceback.print_exc()
            result["error"] = str(e)
        
        result["duration_seconds"] = (datetime.now() - start_time).total_seconds()
        self._log(f"✅ Topic构建完成: {result}")
        
        return result
    
    async def build_topics(self, topics: List[str]) -> List[Dict[str, Any]]:
        """批量构建多个Topic"""
        results = []
        for i, topic in enumerate(topics):
            self._log(f"📦 处理Topic {i+1}/{len(topics)}: {topic}")
            result = await self.build_topic(topic)
            results.append(result)
        return results
    
    async def get_or_build_subgraph(
        self,
        topic: str,
        for_survey: bool = True,
        min_papers: int = None
    ) -> Dict[str, Any]:
        """
        获取或构建子图谱（用于写综述）
        
        智能判断流程：
        1. 分析Topic状态（是否存在，论文是否足够）
        2. 如果不存在或不足，自动触发构建（全量或增量）
        3. 返回构建后的子图谱数据
        """
        self._log(f"🔍 获取子图谱: {topic} (for_survey={for_survey})")
        
        min_papers = min_papers or self.config.sufficient_paper_count
        
        # 1. 分析现有数据
        status = await self.analyze_topic(topic)
        self._log(f"  当前状态: {status.reason}")
        
        # 2. 自动触发构建逻辑
        if status.recommended_action != BuildAction.SKIP:
            self._log(f"⚠️ 数据不足，自动触发构建: {status.recommended_action.value}")
            
            # 自动执行构建，无需用户干预
            build_result = await self.build_topic(topic)
            
            if not build_result.get("success"):
                self._log(f"❌ 自动构建失败: {build_result.get('error')}", "error")
                # 即使失败，也尝试返回现有数据
            
            # 重新分析状态
            status = await self.analyze_topic(topic)
        
        # 3. 提取子图谱
        subgraph = await self._extract_subgraph(topic)
        
        # 检查结果是否为空
        if not subgraph.get("papers"):
            self._log(f"⚠️ 警告: 子图谱为空，可能爬取失败或无相关论文", "warning")
        
        return {
            "topic": topic,
            "status": status.__dict__,
            "subgraph": subgraph
        }
    
    # ==================== 流水线阶段 ====================
    
    async def _stage_crawl(self, topic: str, incremental: bool = False) -> List[Dict]:
        """阶段1: 爬取论文"""
        self._update_progress("crawl", 0, "开始爬取论文...")
        self._log(f"📡 阶段1: 爬取论文 (incremental={incremental})")
        
        year_start = self.config.year_start
        if incremental:
            # 增量模式：只爬取近2年
            year_start = max(year_start, datetime.now().year - 2)
        
        target_count = self.config.target_paper_count
        if incremental:
            target_count = target_count // 2
        
        papers = await self.collector.collect_comprehensive_pool(
            keywords=[topic],
            target_count=target_count,
            year_start=year_start,
            year_end=self.config.year_end,
            use_survey_strategy=self.config.use_survey_strategy
        )
        
        if papers is None:
            papers = []
        
        self._update_progress("crawl", 100, f"爬取完成: {len(papers)}篇")
        self._log(f"  ✓ 爬取完成: {len(papers)}篇论文")
        
        return papers
    
    async def _stage_store(self, topic: str, papers: List[Dict]):
        """阶段2: 存储到数据库"""
        self._update_progress("store", 0, "存储论文到数据库...")
        self._log(f"💾 阶段2: 存储论文 ({len(papers)}篇)")
        
        # 确保Topic存在
        self.db.add_topic(topic)
        
        stored_count = 0
        for i, paper in enumerate(papers):
            paper_id = paper.get('paper_id') or paper.get('id')
            if not paper_id:
                continue
            
            # 添加论文
            if self.db.add_paper(paper):
                stored_count += 1
            
            # 链接到Topic
            self.db.link_paper_to_topic(paper_id, topic, 0.9)
            
            # 处理引用关系
            for ref_id in paper.get('referenced_works', []):
                self.db.add_citation(paper_id, ref_id)
            
            if (i + 1) % 50 == 0:
                self._update_progress("store", (i + 1) / len(papers) * 100, f"已存储 {i+1}/{len(papers)}")
        
        self._update_progress("store", 100, f"存储完成: {stored_count}篇")
        self._log(f"  ✓ 存储完成: {stored_count}篇")
    
    async def _stage_pdf_process(self, papers: List[Dict]) -> List[Dict]:
        """阶段3: PDF下载和解析"""
        self._update_progress("pdf", 0, "下载和解析PDF...")
        self._log(f"📄 阶段3: PDF处理 ({len(papers)}篇)")
        
        try:
            from src.modules.paper_acquisition.multi_source_pdf_downloader import MultiSourcePDFDownloader
            from src.modules.mekg.pdf_processor import PDFProcessor
            from pathlib import Path
            
            # 创建PDF目录
            pdf_dir = Path("data/pdfs")
            pdf_dir.mkdir(parents=True, exist_ok=True)
            
            # 下载PDF
            downloader = MultiSourcePDFDownloader(
                pdf_dir=pdf_dir,
                max_concurrent=self.config.max_pdf_concurrent
            )
            papers_with_pdf = await downloader.download_papers_until_target(
                papers,
                target_count=min(len(papers), 200)  # 限制下载数量
            )
            
            self._log(f"  ✓ PDF下载: {len(papers_with_pdf)}篇")
            
            # 解析PDF
            processor = PDFProcessor()
            for paper in papers_with_pdf:
                pdf_path = paper.get('pdf_path')
                if pdf_path:
                    text = processor.extract_text_from_pdf(pdf_path)
                    if text:
                        paper['full_text'] = text
            
            self._update_progress("pdf", 100, f"PDF处理完成")
            return papers_with_pdf
            
        except Exception as e:
            self._log(f"  ⚠️ PDF处理失败: {e}", "warning")
            return papers
    
    async def _stage_extract_attributes(self, papers: List[Dict]) -> List[Dict]:
        """阶段4: 属性提取 (含实体消歧)"""
        self._update_progress("extract", 0, "提取论文属性...")
        self._log(f"🔬 阶段4: 属性提取 ({len(papers)}篇)")
        
        # 1. 语义实体抽取
        entities_list = await self.entity_extractor.batch_extract(papers, show_progress=True)
        
        # 2. 收集所有实体进行消歧
        all_entities = []
        for entities in entities_list:
            all_entities.extend([t.value for t in entities.tasks])
            all_entities.extend([m.value for m in entities.methods])
            all_entities.extend([m.value for m in entities.models])
            
        # 3. 执行消歧
        if all_entities:
            self._log(f"  正在对 {len(all_entities)} 个实体进行消歧...")
            mapping = await self.entity_disambiguator.disambiguate(all_entities)
        else:
            mapping = {}
            
        # 4. 合并结果并应用消歧
        for paper, entities in zip(papers, entities_list):
            # 辅助函数：应用映射
            def map_vals(vals):
                return list(set([mapping.get(v, v) for v in vals]))

            paper['semantic_entities'] = {
                'problem': [p.value for p in entities.problems],
                'method': map_vals([m.value for m in entities.methods]),
                'model': map_vals([m.value for m in entities.models]),
                'task': map_vals([t.value for t in entities.tasks]),
                'dataset': [d.value for d in entities.datasets],
                'metric': [m.value for m in entities.metrics],
                'innovation': [i.value for i in entities.innovations]
            }
            
            # 更新数据库
            paper_id = paper.get('paper_id') or paper.get('id')
            if paper_id:
                self.db.update_paper(paper_id, {
                    'innovations': paper['semantic_entities'].get('innovation', []),
                    'research_domains': paper['semantic_entities'].get('task', [])
                })
        
        self._update_progress("extract", 100, "属性提取完成")
        self._log(f"  ✓ 属性提取完成")
        
        return papers
    
    async def _stage_discover_relations(self, papers: List[Dict]) -> List[Dict]:
        """阶段5: 关系发现 (含引用上下文分析，20线程高并发)"""
        self._update_progress("relations", 0, "发现论文间关系...")
        self._log(f"🔗 阶段5: 关系发现 ({len(papers)}篇，20线程并发)")
        
        all_relations = []
        
        # 1. 引用上下文分析 (针对有全文的论文) - 跳过以加速
        # for paper in papers:
        #     if paper.get('full_text'):
        #         try:
        #             contexts = await self.citation_analyzer.extract_contexts(paper['full_text'])
        #         except Exception as e:
        #             self._log(f"  ⚠️ 引用分析失败: {e}", "warning")

        # 确保新论文都有 paper_id 字段
        for paper in papers:
            if 'paper_id' not in paper and 'id' in paper:
                paper['paper_id'] = paper['id']

        # 2. 获取现有论文作为背景
        existing_papers = self.db.get_all_papers()
        self._log(f"  现有论文: {len(existing_papers)}篇")
        
        # 确保现有论文都有 paper_id 字段
        for paper in existing_papers:
            if 'paper_id' not in paper and 'id' in paper:
                paper['paper_id'] = paper['id']
        
        # 3. 定义进度回调
        def relation_progress_callback(completed: int, total: int, found: int):
            """关系发现进度回调"""
            if total > 0:
                pct = (completed / total) * 100
                self._update_progress(
                    "relations",
                    pct,
                    f"关系提取: {completed}/{total} ({pct:.1f}%) | 已发现: {found}条"
                )
                # 每10%打印一次日志
                if completed % max(1, total // 10) == 0 or completed == total:
                    self._log(f"  进度: {completed}/{total} ({pct:.1f}%) | 已发现: {found}条关系")
        
        # 4. 使用增量关系发现器 (20线程高并发)
        relations = await self.relation_discoverer.discover_relations(
            new_papers=papers,
            existing_papers=existing_papers,
            max_concurrent=20,  # 固定20线程并发
            progress_callback=relation_progress_callback
        )
        all_relations.extend(relations)
        
        # 5. 存储关系到数据库
        self._log(f"  存储 {len(all_relations)} 条关系到数据库...")
        for rel in all_relations:
            self.db.execute_cypher(
                """
                MATCH (a:Paper {id: $src}), (b:Paper {id: $tgt})
                MERGE (a)-[r:SEMANTIC_RELATION]->(b)
                SET r.type = $type, r.confidence = $conf, r.evidence = $evidence
                """,
                {
                    "src": rel['source'],
                    "tgt": rel['target'],
                    "type": rel['type'],
                    "conf": rel['confidence'],
                    "evidence": rel.get('evidence', '')
                }
            )
        
        self._update_progress("relations", 100, f"发现{len(all_relations)}条关系")
        self._log(f"  ✓ 关系发现完成: {len(all_relations)}条")
        
        return all_relations
    
    async def _stage_community_detection(self) -> Dict[int, List[str]]:
        """阶段6: 社区发现和命名"""
        self._update_progress("community", 0, "检测社区...")
        self._log(f"🏘️ 阶段6: 社区发现")
        
        # 运行社区检测
        communities = self.db.detect_communities()
        
        self._log(f"  ✓ 检测到 {len(communities)} 个社区")
        
        # 为社区命名
        if self.config.enable_community_naming:
            self._update_progress("community", 50, "为社区命名...")
            
            for comm_id, paper_ids in communities.items():
                if len(paper_ids) < self.config.min_community_size:
                    continue
                
                # 获取社区中的代表性论文
                top_papers = await self._get_top_papers_in_community(paper_ids, limit=5)
                
                if top_papers:
                    # 使用LLM生成社区名称
                    community_name = await self._generate_community_name(top_papers)
                    
                    if community_name:
                        # 存储社区名称
                        self.db.execute_cypher(
                            """
                            MERGE (c:Community {id: $id})
                            SET c.name = $name, c.paper_count = $count
                            """,
                            {"id": comm_id, "name": community_name, "count": len(paper_ids)}
                        )
                        
                        self._log(f"    社区{comm_id}: {community_name} ({len(paper_ids)}篇)")
        
        self._update_progress("community", 100, f"社区处理完成")
        return communities
    
    async def _get_top_papers_in_community(self, paper_ids: List[str], limit: int = 5) -> List[Dict]:
        """获取社区中的代表性论文（按引用数排序）"""
        try:
            results = self.db.execute_cypher(
                """
                MATCH (p:Paper)
                WHERE p.id IN $ids
                RETURN p.id AS id, p.title AS title, p.abstract AS abstract, p.citations AS citations
                ORDER BY p.citations DESC
                LIMIT $limit
                """,
                {"ids": paper_ids, "limit": limit}
            )
            return results
        except:
            return []
    
    async def _generate_community_name(self, papers: List[Dict]) -> Optional[str]:
        """使用LLM生成社区名称"""
        try:
            # 构建prompt
            papers_text = "\n".join([
                f"- {p.get('title', '')}: {p.get('abstract', '')[:200]}..."
                for p in papers[:5]
            ])
            
            prompt = f"""Based on the following research papers in a community, generate a concise name (3-5 words) that captures the main research theme:

{papers_text}

Community name (3-5 words only):"""
            
            # 调用LLM
            name = await self.community_labeler.label_community(papers)
            return name
            
        except Exception as e:
            self._log(f"社区命名失败: {e}", "warning")
            return None
    
    async def _extract_subgraph(self, topic: str) -> Dict[str, Any]:
        """提取Topic的子图谱"""
        try:
            # 获取论文
            papers = self.db.execute_cypher(
                """
                MATCH (p:Paper)-[:BELONGS_TO]->(t:Topic {name: $topic})
                RETURN p
                """,
                {"topic": topic}
            )
            
            # 获取关系
            relations = self.db.execute_cypher(
                """
                MATCH (p1:Paper)-[:BELONGS_TO]->(t:Topic {name: $topic})
                MATCH (p1)-[r]->(p2:Paper)
                RETURN p1.id AS src, p2.id AS tgt, type(r) AS type
                """,
                {"topic": topic}
            )
            
            # 获取社区
            communities = self.db.execute_cypher(
                """
                MATCH (p:Paper)-[:BELONGS_TO]->(t:Topic {name: $topic})
                RETURN p.community_id AS comm_id, collect(p.id) AS paper_ids
                """,
                {"topic": topic}
            )
            
            return {
                "papers": [p.get('p', {}) for p in papers],
                "relations": relations,
                "communities": {c['comm_id']: c['paper_ids'] for c in communities if c['comm_id']}
            }
            
        except Exception as e:
            self._log(f"提取子图谱失败: {e}", "error")
            return {"papers": [], "relations": [], "communities": {}}


# 便捷函数
def create_orchestrator(config: PipelineConfig = None) -> MEKGPipelineOrchestrator:
    """创建编排器实例"""
    return MEKGPipelineOrchestrator(config)


async def build_topic(topic: str, **kwargs) -> Dict[str, Any]:
    """便捷函数：构建单个Topic"""
    orchestrator = MEKGPipelineOrchestrator()
    return await orchestrator.build_topic(topic, **kwargs)


if __name__ == "__main__":
    async def test():
        config = PipelineConfig(
            target_paper_count=50,
            enable_pdf_download=False,
            enable_community_naming=False
        )
        
        orchestrator = MEKGPipelineOrchestrator(config)
        
        # 测试分析
        status = await orchestrator.analyze_topic("Large Language Model Agents")
        print(f"Status: {status}")
        
        # 测试构建
        # result = await orchestrator.build_topic("Large Language Model Agents")
        # print(f"Result: {result}")
    
    asyncio.run(test())