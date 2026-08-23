"""
Incremental MEKG Builder
实现基于 Topic 状态的三路自动化构建逻辑。
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from mekg.src.storage.memgraph_graph_db import MemgraphGraphDB
from mekg.src.processing.paper_pool_collector import PaperPoolCollector
from mekg.src.extraction.semantic_entity_extractor import SemanticEntityExtractor

class IncrementalBuilder:
    def __init__(self, host: str = None, port: int = None, user: str = None, password: str = None):
        """
        初始化增量构建器
        
        Args:
            host: Memgraph 主机地址，默认从环境变量读取
            port: Memgraph 端口，默认 7687
            user: 用户名
            password: 密码
        """
        self.db = MemgraphGraphDB(host=host, port=port, user=user, password=password)
        self.collector = PaperPoolCollector()
        self.extractor = SemanticEntityExtractor(max_workers=5) # 限制并发以避免限流
        
    async def build_topic(self, topic: str, target_count: int = 100) -> Dict[str, Any]:
        """
        构建 Topic 知识图谱 (三路逻辑入口)
        
        Args:
            topic: 主题名称
            target_count: 目标论文数量
            
        Returns:
            构建结果统计
        """
        logger.info(f"Starting build process for topic: {topic}")
        
        # 1. 检查状态
        status = self.db.get_topic_status(topic)
        logger.info(f"Topic status: {status}")
        
        result = {
            "topic": topic,
            "path": "",
            "new_papers": 0,
            "total_papers": 0
        }
        
        # 2. 路由逻辑
        if not status['exists']:
            # Path 1: Cold Start
            logger.info("Path 1: Cold Start - Topic not found, starting full crawl")
            result["path"] = "cold_start"
            await self._run_cold_start(topic, target_count)
            
        elif status['needs_update']:
            # Path 2: Incremental Update
            logger.info("Path 2: Incremental Update - Updating existing topic")
            result["path"] = "incremental"
            await self._run_incremental(topic, status['last_updated'], target_count)
            
        else:
            # Path 3: Direct Use
            logger.info("Path 3: Direct Use - Data is sufficient")
            result["path"] = "direct"
            
        # 3. 更新最终统计
        final_status = self.db.get_topic_status(topic)
        result["total_papers"] = final_status['paper_count']
        
        return result
        
    async def _run_cold_start(self, topic: str, target_count: int):
        """冷启动构建"""
        # 1. 创建 Topic 节点
        self.db.add_topic(topic)
        
        # 2. 爬取论文
        papers = await self.collector.collect_comprehensive_pool(
            keywords=[topic],
            target_count=target_count,
            year_start=2018,
            year_end=datetime.now().year,
            use_survey_strategy=True # 启用综述优先策略
        )
        
        # 3. 语义增强 (LLM 解析)
        enriched_papers = await self._enrich_papers(papers)
        
        # 4. 存入数据库
        self._save_papers(enriched_papers, topic)
        
    async def _run_incremental(self, topic: str, last_updated: datetime, target_count: int):
        """增量构建"""
        # 1. 确定时间范围
        start_year = last_updated.year if last_updated else 2023
        
        # 2. 爬取新论文
        papers = await self.collector.collect_comprehensive_pool(
            keywords=[topic],
            target_count=target_count // 2, # 增量通常不需要那么多
            year_start=start_year,
            year_end=datetime.now().year,
            use_survey_strategy=False # 增量时可能不需要综述策略，或者视情况而定
        )
        
        # 3. 语义增强 (LLM 解析)
        enriched_papers = await self._enrich_papers(papers)
        
        # 4. 存入数据库
        self._save_papers(enriched_papers, topic)
        
        # 5. 更新 Topic 时间
        self.db.add_topic(topic)
    
    async def _enrich_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """使用 LLM 增强论文信息"""
        if not papers:
            return []
            
        logger.info(f"Enriching {len(papers)} papers with semantic entities...")
        
        # 批量抽取
        entities_list = await self.extractor.batch_extract(papers, show_progress=True)
        
        # 合并结果
        enriched_papers = []
        for paper, entities in zip(papers, entities_list):
            # 将抽取结果转换回字典格式，以便存入 Memgraph
            # 注意：我们需要适配 MemgraphGraphDB.add_paper 期望的格式
            
            # Method Info (STRUCT)
            method_name = entities.methods[0].value if entities.methods else ""
            method_desc = entities.methods[0].value if entities.methods else "" # 暂时复用 value，理想情况应该有单独的 desc
            paper['method_info'] = {'name': method_name, 'description': method_desc}
            
            # Innovations (LIST)
            paper['innovations'] = [i.value for i in entities.innovations]
            
            # Research Domains (LIST) - 这里用 Tasks 代替
            paper['research_domains'] = [t.value for t in entities.tasks]
            
            # Limitations (LIST) - 目前提取器没提取这个，留空
            paper['limitations'] = []
            
            enriched_papers.append(paper)
            
        return enriched_papers

    def _save_papers(self, papers: List[Dict[str, Any]], topic: str):
        """保存论文并建立链接"""
        count = 0
        for paper in papers:
            # 1. 添加论文
            if self.db.add_paper(paper):
                count += 1
                
            # 2. 链接到 Topic
            # 简单的相关性计算：如果来自关键词搜索，相关性高
            score = 0.9 if paper.get('from_keyword_search') else 0.7
            self.db.link_paper_to_topic(paper['paper_id'], topic, score)
            
            # 3. 处理引用关系
            # PaperPoolCollector 已经收集了 referenced_works
            for ref_id in paper.get('referenced_works', []):
                # 只有当引用的论文也在库里时才添加关系（或者我们可以创建占位节点）
                # 这里简化处理：尝试添加引用关系，add_citation 会检查节点是否存在
                self.db.add_citation(paper['paper_id'], ref_id)
                
        logger.info(f"Saved {count} papers for topic {topic}")

    def close(self):
        self.db.close()