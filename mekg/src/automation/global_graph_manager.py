"""
全局图谱管理器 - GlobalGraphManager

负责将各个Task生成的局部图谱（mekg_data.json）合并到全局学术图谱数据库中。
实现知识的累积和复用。
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

from mekg.src.storage.semantic_entity_db import SemanticEntityDB
from mekg.src.core.data_structures import MEKGGraph, MEKGNode, MEKGEdge, RelationType

class GlobalGraphManager:
    """
    全局图谱管理器
    
    Attributes:
        db_path: 全局数据库路径
        db: 语义实体数据库实例
    """
    
    def __init__(self, db_path: str = "data/graph_db/global_academic_graph.db"):
        """
        初始化全局图谱管理器
        
        Args:
            db_path: 全局数据库路径，默认为 data/graph_db/global_academic_graph.db
        """
        self.db_path = db_path
        self.db = SemanticEntityDB(db_path)
        logger.info(f"GlobalGraphManager initialized with DB: {db_path}")
        
    def merge_task_graph(self, mekg_json_path: str, topic: str = None) -> Dict[str, int]:
        """
        将任务生成的图谱合并到全局图谱中
        
        Args:
            mekg_json_path: mekg_data.json 文件路径
            topic: 任务主题（可选，如果json中没有则使用此参数）
            
        Returns:
            统计信息 {
                "new_papers": int,
                "updated_papers": int,
                "new_relations": int,
                "new_entities": int
            }
        """
        path = Path(mekg_json_path)
        if not path.exists():
            logger.error(f"MEKG data file not found: {mekg_json_path}")
            return {"error": "File not found"}
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load MEKG data: {e}")
            return {"error": f"Load failed: {e}"}
            
        # 获取Topic
        current_topic = topic or data.get("topic", "Unknown")
        
        stats = {
            "new_papers": 0,
            "updated_papers": 0,
            "new_relations": 0,
            "new_entities": 0
        }
        
        # 1. 合并论文 (Nodes)
        papers = data.get("papers", [])
        logger.info(f"Merging {len(papers)} papers for topic: {current_topic}")
        
        for paper_data in papers:
            paper_id = paper_data.get("id") or paper_data.get("paper_id")
            if not paper_id:
                continue
                
            # 检查论文是否存在
            exists = self.db.paper_exists(paper_id)
            
            # 构建论文对象
            # 注意：mekg_data.json中的字段可能与数据库字段不完全一致，需要适配
            paper_record = {
                "paper_id": paper_id,
                "title": paper_data.get("title", ""),
                "abstract": paper_data.get("abstract", ""),
                "year": paper_data.get("year"),
                "citations": paper_data.get("citations", 0),
                "authors": paper_data.get("authors", []),
                "attributes": {
                    "category": paper_data.get("category"),
                    "subcategory": paper_data.get("subcategory"),
                    "source": paper_data.get("source"),
                    "pdf_url": paper_data.get("pdf_url")
                },
                "semantic_entities": {} # 暂时留空，后面单独处理
            }
            
            if exists:
                # TODO: 实现更细粒度的更新逻辑，目前简单跳过或覆盖
                # 这里我们选择更新Topic关联，但不覆盖核心元数据（除非新数据更完整）
                stats["updated_papers"] += 1
            else:
                self.db.add_paper(paper_record)
                stats["new_papers"] += 1
            
            # 关联到Topic
            # relevance_score 默认为 1.0，如果是核心论文可以更高
            is_core = paper_data.get("is_core", False)
            self.db.link_paper_to_topic(paper_id, current_topic, relevance=1.0, is_core=is_core)
            
            # 处理语义实体 (如果有)
            # 目前mekg_data.json结构中实体可能分散在不同字段，或者没有显式提取
            # 如果未来有 explicit entities，在这里调用 self.db.add_semantic_entity
            
        # 2. 合并关系 (Edges)
        # mekg_data.json 可能包含 relations 列表
        relations = data.get("relations", [])
        logger.info(f"Merging {len(relations)} relations")
        
        for rel in relations:
            source = rel.get("source")
            target = rel.get("target")
            rel_type = rel.get("type") or rel.get("relation_type")
            
            if source and target and rel_type:
                success = self.db.add_relation(
                    source_id=source,
                    target_id=target,
                    relation_type=rel_type,
                    confidence=rel.get("confidence", 1.0),
                    evidence=rel.get("evidence", ""),
                    metadata=rel.get("metadata")
                )
                if success:
                    stats["new_relations"] += 1
                    
        logger.info(f"Merge complete. Stats: {stats}")
        return stats

    def get_graph_statistics(self) -> Dict[str, Any]:
        """获取全局图谱统计信息"""
        return self.db.get_statistics()

if __name__ == "__main__":
    # 测试代码
    manager = GlobalGraphManager("data/graph_db/test_global.db")
    print("Initialized GlobalGraphManager")
    
    # 模拟一个mekg_data.json路径 (假设存在)
    # manager.merge_task_graph("outputs/xxx/mekg/mekg_data.json")