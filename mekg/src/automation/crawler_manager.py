import threading
import asyncio
import time
from typing import Optional, Callable, List, Dict, Any
from loguru import logger
from mekg.src.automation.incremental_builder import IncrementalBuilder
from mekg.src.processing.paper_pool_collector import PaperPoolCollector
from mekg.src.analysis.community_labeler import CommunityLabeler
from mekg.src.processing.pdf_processor import PDFProcessor
from mekg.src.extraction.semantic_entity_extractor import SemanticEntityExtractor
from mekg.src.extraction.relation_reasoner import RelationReasoner

class CrawlerManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CrawlerManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.is_running = False
        self.current_task = "Idle"
        self.logs: List[str] = []
        self.stats = {"papers_crawled": 0, "communities_detected": 0, "last_update": None}
        self._stop_event = threading.Event()
        self._pause_event = threading.Event() # 新增暂停控制
        self._thread: Optional[threading.Thread] = None
        self._log_callback: Optional[Callable] = None
        self.config = {"max_workers": 5, "max_results": 20}
        
        # 组件初始化 - Memgraph 连接参数
        self.memgraph_host = None  # 使用默认值 127.0.0.1
        self.memgraph_port = None  # 使用默认值 7687
        self.memgraph_user = None
        self.memgraph_password = None
        
    def set_log_callback(self, callback: Callable):
        self._log_callback = callback

    def update_config(self, key: str, value: Any):
        self.config[key] = value
        self.add_log(f"⚙️ Config updated: {key} = {value}")
        
    def start_crawler(self):
        if self.is_running:
            return False
        
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.add_log("🚀 Crawler started")
        return True
        
    def stop_crawler(self):
        if not self.is_running:
            return False
            
        self.add_log("🛑 Stopping crawler...")
        self._stop_event.set()
        # 线程会检测 stop_event 并退出
        return True
        
    def get_status(self) -> Dict:
        return {
            "is_running": self.is_running,
            "current_task": self.current_task,
            "stats": self.stats,
            "recent_logs": self.logs[-20:] # 返回最近20条日志
        }
        
    def add_log(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]
        logger.info(message)
        
        # 触发回调
        if self._log_callback:
            try:
                self._log_callback(log_entry)
            except Exception as e:
                logger.error(f"Log callback failed: {e}")

    def _run_loop(self):
        """后台运行的主循环"""
        # 在线程内部创建 event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._async_crawl_logic())
        except Exception as e:
            self.add_log(f"❌ Crawler crashed: {e}")
        finally:
            self.is_running = False
            self.current_task = "Stopped"
            loop.close()
            
    async def _async_crawl_logic(self):
        # 初始化组件 - 使用 Memgraph
        builder = IncrementalBuilder(
            host=self.memgraph_host,
            port=self.memgraph_port,
            user=self.memgraph_user,
            password=self.memgraph_password
        )
        collector = PaperPoolCollector()
        labeler = CommunityLabeler()
        pdf_processor = PDFProcessor()
        extractor = SemanticEntityExtractor()
        reasoner = RelationReasoner()
        
        self.add_log("🔧 Components initialized")
        
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                self.current_task = "Paused"
                await asyncio.sleep(1)
                continue

            try:
                # 1. 扫描 arXiv (获取最新论文 + PDF) 并用 OpenAlex 增强
                self.current_task = "Scanning arXiv..."
                self.add_log("📡 Scanning arXiv for latest AI papers...")
                
                papers = await collector.fetch_latest_arxiv_papers(
                    categories=["cs.AI", "cs.CL", "cs.CV", "cs.LG"],
                    max_results=self.config["max_results"]
                )
                
                if not papers:
                    self.add_log("⚠️ No new papers found")
                    await asyncio.sleep(10)
                    continue
                    
                # 2. 并发深度解析 (PDF + LLM)
                self.current_task = f"Processing {len(papers)} papers..."
                self.add_log(f"🚀 Starting concurrent processing for {len(papers)} papers...")
                
                # (已在下方重写 process_single_paper，此处删除旧定义以避免冲突)

                # 资源控制：分离 IO 和 CPU 任务
                # IO 信号量 (下载/LLM): 允许较高并发
                io_semaphore = asyncio.Semaphore(self.config["max_workers"])
                # CPU 信号量 (PDF解析): 严格限制并发，避免风扇狂转
                cpu_semaphore = asyncio.Semaphore(2)

                async def process_single_paper(paper):
                    if not paper: return None
                    paper_id = paper.get('id') or paper.get('paper_id')
                    if not paper_id: return None

                    try:
                        # 2.1 下载 PDF (IO 密集)
                        async with io_semaphore:
                            pdf_url = paper.get('pdf_url')
                            pdf_path = None
                            if pdf_url:
                                pdf_path = await pdf_processor.download_pdf(pdf_url, paper_id)
                        
                        # 2.2 提取全文 (CPU 密集 - 限制并发)
                        full_text = ""
                        if pdf_path:
                            async with cpu_semaphore:
                                # 在线程池中运行，避免阻塞事件循环
                                full_text = await asyncio.to_thread(pdf_processor.extract_text_from_pdf, pdf_path)
                                # 给 CPU 一点喘息时间
                                await asyncio.sleep(0.1)
                        
                        # 2.3 深度属性提取 (IO 密集)
                        async with io_semaphore:
                            if len(full_text) > 1000:
                                advanced_attrs = await extractor.extract_from_full_text(paper.get('title', ''), full_text)
                                if advanced_attrs:
                                    paper.update(advanced_attrs)
                    
                            # 2.4 基础属性提取
                            enriched_list = await builder._enrich_papers([paper])
                            return enriched_list[0] if enriched_list else None
                            
                    except Exception as e:
                        logger.error(f"Failed to process {paper_id}: {e}")
                        return None

                tasks = [process_single_paper(p) for p in papers]
                results = await asyncio.gather(*tasks)
                
                # 3. 批量存入数据库
                valid_papers = [p for p in results if p]
                processed_count = 0
                for paper in valid_papers:
                    if builder.db.add_paper(paper):
                        processed_count += 1
                        
                self.stats["papers_crawled"] += processed_count
                self.stats["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.add_log(f"✅ Successfully processed {processed_count}/{len(papers)} papers")

                # 3.5 语义编织 (Semantic Weaving)
                if processed_count > 0:
                    self.current_task = "Weaving semantic graph..."
                    self.add_log("🕸️ Weaving semantic connections (LLM Reasoning)...")
                    await self._weave_semantic_graph(builder, valid_papers, reasoner)
                
                # 4. 社区发现
                self.current_task = "Detecting communities..."
                self.add_log("🔍 Running community detection...")
                communities = builder.db.detect_communities()
                
                if self._stop_event.is_set(): break
                
                # 4. 社区命名
                for comm_id, paper_ids in communities.items():
                    if self._stop_event.is_set(): break
                    if len(paper_ids) < 5: continue
                    
                    # 检查是否已命名 (简化逻辑)
                    # ... (这里可以复用之前的逻辑)
                    
                    self.current_task = f"Labeling community {comm_id}..."
                    # 模拟命名过程
                    # topic_name = await labeler.label_community(...)
                    # builder.db.add_topic(topic_name)
                    
                self.stats["communities_detected"] = len(communities)
                
                # 休息
                self.current_task = "Sleeping..."
                self.add_log("😴 Resting for 60s...")
                
                # 分段睡眠以便快速响应停止信号
                for _ in range(60):
                    if self._stop_event.is_set(): break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                self.add_log(f"⚠️ Error in loop: {e}")
                await asyncio.sleep(10)

    async def _weave_semantic_graph(self, builder, papers, reasoner):
        """基于共享实体和 LLM 推理建立语义连接"""
        count = 0
        
        # 1. 基础连接：通过 Semantic Entity (Method, Domain) 连接
        try:
            for paper in papers:
                paper_id = paper.get('id') or paper.get('paper_id')
                if not paper_id: continue
                
                # Method -> SemanticEntity
                method_info = paper.get('method_info', {})
                if isinstance(method_info, dict):
                    method_name = method_info.get('name')
                else:
                    method_name = None
                    
                if method_name:
                    entity_id = f"Method:{method_name}"
                    # 使用 Memgraph 的方法创建实体和关系
                    builder.db.add_semantic_entity(entity_id, method_name, 'method')
                    if builder.db.link_paper_to_entity(paper_id, entity_id, "PROPOSES"):
                        count += 1

                # 2. 深度推理：处理引用关系
                # 如果 OpenAlex 提供了引用列表，我们尝试找出被引用的论文（如果也在库中）
                # 并使用 LLM 推断引用类型
                refs = paper.get('referenced_works', [])
                if refs:
                    # 查找库中已存在的引用论文
                    for ref_id in refs:  # ref_id 通常是 OpenAlex ID
                        target_id = ref_id
                        
                        # 检查目标论文是否存在
                        target_paper = builder.db.get_paper_by_id(target_id)
                        if target_paper:
                            # 调用 LLM 推理关系
                            self.add_log(f"🧠 Reasoning relation: {paper.get('title', '')[:20]}... -> {target_paper.get('title', '')[:20]}...")
                            relation = await reasoner.infer_relation(paper, target_paper)
                            
                            if relation:
                                rel_type = relation['relation_type']
                                # 使用 Memgraph 的 execute_cypher 创建带属性的边
                                builder.db.execute_cypher(
                                    """
                                    MATCH (a:Paper {id: $src}), (b:Paper {id: $tgt})
                                    MERGE (a)-[r:CITES]->(b)
                                    SET r.type = $type, r.reasoning = $reason
                                    """,
                                    {
                                        "src": paper_id,
                                        "tgt": target_id,
                                        "type": rel_type,
                                        "reason": relation.get('reasoning', '')
                                    }
                                )
                                count += 1
                                self.add_log(f"✨ Inferred: {rel_type}")

        except Exception as e:
            logger.error(f"Weaving failed: {e}")
                
        self.add_log(f"🔗 Created {count} semantic connections")