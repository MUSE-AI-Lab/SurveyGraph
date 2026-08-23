import asyncio
import sys
import os
import time
from loguru import logger

# 添加项目根目录到路径
sys.path.append(os.getcwd())

from src.modules.mekg.storage.memgraph_graph_db import MemgraphGraphDB
from src.modules.mekg.pdf_processor import PDFProcessor
from src.modules.mekg.semantic_entity_extractor import SemanticEntityExtractor
from src.modules.mekg.relation_reasoner import RelationReasoner

async def reprocess():
    logger.info("🔄 Starting data reprocessing...")
    
    db = MemgraphGraphDB()
    pdf_processor = PDFProcessor()
    extractor = SemanticEntityExtractor()
    reasoner = RelationReasoner()
    
    # 1. 获取所有论文
    papers = []
    # 使用 Memgraph 的 execute_cypher 方法
    results = db.execute_cypher("MATCH (p:Paper) RETURN p.id AS id, p.title AS title, p.pdf_url AS pdf_url, p.method_info AS method_info")
    for row in results:
        method_info = row['method_info']
        # 如果 method_info 是 JSON 字符串，解析它
        if isinstance(method_info, str):
            import json
            try:
                method_info = json.loads(method_info)
            except:
                method_info = {}
        papers.append({
            "id": row['id'],
            "title": row['title'],
            "pdf_url": row['pdf_url'],
            "method_info": method_info or {}
        })
        
    logger.info(f"Found {len(papers)} papers in database")
    
    # 2. 补全深度属性
    for paper in papers:
        # 检查是否已有深度属性 (这里简单判断 method_info 是否为空，或者可以检查其他字段)
        # 如果 method_info 只有默认值，说明可能需要重新提取
        if not paper['method_info'] or not paper['method_info'].get('name'):
            logger.info(f"Processing {paper['id']}...")
            
            if paper['pdf_url']:
                try:
                    pdf_path = await pdf_processor.download_pdf(paper['pdf_url'], paper['id'])
                    if pdf_path:
                        text = pdf_processor.extract_text_from_pdf(pdf_path)
                        if len(text) > 1000:
                            attrs = await extractor.extract_from_full_text(paper['title'], text)
                            
                            # 更新数据库
                            # 注意：Kuzu 的 UPDATE 语法
                            # 这里我们需要把 attrs 转换成 Cypher SET 语句
                            # 简化起见，我们只更新 method_info
                            if attrs.get('method_info'):
                                # 使用 Memgraph 的 update_paper 方法
                                db.update_paper(paper['id'], {'method_info': attrs['method_info']})
                                logger.info(f"Updated {paper['id']}")
                except Exception as e:
                    logger.error(f"Failed to process {paper['id']}: {e}")

    # 3. 重建关系 (语义编织)
    logger.info("🕸️ Weaving semantic graph...")
    # 这里复用 CrawlerManager 的逻辑，但需要稍微调整以适应已存在的论文
    # 为了简单，我们只做基础的 Method/Domain 连接
    
    count = 0
    for paper in papers:
        method_info = paper.get('method_info', {})
        if isinstance(method_info, dict):
            method_name = method_info.get('name')
        else:
            method_name = None
            
        if method_name:
            entity_id = f"Method:{method_name}"
            # 确保实体存在并建立关系 - Memgraph 支持 MERGE
            db.add_semantic_entity(entity_id, method_name, 'method')
            # 建立边 - 使用 link_paper_to_entity 方法
            if db.link_paper_to_entity(paper['id'], entity_id, "PROPOSES"):
                count += 1
    logger.info(f"Created {count} new connections")

    logger.info("✅ Reprocessing complete!")

if __name__ == "__main__":
    # 确保在项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    os.chdir(project_root)
    
    # Memgraph 支持并发访问，无需检查文件锁
    logger.info("🚀 Using Memgraph - concurrent access supported!")
    logger.info("📡 Connecting to Memgraph at bolt://localhost:7687")
    
    asyncio.run(reprocess())