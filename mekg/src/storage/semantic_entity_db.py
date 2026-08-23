"""
语义实体数据库扩展 - SemanticEntityDB

扩展PersistentGraphDB以支持语义实体的存储和查询：
- 语义实体表（semantic_entities）
- 实体聚类表（entity_clusters）
- 引用上下文表（citation_contexts）
- 论文内关系表（intra_paper_relations）

这是对PersistentGraphDB的扩展，不修改原有代码
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime

from loguru import logger

from .persistent_graph_db import PersistentGraphDB
from mekg.src.extraction.semantic_entity_extractor import (
    SemanticEntity,
    SemanticEntityType,
    PaperSemanticEntities
)
from mekg.src.extraction.citation_context_analyzer import CitationRelation, CitationRelationType
from mekg.src.processing.entity_disambiguator import DisambiguationResult, EntityCluster


@dataclass
class SemanticEntityRecord:
    """语义实体记录"""
    id: int
    paper_id: str
    entity_type: str
    entity_value: str
    canonical_value: Optional[str]
    confidence: float
    source: str
    created_at: datetime


class SemanticEntityDB(PersistentGraphDB):
    """
    语义实体数据库
    
    扩展PersistentGraphDB以支持语义实体的存储和查询
    """
    
    # Schema版本
    SEMANTIC_SCHEMA_VERSION = 1
    
    def __init__(self, db_path: str = "data/graph_db/mekg_v3.db"):
        """
        初始化语义实体数据库
        
        Args:
            db_path: 数据库路径
        """
        super().__init__(db_path)
        
        # 初始化语义实体相关表
        self._init_semantic_tables()
        
        logger.info(f"语义实体数据库初始化完成: {db_path}")
    
    def _init_semantic_tables(self):
        """初始化语义实体相关表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 语义实体表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS semantic_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_value TEXT NOT NULL,
                    canonical_value TEXT,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'abstract',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
                )
            """)
            
            # 实体聚类表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entity_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    cluster_id INTEGER NOT NULL,
                    entity_value TEXT NOT NULL,
                    is_representative BOOLEAN DEFAULT FALSE,
                    frequency INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 引用上下文表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS citation_contexts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    citing_paper_id TEXT NOT NULL,
                    cited_paper_id TEXT NOT NULL,
                    context TEXT NOT NULL,
                    relation_type TEXT,
                    confidence REAL DEFAULT 0.0,
                    evidence TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(citing_paper_id, cited_paper_id),
                    FOREIGN KEY (citing_paper_id) REFERENCES papers(paper_id),
                    FOREIGN KEY (cited_paper_id) REFERENCES papers(paper_id)
                )
            """)
            
            # 论文内关系表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intra_paper_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_entities_paper 
                ON semantic_entities(paper_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_entities_type 
                ON semantic_entities(entity_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_entities_value 
                ON semantic_entities(entity_value)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_semantic_entities_canonical 
                ON semantic_entities(canonical_value)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_clusters_type 
                ON entity_clusters(entity_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_clusters_cluster 
                ON entity_clusters(entity_type, cluster_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_citation_contexts_citing 
                ON citation_contexts(citing_paper_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_citation_contexts_cited 
                ON citation_contexts(cited_paper_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_intra_relations_paper 
                ON intra_paper_relations(paper_id)
            """)
            
            # 更新papers表，添加语义实体标记
            try:
                cursor.execute("""
                    ALTER TABLE papers ADD COLUMN has_semantic_entities 
                    BOOLEAN DEFAULT FALSE
                """)
            except sqlite3.OperationalError:
                pass  # 列已存在
            
            try:
                cursor.execute("""
                    ALTER TABLE papers ADD COLUMN semantic_extraction_date 
                    TIMESTAMP
                """)
            except sqlite3.OperationalError:
                pass  # 列已存在
            
            logger.debug("语义实体表初始化完成")
    
    # ==================== 语义实体操作 ====================
    
    def add_semantic_entity(
        self,
        paper_id: str,
        entity_type: str,
        entity_value: str,
        confidence: float = 1.0,
        source: str = "abstract",
        canonical_value: str = None
    ) -> int:
        """
        添加语义实体
        
        Args:
            paper_id: 论文ID
            entity_type: 实体类型
            entity_value: 实体值
            confidence: 置信度
            source: 来源
            canonical_value: 标准化值
        
        Returns:
            实体ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO semantic_entities 
                (paper_id, entity_type, entity_value, confidence, source, canonical_value)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (paper_id, entity_type, entity_value, confidence, source, canonical_value))
            
            entity_id = cursor.lastrowid
            
            # 更新论文的语义实体标记
            cursor.execute("""
                UPDATE papers SET has_semantic_entities = TRUE,
                                  semantic_extraction_date = CURRENT_TIMESTAMP
                WHERE paper_id = ?
            """, (paper_id,))
            
            return entity_id
    
    def add_paper_semantic_entities(
        self,
        paper_id_or_entities,
        entities: List[SemanticEntity] = None
    ) -> int:
        """
        添加论文的所有语义实体
        
        支持两种调用方式:
        1. add_paper_semantic_entities(PaperSemanticEntities对象)
        2. add_paper_semantic_entities(paper_id, [SemanticEntity列表])
        
        Args:
            paper_id_or_entities: PaperSemanticEntities对象 或 论文ID
            entities: SemanticEntity列表（当第一个参数是paper_id时使用）
        
        Returns:
            添加的实体数量
        """
        # 判断调用方式
        if isinstance(paper_id_or_entities, PaperSemanticEntities):
            return self._add_paper_semantic_entities_from_object(paper_id_or_entities)
        else:
            return self._add_paper_semantic_entities_from_list(paper_id_or_entities, entities or [])
    
    def _add_paper_semantic_entities_from_object(
        self,
        entities: PaperSemanticEntities
    ) -> int:
        """从PaperSemanticEntities对象添加实体"""
        count = 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 添加各类实体
            all_entities = [
                (entities.problems, "problem"),
                (entities.methods, "method"),
                (entities.models, "model"),
                (entities.tasks, "task"),
                (entities.datasets, "dataset"),
                (entities.metrics, "metric"),
                (entities.innovations, "innovation"),
            ]
            
            for entity_list, entity_type in all_entities:
                for entity in entity_list:
                    cursor.execute("""
                        INSERT INTO semantic_entities
                        (paper_id, entity_type, entity_value, confidence, source, canonical_value)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        entities.paper_id,
                        entity_type,
                        entity.value,
                        entity.confidence,
                        entity.source,
                        entity.canonical_value
                    ))
                    count += 1
            
            # 更新论文标记
            if count > 0:
                cursor.execute("""
                    UPDATE papers SET has_semantic_entities = TRUE,
                                      semantic_extraction_date = CURRENT_TIMESTAMP
                    WHERE paper_id = ?
                """, (entities.paper_id,))
        
        logger.debug(f"添加论文 {entities.paper_id} 的 {count} 个语义实体")
        return count
    
    def _add_paper_semantic_entities_from_list(
        self,
        paper_id: str,
        entities: List[SemanticEntity]
    ) -> int:
        """从SemanticEntity列表添加实体"""
        count = 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for entity in entities:
                # 获取实体名称（兼容不同属性名）
                entity_value = getattr(entity, 'value', None) or getattr(entity, 'name', '')
                entity_type = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
                
                cursor.execute("""
                    INSERT INTO semantic_entities
                    (paper_id, entity_type, entity_value, confidence, source, canonical_value)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    paper_id,
                    entity_type,
                    entity_value,
                    getattr(entity, 'confidence', 1.0),
                    getattr(entity, 'source', 'abstract'),
                    getattr(entity, 'canonical_value', None)
                ))
                count += 1
            
            # 更新论文标记
            if count > 0:
                cursor.execute("""
                    UPDATE papers SET has_semantic_entities = TRUE,
                                      semantic_extraction_date = CURRENT_TIMESTAMP
                    WHERE paper_id = ?
                """, (paper_id,))
        
        logger.debug(f"添加论文 {paper_id} 的 {count} 个语义实体")
        return count
    
    def get_paper_semantic_entities(
        self,
        paper_id: str
    ) -> PaperSemanticEntities:
        """
        获取论文的语义实体
        
        Args:
            paper_id: 论文ID
        
        Returns:
            PaperSemanticEntities对象
        """
        paper = self.get_paper(paper_id)
        title = paper.get("title", "") if paper else ""
        
        result = PaperSemanticEntities(paper_id=paper_id, title=title)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT entity_type, entity_value, confidence, source, canonical_value
                FROM semantic_entities
                WHERE paper_id = ?
            """, (paper_id,))
            
            for row in cursor.fetchall():
                entity_type_str, value, confidence, source, canonical = row
                
                try:
                    entity_type = SemanticEntityType(entity_type_str)
                except ValueError:
                    continue
                
                entity = SemanticEntity(
                    entity_type=entity_type,
                    value=value,
                    confidence=confidence,
                    source=source,
                    canonical_value=canonical
                )
                
                if entity_type == SemanticEntityType.PROBLEM:
                    result.problems.append(entity)
                elif entity_type == SemanticEntityType.METHOD:
                    result.methods.append(entity)
                elif entity_type == SemanticEntityType.MODEL:
                    result.models.append(entity)
                elif entity_type == SemanticEntityType.TASK:
                    result.tasks.append(entity)
                elif entity_type == SemanticEntityType.DATASET:
                    result.datasets.append(entity)
                elif entity_type == SemanticEntityType.METRIC:
                    result.metrics.append(entity)
                elif entity_type == SemanticEntityType.INNOVATION:
                    result.innovations.append(entity)
        
        return result
    
    def get_entities_by_type(
        self,
        entity_type: str,
        limit: int = 1000
    ) -> List[Tuple[str, str, int]]:
        """
        获取指定类型的所有实体
        
        Args:
            entity_type: 实体类型
            limit: 返回数量限制
        
        Returns:
            [(entity_value, canonical_value, count), ...]
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT entity_value, canonical_value, COUNT(*) as cnt
                FROM semantic_entities
                WHERE entity_type = ?
                GROUP BY entity_value
                ORDER BY cnt DESC
                LIMIT ?
            """, (entity_type, limit))
            
            return [(row[0], row[1], row[2]) for row in cursor.fetchall()]
    
    def get_papers_by_entity(
        self,
        entity_type: str,
        entity_value: str,
        use_canonical: bool = True
    ) -> List[str]:
        """
        获取包含指定实体的论文
        
        Args:
            entity_type: 实体类型
            entity_value: 实体值
            use_canonical: 是否使用标准化值匹配
        
        Returns:
            论文ID列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if use_canonical:
                cursor.execute("""
                    SELECT DISTINCT paper_id FROM semantic_entities
                    WHERE entity_type = ? AND (
                        entity_value = ? OR canonical_value = ?
                    )
                """, (entity_type, entity_value, entity_value))
            else:
                cursor.execute("""
                    SELECT DISTINCT paper_id FROM semantic_entities
                    WHERE entity_type = ? AND entity_value = ?
                """, (entity_type, entity_value))
            
            return [row[0] for row in cursor.fetchall()]
    
    def get_all_semantic_entities(
        self,
        entity_type: str = None,
        limit: int = 10000
    ) -> List[Dict[str, Any]]:
        """
        获取所有语义实体
        
        Args:
            entity_type: 可选，筛选特定类型
            limit: 返回数量限制
        
        Returns:
            实体字典列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if entity_type:
                cursor.execute("""
                    SELECT id, paper_id, entity_type, entity_value,
                           canonical_value, confidence, source
                    FROM semantic_entities
                    WHERE entity_type = ?
                    LIMIT ?
                """, (entity_type, limit))
            else:
                cursor.execute("""
                    SELECT id, paper_id, entity_type, entity_value,
                           canonical_value, confidence, source
                    FROM semantic_entities
                    LIMIT ?
                """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "paper_id": row[1],
                    "entity_type": row[2],
                    "name": row[3],
                    "canonical_value": row[4],
                    "confidence": row[5],
                    "source": row[6]
                })
            
            return results
    
    def get_relations_between(
        self,
        paper1_id: str,
        paper2_id: str
    ) -> List[Dict[str, Any]]:
        """
        获取两篇论文之间的所有关系
        
        Args:
            paper1_id: 论文1 ID
            paper2_id: 论文2 ID
        
        Returns:
            关系字典列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT source_id, target_id, relation_type, confidence, evidence
                FROM relations
                WHERE (source_id = ? AND target_id = ?)
                   OR (source_id = ? AND target_id = ?)
            """, (paper1_id, paper2_id, paper2_id, paper1_id))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "source_id": row[0],
                    "target_id": row[1],
                    "relation_type": row[2],
                    "confidence": row[3],
                    "evidence": row[4]
                })
            
            return results
    
    def add_entity_cluster(
        self,
        entity_type: str,
        canonical_name: str,
        members: List[str]
    ) -> int:
        """
        添加实体聚类
        
        Args:
            entity_type: 实体类型
            canonical_name: 标准名称
            members: 聚类成员列表
        
        Returns:
            聚类ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取下一个聚类ID
            cursor.execute("""
                SELECT COALESCE(MAX(cluster_id), 0) + 1
                FROM entity_clusters
                WHERE entity_type = ?
            """, (entity_type,))
            cluster_id = cursor.fetchone()[0]
            
            # 添加聚类成员
            for member in members:
                is_representative = (member == canonical_name)
                cursor.execute("""
                    INSERT INTO entity_clusters
                    (entity_type, cluster_id, entity_value, is_representative, frequency)
                    VALUES (?, ?, ?, ?, 1)
                """, (entity_type, cluster_id, member, is_representative))
            
            # 更新语义实体表的canonical_value
            for member in members:
                cursor.execute("""
                    UPDATE semantic_entities
                    SET canonical_value = ?
                    WHERE entity_type = ? AND entity_value = ?
                """, (canonical_name, entity_type, member))
            
            return cluster_id
    
    def find_papers_with_shared_entities(
        self,
        paper_id: str,
        entity_types: List[str] = None
    ) -> List[Tuple[str, List[str], int]]:
        """
        找到与指定论文共享实体的论文
        
        Args:
            paper_id: 论文ID
            entity_types: 要检查的实体类型列表
        
        Returns:
            [(other_paper_id, shared_entities, count), ...]
        """
        if entity_types is None:
            entity_types = ["task", "dataset", "method", "model"]
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取当前论文的实体
            type_placeholders = ",".join(["?" for _ in entity_types])
            cursor.execute(f"""
                SELECT entity_type, COALESCE(canonical_value, entity_value) as value
                FROM semantic_entities
                WHERE paper_id = ? AND entity_type IN ({type_placeholders})
            """, [paper_id] + entity_types)
            
            my_entities = set((row[0], row[1]) for row in cursor.fetchall())
            
            if not my_entities:
                return []
            
            # 查找共享实体的论文
            results = {}
            
            for entity_type, entity_value in my_entities:
                cursor.execute("""
                    SELECT paper_id FROM semantic_entities
                    WHERE entity_type = ? AND (
                        entity_value = ? OR canonical_value = ?
                    ) AND paper_id != ?
                """, (entity_type, entity_value, entity_value, paper_id))
                
                for row in cursor.fetchall():
                    other_id = row[0]
                    if other_id not in results:
                        results[other_id] = []
                    results[other_id].append(f"{entity_type}:{entity_value}")
            
            # 排序并返回
            sorted_results = sorted(
                [(pid, entities, len(entities)) for pid, entities in results.items()],
                key=lambda x: -x[2]
            )
            
            return sorted_results
    
    # ==================== 实体聚类操作 ====================
    
    def save_disambiguation_result(
        self,
        result: DisambiguationResult
    ) -> int:
        """
        保存消歧结果
        
        Args:
            result: DisambiguationResult对象
        
        Returns:
            保存的聚类数量
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 清除旧的聚类数据
            cursor.execute("""
                DELETE FROM entity_clusters WHERE entity_type = ?
            """, (result.entity_type,))
            
            # 保存新的聚类
            for cluster in result.clusters:
                for entity in cluster.entities:
                    cursor.execute("""
                        INSERT INTO entity_clusters 
                        (entity_type, cluster_id, entity_value, is_representative, frequency)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        result.entity_type,
                        cluster.cluster_id,
                        entity,
                        entity == cluster.representative,
                        cluster.frequencies.get(entity, 1)
                    ))
            
            # 更新语义实体表的canonical_value
            for original, canonical in result.mapping.items():
                cursor.execute("""
                    UPDATE semantic_entities 
                    SET canonical_value = ?
                    WHERE entity_type = ? AND entity_value = ?
                """, (canonical, result.entity_type, original))
        
        logger.info(f"保存 {result.entity_type} 消歧结果: {len(result.clusters)} 个聚类")
        return len(result.clusters)
    
    def get_canonical_entity(
        self,
        entity_type: str,
        entity_value: str
    ) -> Optional[str]:
        """
        获取实体的标准化值
        
        Args:
            entity_type: 实体类型
            entity_value: 实体值
        
        Returns:
            标准化值，如果没有则返回None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT entity_value FROM entity_clusters
                WHERE entity_type = ? AND cluster_id = (
                    SELECT cluster_id FROM entity_clusters
                    WHERE entity_type = ? AND entity_value = ?
                ) AND is_representative = TRUE
            """, (entity_type, entity_type, entity_value))
            
            row = cursor.fetchone()
            return row[0] if row else None
    
    # ==================== 引用上下文操作 ====================
    
    def add_citation_context(
        self,
        relation: CitationRelation
    ) -> bool:
        """
        添加引用上下文
        
        Args:
            relation: CitationRelation对象
        
        Returns:
            是否成功添加
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    INSERT INTO citation_contexts 
                    (citing_paper_id, cited_paper_id, context, relation_type, confidence, evidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    relation.citing_paper_id,
                    relation.cited_paper_id,
                    relation.context,
                    relation.relation_type.value,
                    relation.confidence,
                    relation.evidence
                ))
                return True
            except sqlite3.IntegrityError:
                # 已存在，更新
                cursor.execute("""
                    UPDATE citation_contexts SET
                        context = ?,
                        relation_type = ?,
                        confidence = ?,
                        evidence = ?
                    WHERE citing_paper_id = ? AND cited_paper_id = ?
                """, (
                    relation.context,
                    relation.relation_type.value,
                    relation.confidence,
                    relation.evidence,
                    relation.citing_paper_id,
                    relation.cited_paper_id
                ))
                return True
    
    def get_citation_context(
        self,
        citing_id: str,
        cited_id: str
    ) -> Optional[CitationRelation]:
        """
        获取引用上下文
        
        Args:
            citing_id: 引用论文ID
            cited_id: 被引论文ID
        
        Returns:
            CitationRelation对象
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT context, relation_type, confidence, evidence
                FROM citation_contexts
                WHERE citing_paper_id = ? AND cited_paper_id = ?
            """, (citing_id, cited_id))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            try:
                rel_type = CitationRelationType(row[1])
            except ValueError:
                rel_type = CitationRelationType.UNKNOWN
            
            return CitationRelation(
                citing_paper_id=citing_id,
                cited_paper_id=cited_id,
                relation_type=rel_type,
                confidence=row[2],
                context=row[0],
                evidence=row[3] or ""
            )
    
    def get_citation_contexts_for_paper(
        self,
        paper_id: str,
        direction: str = "both"
    ) -> List[CitationRelation]:
        """
        获取论文的所有引用上下文
        
        Args:
            paper_id: 论文ID
            direction: "citing"(引用了谁), "cited"(被谁引用), "both"
        
        Returns:
            CitationRelation列表
        """
        results = []
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if direction in ["citing", "both"]:
                cursor.execute("""
                    SELECT citing_paper_id, cited_paper_id, context, 
                           relation_type, confidence, evidence
                    FROM citation_contexts
                    WHERE citing_paper_id = ?
                """, (paper_id,))
                
                for row in cursor.fetchall():
                    try:
                        rel_type = CitationRelationType(row[3])
                    except ValueError:
                        rel_type = CitationRelationType.UNKNOWN
                    
                    results.append(CitationRelation(
                        citing_paper_id=row[0],
                        cited_paper_id=row[1],
                        relation_type=rel_type,
                        confidence=row[4],
                        context=row[2],
                        evidence=row[5] or ""
                    ))
            
            if direction in ["cited", "both"]:
                cursor.execute("""
                    SELECT citing_paper_id, cited_paper_id, context, 
                           relation_type, confidence, evidence
                    FROM citation_contexts
                    WHERE cited_paper_id = ?
                """, (paper_id,))
                
                for row in cursor.fetchall():
                    try:
                        rel_type = CitationRelationType(row[3])
                    except ValueError:
                        rel_type = CitationRelationType.UNKNOWN
                    
                    results.append(CitationRelation(
                        citing_paper_id=row[0],
                        cited_paper_id=row[1],
                        relation_type=rel_type,
                        confidence=row[4],
                        context=row[2],
                        evidence=row[5] or ""
                    ))
        
        return results
    
    # ==================== 统计信息扩展 ====================
    
    def get_semantic_statistics(self) -> Dict[str, Any]:
        """获取语义实体统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 语义实体总数
            cursor.execute("SELECT COUNT(*) FROM semantic_entities")
            entity_count = cursor.fetchone()[0]
            
            # 按类型统计
            cursor.execute("""
                SELECT entity_type, COUNT(*) 
                FROM semantic_entities 
                GROUP BY entity_type
            """)
            entity_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 有语义实体的论文数
            cursor.execute("""
                SELECT COUNT(*) FROM papers WHERE has_semantic_entities = TRUE
            """)
            papers_with_entities = cursor.fetchone()[0]
            
            # 聚类数
            cursor.execute("""
                SELECT entity_type, COUNT(DISTINCT cluster_id) 
                FROM entity_clusters 
                GROUP BY entity_type
            """)
            clusters_by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 引用上下文数
            cursor.execute("SELECT COUNT(*) FROM citation_contexts")
            citation_context_count = cursor.fetchone()[0]
            
            # 引用关系类型分布
            cursor.execute("""
                SELECT relation_type, COUNT(*) 
                FROM citation_contexts 
                GROUP BY relation_type
            """)
            citation_relations = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            "semantic_entity_count": entity_count,
            "entity_by_type": entity_by_type,
            "papers_with_entities": papers_with_entities,
            "clusters_by_type": clusters_by_type,
            "citation_context_count": citation_context_count,
            "citation_relation_types": citation_relations
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取完整统计信息（包含语义实体）"""
        # 获取基础统计
        base_stats = super().get_statistics()
        
        # 添加语义实体统计
        semantic_stats = self.get_semantic_statistics()
        base_stats["semantic"] = semantic_stats
        
        return base_stats


# 便捷函数
def get_semantic_db() -> SemanticEntityDB:
    """获取默认语义实体数据库实例"""
    return SemanticEntityDB("data/graph_db/mekg_v3.db")


if __name__ == "__main__":
    # 测试
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_semantic.db")
        db = SemanticEntityDB(db_path)
        
        # 添加测试论文
        paper = {
            "paper_id": "W001",
            "title": "BERT: Pre-training of Deep Bidirectional Transformers",
            "abstract": "We introduce BERT...",
            "year": 2018
        }
        db.add_paper(paper)
        
        # 添加语义实体
        entities = PaperSemanticEntities(
            paper_id="W001",
            title=paper["title"],
            problems=[SemanticEntity(
                entity_type=SemanticEntityType.PROBLEM,
                value="Language understanding requires bidirectional context"
            )],
            methods=[SemanticEntity(
                entity_type=SemanticEntityType.METHOD,
                value="Masked language modeling with bidirectional transformers"
            )],
            models=[SemanticEntity(
                entity_type=SemanticEntityType.MODEL,
                value="BERT"
            )],
            tasks=[
                SemanticEntity(entity_type=SemanticEntityType.TASK, value="question answering"),
                SemanticEntity(entity_type=SemanticEntityType.TASK, value="language inference")
            ],
            datasets=[
                SemanticEntity(entity_type=SemanticEntityType.DATASET, value="SQuAD"),
                SemanticEntity(entity_type=SemanticEntityType.DATASET, value="GLUE")
            ],
            metrics=[
                SemanticEntity(entity_type=SemanticEntityType.METRIC, value="F1-score"),
                SemanticEntity(entity_type=SemanticEntityType.METRIC, value="accuracy")
            ]
        )
        
        count = db.add_paper_semantic_entities(entities)
        print(f"添加了 {count} 个语义实体")
        
        # 查询语义实体
        retrieved = db.get_paper_semantic_entities("W001")
        print(f"检索到的实体: {retrieved.entity_count()}")
        print(f"  Tasks: {[t.value for t in retrieved.tasks]}")
        print(f"  Datasets: {[d.value for d in retrieved.datasets]}")
        
        # 获取统计信息
        stats = db.get_statistics()
        print(f"\n统计信息:")
        print(f"  论文数: {stats['paper_count']}")
        print(f"  语义实体数: {stats['semantic']['semantic_entity_count']}")
        print(f"  按类型: {stats['semantic']['entity_by_type']}")
        
        print("\n测试通过!")