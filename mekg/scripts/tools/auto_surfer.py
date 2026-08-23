import asyncio
import sys
import os
import random
import time
from collections import deque
from loguru import logger

# 添加项目根目录到路径
sys.path.append(os.getcwd())

from src.modules.mekg.automation.incremental_builder import IncrementalBuilder
from src.modules.mekg.paper_pool_collector import PaperPoolCollector
from src.modules.mekg.community_labeler import CommunityLabeler

class CommunityAutoSurfer:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        """
        初始化社区自动冲浪器
        
        Args:
            uri: Memgraph 连接 URI，默认从环境变量读取
            user: 用户名
            password: 密码
        """
        self.builder = IncrementalBuilder(uri=uri, user=user, password=password)
        self.collector = PaperPoolCollector()
        self.labeler = CommunityLabeler()
        self.processed_community_ids = set()
        
    async def start_surfing(self):
        logger.info("🏄 Community AutoSurfer started! Monitoring arXiv for AI trends...")
        
        while True:
            try:
                # 1. 扫描 arXiv 获取最新 AI 论文
                logger.info("📡 Scanning arXiv for new papers...")
                papers = await self.collector.fetch_latest_arxiv_papers(
                    categories=["cs.AI", "cs.CL", "cs.CV", "cs.LG"], 
                    max_results=50 # 每次只取最新的一批
                )
                
                if not papers:
                    logger.warning("No papers found. Waiting...")
                    await asyncio.sleep(60)
                    continue
                    
                # 2. 存入数据库并增强
                logger.info(f"📥 Ingesting {len(papers)} papers...")
                # 这里我们复用 builder 的 save 逻辑，但跳过 topic 链接（因为还没 topic）
                # 我们需要先 enrich，再 save
                enriched_papers = await self.builder._enrich_papers(papers)
                
                # 直接使用 builder.db 添加论文
                count = 0
                for paper in enriched_papers:
                    if self.builder.db.add_paper(paper):
                        count += 1
                logger.info(f"✅ Saved {count} new papers to Memgraph")
                
                # 3. 运行社区发现 (Community Detection)
                # 这一步会更新数据库中论文的 community_id
                logger.info("🔍 Detecting research communities...")
                communities = self.builder.db.detect_communities()
                
                # 4. 为新社区命名 (Topic Generation)
                for comm_id, paper_ids in communities.items():
                    # 如果社区太小，忽略
                    if len(paper_ids) < 5:
                        continue
                        
                    # 如果已经处理过这个 ID，且论文数变化不大，可能不需要重新命名
                    # 但为了简单起见，我们这里假设 ID 可能会变（Leiden算法特性），或者我们只关心Top社区
                    # 更好的做法是检查该社区是否已经有关联的 Topic 节点
                    
                    # 检查是否已存在 Topic 链接
                    # 随机抽样检查
                    sample_id = paper_ids[0]
                    results = self.builder.db.execute_cypher(
                        "MATCH (p:Paper {id: $pid})-[:BELONGS_TO]->(t:Topic) RETURN t.name AS name",
                        {"pid": sample_id}
                    )
                    if results:
                        topic_name = results[0]['name']
                        logger.info(f"Community {comm_id} already labeled as: {topic_name}")
                        continue
                    
                    # 需要命名
                    logger.info(f"🏷️ Labeling new community {comm_id} ({len(paper_ids)} papers)...")
                    
                    # 获取社区内的论文详情用于 LLM 总结
                    community_papers = []
                    # 这里为了性能，只取前几篇
                    for pid in paper_ids[:5]:
                        paper = self.builder.db.get_paper_by_id(pid)
                        if paper:
                            community_papers.append({
                                "title": paper.get('title', ''),
                                "abstract": paper.get('abstract', '')
                            })
                        
                    topic_name = await self.labeler.label_community(community_papers)
                    logger.info(f"✨ New Topic Discovered: {topic_name}")
                    
                    # 5. 回写 Topic 节点并建立链接
                    self.builder.db.add_topic(topic_name)
                    for pid in paper_ids:
                        self.builder.db.link_paper_to_topic(pid, topic_name, score=0.9)
                        
                logger.info("😴 Resting for 5 minutes before next scan...")
                await asyncio.sleep(300) # 每5分钟扫描一次
                
            except Exception as e:
                logger.error(f"💥 Surfer crash: {e}")
                await asyncio.sleep(60)

if __name__ == "__main__":
    surfer = CommunityAutoSurfer()
    asyncio.run(surfer.start_surfing())