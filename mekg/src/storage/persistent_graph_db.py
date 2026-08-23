"""
Persistent Graph Database
=========================

基于SQLite的持久化图数据库，用于存储论文、引用关系和图谱结构。
"""

import sqlite3
import json
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
from dataclasses import dataclass
from loguru import logger

class PersistentGraphDB:
    """持久化图数据库 (SQLite实现)"""
    
    def __init__(self, db_path: str = "data/graph_db/mekg.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 论文表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    paper_id TEXT PRIMARY KEY,
                    title TEXT,
                    abstract TEXT,
                    year INTEGER,
                    citations INTEGER,
                    authors TEXT,  -- JSON list
                    attributes TEXT, -- JSON dict
                    semantic_entities TEXT, -- JSON dict
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 引用关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS citations (
                    source_id TEXT,
                    target_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_id, target_id),
                    FOREIGN KEY (source_id) REFERENCES papers(paper_id),
                    FOREIGN KEY (target_id) REFERENCES papers(paper_id)
                )
            """)
            
            # 语义关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    source_id TEXT,
                    target_id TEXT,
                    relation_type TEXT,
                    confidence REAL,
                    evidence TEXT,
                    metadata TEXT, -- JSON dict
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source_id, target_id, relation_type),
                    FOREIGN KEY (source_id) REFERENCES papers(paper_id),
                    FOREIGN KEY (target_id) REFERENCES papers(paper_id)
                )
            """)
            
            # Topic关联表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS topic_papers (
                    topic TEXT,
                    paper_id TEXT,
                    relevance REAL,
                    is_core BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (topic, paper_id),
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
                )
            """)
            
            conn.commit()
    
    def add_paper(self, paper: Dict[str, Any]) -> bool:
        """添加论文"""
        paper_id = paper.get("paper_id") or paper.get("id")
        if not paper_id:
            return False
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO papers 
                    (paper_id, title, abstract, year, citations, authors, attributes, semantic_entities)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    paper_id,
                    paper.get("title", ""),
                    paper.get("abstract", ""),
                    paper.get("year"),
                    paper.get("citations", 0),
                    json.dumps(paper.get("authors", [])),
                    json.dumps(paper.get("attributes", {})),
                    json.dumps(paper.get("semantic_entities", {}))
                ))
                return True
        except Exception as e:
            logger.error(f"Failed to add paper {paper_id}: {e}")
            return False

    def get_paper(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """获取论文"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "paper_id": row[0],
                        "title": row[1],
                        "abstract": row[2],
                        "year": row[3],
                        "citations": row[4],
                        "authors": json.loads(row[5]) if row[5] else [],
                        "attributes": json.loads(row[6]) if row[6] else {},
                        "semantic_entities": json.loads(row[7]) if row[7] else {}
                    }
        except Exception as e:
            logger.error(f"Failed to get paper {paper_id}: {e}")
        return None

    def paper_exists(self, paper_id: str) -> bool:
        """检查论文是否存在"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,))
                return cursor.fetchone() is not None
        except Exception:
            return False

    def add_citation(self, source_id: str, target_id: str) -> bool:
        """添加引用关系"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO citations (source_id, target_id)
                    VALUES (?, ?)
                """, (source_id, target_id))
                return True
        except Exception as e:
            logger.error(f"Failed to add citation {source_id}->{target_id}: {e}")
            return False

    def get_citations(self, paper_id: str, direction: str = "citing") -> List[str]:
        """获取引用关系"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if direction == "citing":
                    # paper_id 引用的论文
                    cursor.execute("SELECT target_id FROM citations WHERE source_id = ?", (paper_id,))
                else:
                    # 引用 paper_id 的论文
                    cursor.execute("SELECT source_id FROM citations WHERE target_id = ?", (paper_id,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get citations for {paper_id}: {e}")
            return []

    def add_relation(self, source_id: str, target_id: str, relation_type: str, 
                    confidence: float, evidence: str = "", metadata: Dict = None) -> bool:
        """添加语义关系"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO relations 
                    (source_id, target_id, relation_type, confidence, evidence, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    source_id, target_id, relation_type, confidence, evidence,
                    json.dumps(metadata or {})
                ))
                return True
        except Exception as e:
            logger.error(f"Failed to add relation {source_id}->{target_id}: {e}")
            return False

    def get_relations(self, paper_id: str) -> List[Dict]:
        """获取与论文相关的所有关系"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT source_id, target_id, relation_type, confidence, evidence, metadata 
                    FROM relations 
                    WHERE source_id = ? OR target_id = ?
                """, (paper_id, paper_id))
                
                relations = []
                for row in cursor.fetchall():
                    relations.append({
                        "source": row[0],
                        "target": row[1],
                        "type": row[2],
                        "confidence": row[3],
                        "evidence": row[4],
                        "metadata": json.loads(row[5]) if row[5] else {}
                    })
                return relations
        except Exception as e:
            logger.error(f"Failed to get relations for {paper_id}: {e}")
            return []

    def link_paper_to_topic(self, paper_id: str, topic: str, relevance: float = 1.0, is_core: bool = False):
        """关联论文到Topic"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO topic_papers (topic, paper_id, relevance, is_core)
                    VALUES (?, ?, ?, ?)
                """, (topic, paper_id, relevance, is_core))
        except Exception as e:
            logger.error(f"Failed to link paper {paper_id} to topic {topic}: {e}")

    def get_topic_papers(self, topic: str) -> List[str]:
        """获取Topic下的所有论文ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT paper_id FROM topic_papers WHERE topic = ?", (topic,))
                return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def get_neighbors(self, paper_id: str) -> List[str]:
        """获取论文的邻居（引用和被引）"""
        citing = self.get_citations(paper_id, "citing")
        cited_by = self.get_citations(paper_id, "cited_by")
        return list(set(citing + cited_by))

    def get_statistics(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                stats = {}
                cursor.execute("SELECT COUNT(*) FROM papers")
                stats["papers"] = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM citations")
                stats["citations"] = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM relations")
                stats["relations"] = cursor.fetchone()[0]
                return stats
        except Exception:
            return {}

# 辅助函数
def get_default_db() -> PersistentGraphDB:
    return PersistentGraphDB()

@dataclass
class SubGraph:
    """子图结构"""
    nodes: List[str]
    edges: List[Dict]