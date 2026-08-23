"""
KuzuDB Graph Storage Implementation
替代原有的 SQLite + NetworkX 方案，提供统一的图存储与计算能力。
"""

import kuzu
import shutil
import os
import json
import igraph as ig
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from loguru import logger

class KuzuGraphDB:
    def __init__(self, db_path: str = "data/kuzu_db", read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only
        
        # 确保父目录存在
        dirname = os.path.dirname(self.db_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
            
        # 初始化 Schema (只在第一次运行时需要，且非只读模式)
        if not self.read_only:
            self._init_schema()
        
    def _get_conn(self):
        """获取数据库连接 (短连接模式)"""
        # 每次调用都重新打开，用完即毁，以释放文件锁
        db = kuzu.Database(self.db_path)
        conn = kuzu.Connection(db)
        return db, conn

    def _init_schema(self):
        """初始化 Schema"""
        try:
            db, conn = self._get_conn()
            self._create_tables(conn)
            # 显式关闭
            del conn
            del db
        except Exception as e:
            logger.error(f"Schema init failed: {e}")

    def _create_tables(self, conn):
        """创建节点和关系表"""
        try:
            # 1. Paper 节点
            conn.execute("""
                CREATE NODE TABLE IF NOT EXISTS Paper (
                    id STRING,
                    title STRING,
                    abstract STRING,
                    year INT64,
                    citations INT64,
                    venue STRING,
                    authors STRING,
                    doi STRING,
                    pdf_url STRING,
                    method_info STRUCT(name STRING, description STRING),
                    innovations STRING[],
                    limitations STRING[],
                    research_domains STRING[],
                    is_survey BOOLEAN,
                    community_id INT64,
                    created_at TIMESTAMP,
                    PRIMARY KEY (id)
                )
            """)
            
            # 2. Topic 节点
            conn.execute("""
                CREATE NODE TABLE IF NOT EXISTS Topic (
                    name STRING,
                    last_updated TIMESTAMP,
                    PRIMARY KEY (name)
                )
            """)
            
            # 3. SemanticEntity 节点
            conn.execute("""
                CREATE NODE TABLE IF NOT EXISTS SemanticEntity (
                    id STRING,
                    name STRING,
                    type STRING,
                    PRIMARY KEY (id)
                )
            """)
            
            # 4. 关系表
            conn.execute("CREATE REL TABLE IF NOT EXISTS CITES (FROM Paper TO Paper)")
            conn.execute("""
                CREATE REL TABLE IF NOT EXISTS BELONGS_TO (
                    FROM Paper TO Topic,
                    relevance_score DOUBLE
                )
            """)
            conn.execute("CREATE REL TABLE IF NOT EXISTS PROPOSES (FROM Paper TO SemanticEntity)")
            conn.execute("CREATE REL TABLE IF NOT EXISTS SOLVES (FROM Paper TO SemanticEntity)")
            conn.execute("CREATE REL TABLE IF NOT EXISTS USES (FROM Paper TO SemanticEntity)")
            
        except Exception as e:
            logger.error(f"Table creation failed: {e}")

    def add_paper(self, paper_data: Dict[str, Any]):
        """添加论文节点"""
        db, conn = self._get_conn()
        try:
            # 准备数据
            paper_id = paper_data.get('paper_id') or paper_data.get('id')
            if not paper_id:
                return False
                
            # 处理 STRUCT
            method_info = paper_data.get('method_info', {})
            if not isinstance(method_info, dict): method_info = {'name': '', 'description': ''}
            if 'name' not in method_info: method_info['name'] = ''
            if 'description' not in method_info: method_info['description'] = ''
            
            # 处理 LISTs
            innovations = paper_data.get('innovations', []) if isinstance(paper_data.get('innovations'), list) else []
            limitations = paper_data.get('limitations', []) if isinstance(paper_data.get('limitations'), list) else []
            domains = paper_data.get('research_domains', []) if isinstance(paper_data.get('research_domains'), list) else []
            
            # 检查是否存在
            if self._node_exists(conn, "Paper", paper_id):
                return True
            
            cypher = """
            CREATE (p:Paper {
                id: $id,
                title: $title,
                abstract: $abstract,
                year: $year,
                citations: $citations,
                venue: $venue,
                authors: $authors,
                doi: $doi,
                pdf_url: $pdf_url,
                method_info: $method_info,
                innovations: $innovations,
                limitations: $limitations,
                research_domains: $domains,
                is_survey: $is_survey,
                created_at: timestamp($created_at)
            })
            """
            
            params = {
                "id": paper_id,
                "title": paper_data.get('title', ''),
                "abstract": paper_data.get('abstract', ''),
                "year": int(paper_data.get('year', 0)),
                "citations": int(paper_data.get('citations', 0)),
                "venue": paper_data.get('venue', ''),
                "authors": str(paper_data.get('authors', '')),
                "doi": paper_data.get('doi', ''),
                "pdf_url": paper_data.get('pdf_url', ''),
                "method_info": method_info,
                "innovations": innovations,
                "limitations": limitations,
                "domains": domains,
                "is_survey": bool(paper_data.get('is_survey', False)),
                "created_at": datetime.now().isoformat()
            }
            
            conn.execute(cypher, params)
            return True
        except Exception as e:
            logger.error(f"Failed to add paper: {e}")
            return False
        finally:
            del conn
            del db

    def add_topic(self, topic_name: str):
        """添加或更新 Topic"""
        db, conn = self._get_conn()
        try:
            if self._node_exists(conn, "Topic", topic_name):
                conn.execute(
                    "MATCH (t:Topic {name: $name}) SET t.last_updated = timestamp($time)",
                    {"name": topic_name, "time": datetime.now().isoformat()}
                )
            else:
                conn.execute(
                    "CREATE (t:Topic {name: $name, last_updated: timestamp($time)})",
                    {"name": topic_name, "time": datetime.now().isoformat()}
                )
            return True
        except Exception as e:
            logger.error(f"Failed to add topic: {e}")
            return False
        finally:
            del conn
            del db

    def link_paper_to_topic(self, paper_id: str, topic_name: str, score: float = 1.0):
        """建立 Paper -> Topic 关系"""
        db, conn = self._get_conn()
        try:
            if not self._node_exists(conn, "Paper", paper_id) or not self._node_exists(conn, "Topic", topic_name):
                return False
                
            result = conn.execute(
                "MATCH (p:Paper {id: $pid})-[r:BELONGS_TO]->(t:Topic {name: $topic}) RETURN count(*)",
                {"pid": paper_id, "topic": topic_name}
            )
            if result.get_next()[0] > 0:
                return True
                
            conn.execute(
                "MATCH (p:Paper {id: $pid}), (t:Topic {name: $topic}) CREATE (p)-[:BELONGS_TO {relevance_score: $score}]->(t)",
                {"pid": paper_id, "topic": topic_name, "score": score}
            )
            return True
        except Exception as e:
            logger.error(f"Link failed: {e}")
            return False
        finally:
            del conn
            del db

    def add_citation(self, source_id: str, target_id: str):
        """添加引用关系"""
        db, conn = self._get_conn()
        try:
            if not self._node_exists(conn, "Paper", source_id) or not self._node_exists(conn, "Paper", target_id):
                return False
                
            check_cypher = "MATCH (a:Paper {id: $src})-[r:CITES]->(b:Paper {id: $tgt}) RETURN count(*)"
            if conn.execute(check_cypher, {"src": source_id, "tgt": target_id}).get_next()[0] > 0:
                return True
                
            create_cypher = "MATCH (a:Paper {id: $src}), (b:Paper {id: $tgt}) CREATE (a)-[:CITES]->(b)"
            conn.execute(create_cypher, {"src": source_id, "tgt": target_id})
            return True
        except Exception as e:
            return False
        finally:
            del conn
            del db

    def get_topic_status(self, topic_name: str) -> Dict[str, Any]:
        """获取 Topic 状态"""
        db, conn = self._get_conn()
        status = {
            'exists': False,
            'paper_count': 0,
            'last_updated': None,
            'needs_update': True
        }
        
        try:
            result = conn.execute(
                "MATCH (t:Topic {name: $name}) RETURN t.last_updated",
                {"name": topic_name}
            )
            
            if result.has_next():
                status['exists'] = True
                row = result.get_next()
                status['last_updated'] = row[0]
                
                count_result = conn.execute(
                    "MATCH (p:Paper)-[:BELONGS_TO]->(t:Topic {name: $name}) RETURN count(p)",
                    {"name": topic_name}
                )
                if count_result.has_next():
                    status['paper_count'] = count_result.get_next()[0]
                
                if status['paper_count'] > 10:
                    status['needs_update'] = False
                    
        except Exception as e:
            logger.error(f"Error checking status: {e}")
        finally:
            del conn
            del db
            
        return status

    def detect_communities(self) -> Dict[int, List[str]]:
        """
        运行社区发现算法 (Leiden)
        
        Returns:
            {community_id: [paper_id_list]}
        """
        db, conn = self._get_conn()
        try:
            logger.info("Starting community detection...")
            
            # 1. 导出图结构 (Paper -> Paper 引用关系)
            # 获取所有 Paper 节点 ID
            paper_result = conn.execute("MATCH (p:Paper) RETURN p.id")
            paper_ids = []
            while paper_result.has_next():
                paper_ids.append(paper_result.get_next()[0])
                
            if not paper_ids:
                return {}
                
            # 建立 ID 到 索引 的映射
            id_to_idx = {pid: i for i, pid in enumerate(paper_ids)}
            idx_to_id = {i: pid for pid, i in id_to_idx.items()}
            
            # 获取边 (CITES)
            edge_result = conn.execute("MATCH (a:Paper)-[r:CITES]->(b:Paper) RETURN a.id, b.id")
            edges = []
            while edge_result.has_next():
                src, dst = edge_result.get_next()
                if src in id_to_idx and dst in id_to_idx:
                    edges.append((id_to_idx[src], id_to_idx[dst]))
            
            logger.info(f"Graph loaded: {len(paper_ids)} nodes, {len(edges)} edges")
            
            if not edges:
                # 没有边，每个点自成一社区
                return {i: [pid] for i, pid in enumerate(paper_ids)}

            # 2. 构建 igraph 对象
            g = ig.Graph(len(paper_ids), edges)
            
            # 3. 运行 Leiden 算法
            # 使用 modularity 优化
            partition = g.community_leiden(objective_function='modularity')
            
            # 4. 更新数据库
            # 批量更新比较慢，这里逐个更新
            # Kuzu 支持 UPDATE
            communities = {}
            for idx, comm_id in enumerate(partition.membership):
                paper_id = idx_to_id[idx]
                
                # 记录结果
                if comm_id not in communities:
                    communities[comm_id] = []
                communities[comm_id].append(paper_id)
                
                # 更新 DB
                conn.execute(
                    "MATCH (p:Paper {id: $id}) SET p.community_id = $comm",
                    {"id": paper_id, "comm": comm_id}
                )
                
            logger.info(f"Detected {len(communities)} communities")
            return communities
            
        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            return {}
        finally:
            del conn
            del db

    def _node_exists(self, conn, label: str, key_val: str) -> bool:
        """检查节点是否存在 (需要传入 conn)"""
        key_field = "name" if label == "Topic" else "id"
        query = f"MATCH (n:{label} {{{key_field}: $val}}) RETURN count(*)"
        result = conn.execute(query, {"val": key_val})
        return result.get_next()[0] > 0

    def close(self):
        pass