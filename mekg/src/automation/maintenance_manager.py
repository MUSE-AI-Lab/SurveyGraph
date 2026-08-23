"""
MEKG 自动化维护管理器

负责图谱的定期扫描、社区识别、Topic 语义化以及自动查漏补缺。
"""

import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from mekg.src.storage.persistent_graph_db import PersistentGraphDB, get_default_db
from mekg.src.processing.paper_pool_collector import PaperPoolCollector
from src.models.LLM.ChatAgent import ChatAgent

class AutoMaintenanceManager:
    def __init__(self, db: PersistentGraphDB = None):
        self.db = db or get_default_db()
        self.llm = ChatAgent()
        self.collector = PaperPoolCollector()
        
    async def run_maintenance_cycle(self, auto_fill: bool = True) -> Dict[str, Any]:
        """
        执行一次完整的维护周期
        
        Args:
            auto_fill: 是否自动补充缺失的论文
            
        Returns:
            维护报告
        """
        logger.info("开始自动化维护周期...")
        report = {
            "timestamp": datetime.now().isoformat(),
            "steps": [],
            "new_topics": [],
            "filled_topics": []
        }
        
        # 1. 社区检测
        logger.info("Step 1: 执行社区检测")
        communities = self.db.detect_communities(algorithm='louvain')
        num_communities = len(set(communities.values()))
        report["steps"].append(f"检测到 {num_communities} 个社区")
        
        # 2. Topic 语义化与分析
        logger.info("Step 2: 分析社区 Topic")
        topic_analysis = await self._analyze_communities(communities)
        report["new_topics"] = topic_analysis
        
        # 3. 查漏补缺
        if auto_fill:
            logger.info("Step 3: 自动查漏补缺")
            filled = await self._fill_gaps(topic_analysis)
            report["filled_topics"] = filled
            
        logger.info("维护周期完成")
        return report
        
    async def _analyze_communities(self, communities: Dict[str, int]) -> List[Dict]:
        """分析每个社区，生成 Topic 名称，并检查活跃度"""
        # 按社区ID分组论文
        comm_papers = {}
        for paper_id, comm_id in communities.items():
            if comm_id not in comm_papers:
                comm_papers[comm_id] = []
            comm_papers[comm_id].append(paper_id)
            
        results = []
        
        for comm_id, paper_ids in comm_papers.items():
            # 跳过太小的社区
            if len(paper_ids) < 3:
                continue
                
            # 获取社区内 PageRank 最高的论文作为代表
            papers_data = []
            for pid in paper_ids:
                p = self.db.get_paper(pid)
                if p:
                    papers_data.append(p)
            
            # 按 PageRank 排序 (如果数据库中有 pagerank 字段)
            papers_data.sort(key=lambda x: x.get('pagerank', 0), reverse=True)
            top_papers = papers_data[:5]
            
            # 检查是否已有 Topic
            # 这里简化处理：如果社区ID对应的 Topic 已存在且最近更新过，则跳过 LLM
            # 实际应用中可能需要更复杂的映射逻辑
            
            # 调用 LLM 生成 Topic
            topic_info = await self._generate_topic_name(top_papers)
            
            # 检查活跃度
            years = [p.get('year', 0) for p in papers_data if p.get('year')]
            max_year = max(years) if years else 0
            current_year = datetime.now().year
            is_outdated = (current_year - max_year) > 1
            
            # 保存 Topic 到数据库
            self.db.add_topic(
                topic=topic_info['name'],
                keywords=topic_info['keywords'],
                description=topic_info['description']
            )
            
            # 关联论文到 Topic
            for pid in paper_ids:
                self.db.link_paper_to_topic(pid, topic_info['name'])
                
            results.append({
                "community_id": comm_id,
                "topic": topic_info['name'],
                "paper_count": len(paper_ids),
                "last_active_year": max_year,
                "is_outdated": is_outdated,
                "keywords": topic_info['keywords']
            })
            
        return results
    
    async def _generate_topic_name(self, papers: List[Dict]) -> Dict:
        """使用 LLM 生成 Topic 名称"""
        papers_text = "\n".join([
            f"- {p.get('title')} (Year: {p.get('year')})\n  Abstract: {p.get('abstract', '')[:200]}..."
            for p in papers
        ])
        
        prompt = f"""
        Analyze the following academic papers and identify the common research topic.
        
        Papers:
        {papers_text}
        
        Return a JSON object with the following fields:
        - "name": A short, precise topic name (e.g., "Large Language Model Agents").
        - "keywords": A list of 3-5 related keywords.
        - "description": A one-sentence description of this research area.
        
        JSON Response:
        """
        
        try:
            # 使用 run_in_executor 调用同步的 remote_chat
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.llm.remote_chat(prompt, temperature=0.3)
            )
            
            # 清理 markdown 代码块标记
            response = response.replace("```json", "").replace("```", "").strip()
            return json.loads(response)
        except Exception as e:
            logger.error(f"LLM Topic 生成失败: {e}")
            return {
                "name": f"Unknown Topic",
                "keywords": [],
                "description": "Failed to generate description."
            }

    async def _fill_gaps(self, topic_analysis: List[Dict]) -> List[str]:
        """对陈旧的 Topic 进行补充"""
        filled_topics = []
        
        for item in topic_analysis:
            if item['is_outdated']:
                topic = item['topic']
                logger.info(f"Topic '{topic}' 需要更新 (Last active: {item['last_active_year']})")
                
                # 搜索新论文
                keywords = item['keywords']
                if not keywords:
                    keywords = [topic]
                    
                new_papers = await self.collector.collect_comprehensive_pool(
                    keywords=keywords,
                    target_count=5,  # 少量补充
                    year_start=item['last_active_year'] + 1,
                    year_end=datetime.now().year,
                    enrich_cited_by=False,
                    use_survey_strategy=False
                )
                
                if new_papers:
                    # 添加到数据库
                    count = self.db.add_papers_batch(new_papers)
                    
                    # 关联到 Topic
                    for p in new_papers:
                        self.db.link_paper_to_topic(p['paper_id'], topic)
                        
                    logger.info(f"Topic '{topic}' 补充了 {count} 篇新论文")
                    filled_topics.append(topic)
                    
        return filled_topics

if __name__ == "__main__":
    # 测试代码
    async def test():
        manager = AutoMaintenanceManager()
        # 模拟运行（假设数据库已有数据）
        # report = await manager.run_maintenance_cycle(auto_fill=False)
        # print(json.dumps(report, indent=2, ensure_ascii=False))
        pass
    
    # asyncio.run(test())