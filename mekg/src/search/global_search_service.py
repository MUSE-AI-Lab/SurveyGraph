"""
全局图谱搜索服务 - GlobalSearchService

提供对全局学术图谱的检索功能，支持关键词搜索、实体搜索和子图提取。
"""

from typing import List, Dict, Any, Optional
from loguru import logger
from mekg.src.storage.semantic_entity_db import SemanticEntityDB

class GlobalSearchService:
    """
    全局图谱搜索服务
    """
    
    def __init__(self, db_path: str = "data/graph_db/global_academic_graph.db"):
        """
        初始化搜索服务
        
        Args:
            db_path: 全局数据库路径
        """
        self.db = SemanticEntityDB(db_path)
        logger.info(f"GlobalSearchService initialized with DB: {db_path}")
        
    def search_papers(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        基于关键词搜索论文
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            论文列表
        """
        # 目前 SemanticEntityDB 还没有专门的 search_papers 方法，
        # 我们可以在这里实现一个简单的基于 SQL LIKE 的搜索，
        # 或者未来扩展为 FTS (Full Text Search)。
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            # 简单的标题和摘要搜索
            sql = """
                SELECT paper_id, title, abstract, year, citations 
                FROM papers 
                WHERE title LIKE ? OR abstract LIKE ?
                ORDER BY citations DESC
                LIMIT ?
            """
            like_query = f"%{query}%"
            cursor.execute(sql, (like_query, like_query, limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "paper_id": row[0],
                    "title": row[1],
                    "abstract": row[2],
                    "year": row[3],
                    "citations": row[4]
                })
            return results

    def find_related_papers_by_entity(self, entity_value: str, entity_type: str = None) -> List[Dict[str, Any]]:
        """
        通过语义实体查找相关论文
        
        Args:
            entity_value: 实体名称 (如 "Transformer")
            entity_type: 实体类型 (如 "model", "method")
            
        Returns:
            论文列表
        """
        paper_ids = self.db.get_papers_by_entity(entity_type, entity_value) if entity_type else []
        
        # 如果没有指定类型，搜索所有类型
        if not entity_type:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT paper_id FROM semantic_entities 
                    WHERE entity_value = ? OR canonical_value = ?
                """, (entity_value, entity_value))
                paper_ids = [row[0] for row in cursor.fetchall()]
                
        results = []
        for pid in paper_ids:
            paper = self.db.get_paper(pid)
            if paper:
                results.append(paper)
        return results

    def get_topic_subgraph(self, topic: str) -> Dict[str, Any]:
        """
        提取指定Topic的子图
        
        Args:
            topic: Topic名称
            
        Returns:
            包含节点和边的字典
        """
        paper_ids = self.db.get_topic_papers(topic)
        papers = []
        for pid in paper_ids:
            p = self.db.get_paper(pid)
            if p:
                papers.append(p)
                
        # 获取这些论文之间的关系
        relations = []
        # 这是一个简单的实现，实际可能需要更复杂的查询
        for i, pid1 in enumerate(paper_ids):
            for pid2 in paper_ids[i+1:]:
                rels = self.db.get_relations_between(pid1, pid2)
                relations.extend(rels)
                
        return {
            "topic": topic,
            "papers": papers,
            "relations": relations
        }

    def get_statistics(self) -> Dict[str, Any]:
        """获取全局图谱统计信息"""
        return self.db.get_statistics()

if __name__ == "__main__":
    # 测试代码
    service = GlobalSearchService("data/graph_db/test_global_graph.db")
    results = service.search_papers("question answering")
    print(f"Found {len(results)} papers")
    for p in results[:3]:
        print(f"- {p['title']} ({p['year']})")