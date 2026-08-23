"""
Topic 驱动构建器

负责从指定 Topic 出发，执行"爬取 -> 关系提取 -> 图谱编织"的全流程。
"""

import asyncio
from typing import Dict, List, Any, Optional
from loguru import logger

from mekg.src.storage.persistent_graph_db import PersistentGraphDB, get_default_db, SubGraph
from mekg.src.processing.paper_pool_collector import PaperPoolCollector
# 假设有一个关系提取器，如果没有则使用简单的规则或 LLM
# from src.modules.mekg.semantic_entity_extractor import SemanticEntityExtractor 

class TopicGraphBuilder:
    def __init__(self, db: PersistentGraphDB = None):
        self.db = db or get_default_db()
        self.collector = PaperPoolCollector()
        
    async def build_graph_for_topic(
        self, 
        topic: str, 
        limit: int = 50,
        year_start: int = 2020
    ) -> SubGraph:
        """
        为指定 Topic 构建知识图谱
        
        Args:
            topic: Topic 名称
            limit: 爬取论文数量限制
            year_start: 起始年份
            
        Returns:
            构建好的子图
        """
        logger.info(f"开始为 Topic '{topic}' 构建图谱...")
        
        # 1. 检查数据库中是否已有足够数据
        existing_papers = self.db.get_topic_papers(topic)
        if len(existing_papers) >= limit:
            logger.info(f"Topic '{topic}' 已有 {len(existing_papers)} 篇论文，直接提取子图")
            return self.db.extract_subgraph_by_topic(topic, max_nodes=limit)
            
        # 2. 爬取新数据
        logger.info(f"数据不足，开始爬取: {topic}")
        papers = await self.collector.collect_comprehensive_pool(
            keywords=[topic],
            target_count=limit,
            year_start=year_start,
            enrich_cited_by=True,
            use_survey_strategy=True
        )
        
        if not papers:
            logger.warning(f"未找到关于 '{topic}' 的论文")
            return SubGraph(nodes=[], edges=[], topic=topic)
            
        # 3. 入库
        logger.info(f"将 {len(papers)} 篇论文存入数据库")
        self.db.add_papers_batch(papers)
        
        # 4. 建立 Topic 关联
        self.db.add_topic(topic)
        for p in papers:
            # 简单的相关性分数，实际可根据搜索排名计算
            self.db.link_paper_to_topic(p['paper_id'], topic, relevance_score=1.0)
            
        # 5. 关系编织 (简化版)
        # 这里我们主要利用引用关系，如果有 SemanticEntityExtractor 可以进一步提取语义关系
        logger.info("编织引用关系...")
        citations = []
        for p in papers:
            # 处理参考文献
            if 'referenced_works' in p:
                for ref_id in p['referenced_works']:
                    # 只添加库中已存在的引用关系，避免悬空边
                    if self.db.paper_exists(ref_id):
                        citations.append((p['paper_id'], ref_id))
            
            # 处理被引
            if 'cited_by' in p:
                for citing_id in p['cited_by']:
                    if self.db.paper_exists(citing_id):
                        citations.append((citing_id, p['paper_id']))
                        
        self.db.add_citations_batch(citations)
        
        # 6. 提取子图
        logger.info("提取最终子图")
        subgraph = self.db.extract_subgraph_by_topic(topic, max_nodes=limit)
        
        return subgraph

if __name__ == "__main__":
    # 测试代码
    async def test():
        builder = TopicGraphBuilder()
        # subgraph = await builder.build_graph_for_topic("LLM Agents", limit=10)
        # print(f"构建完成: {len(subgraph.nodes)} 节点")
        pass
    
    # asyncio.run(test())