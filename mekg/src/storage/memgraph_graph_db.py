"""
Memgraph Graph Storage Implementation
替代 KuzuDB，提供支持并发访问的图存储能力。

Memgraph 是一个高性能的图数据库，支持：
- 多客户端并发读写
- Cypher 查询语言
- 原生 mgclient 驱动（推荐）或 Neo4j Bolt 协议兼容
"""

import os
import json
import igraph as ig
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from loguru import logger

# 优先使用 mgclient（Memgraph 原生驱动）
try:
    import mgclient
    MGCLIENT_AVAILABLE = True
except ImportError:
    MGCLIENT_AVAILABLE = False
    logger.warning("mgclient not installed. Run: pip install pymgclient")

# 备用：neo4j 驱动（可能有兼容性问题）
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


class MemgraphGraphDB:
    """
    Memgraph 图数据库存储层
    
    优先使用 mgclient（Memgraph 原生 C 驱动），性能更好且兼容性更强。
    如果 mgclient 不可用，则回退到 neo4j 驱动。
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None,
        read_only: bool = False,
        use_mgclient: bool = True  # 优先使用 mgclient
    ):
        """
        初始化 Memgraph 连接
        
        Args:
            host: Memgraph 主机地址，默认从环境变量 MEMGRAPH_HOST 读取，或使用 127.0.0.1
            port: Memgraph 端口，默认从环境变量 MEMGRAPH_PORT 读取，或使用 7687
            user: 用户名，默认从环境变量 MEMGRAPH_USER 读取
            password: 密码，默认从环境变量 MEMGRAPH_PASSWORD 读取
            database: 数据库名（Memgraph 通常不需要）
            read_only: 是否只读模式
            use_mgclient: 是否优先使用 mgclient 驱动
        """
        self.host = host or os.getenv("MEMGRAPH_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("MEMGRAPH_PORT", "7687"))
        self.user = user or os.getenv("MEMGRAPH_USER", "")
        self.password = password or os.getenv("MEMGRAPH_PASSWORD", "")
        self.database = database
        self.read_only = read_only
        
        # 选择驱动
        self._use_mgclient = use_mgclient and MGCLIENT_AVAILABLE
        self._conn = None  # mgclient 连接
        self._driver = None  # neo4j 驱动
        self._connected_once = False  # 标记是否已经连接过（用于控制日志输出）
        
        if self._use_mgclient:
            self._init_mgclient()
        elif NEO4J_AVAILABLE:
            self._init_neo4j()
        else:
            raise ImportError(
                "No Memgraph driver available. Install one of:\n"
                "  pip install pymgclient  (recommended)\n"
                "  pip install neo4j"
            )
        
        # 初始化 Schema（创建索引）
        if not self.read_only:
            self._init_schema()
    
    def _init_mgclient(self, silent: bool = False):
        """使用 mgclient 初始化连接
        
        Args:
            silent: 是否静默模式（重连时不输出日志）
        """
        try:
            # mgclient 连接参数
            connect_params = {
                'host': self.host,
                'port': self.port,
                'lazy': False,  # 立即连接
            }
            
            # 添加认证（如果有）
            if self.user:
                connect_params['username'] = self.user
            if self.password:
                connect_params['password'] = self.password
            
            self._conn = mgclient.connect(**connect_params)
            self._conn.autocommit = True  # 自动提交
            
            # 验证连接
            cursor = self._conn.cursor()
            cursor.execute("RETURN 1 AS test")
            cursor.fetchall()
            
            # 只在首次连接时输出 INFO 日志，重连时使用 DEBUG
            if not self._connected_once:
                logger.info(f"Connected to Memgraph at {self.host}:{self.port} (using mgclient)")
                self._connected_once = True
            elif not silent:
                logger.debug(f"Reconnected to Memgraph at {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Memgraph with mgclient: {e}")
            raise
    
    def _init_neo4j(self):
        """使用 neo4j 驱动初始化连接（备用）"""
        uri = f"bolt://{self.host}:{self.port}"
        auth = (self.user, self.password) if self.user else None
        
        try:
            self._driver = GraphDatabase.driver(uri, auth=auth)
            self._driver.verify_connectivity()
            logger.info(f"Connected to Memgraph at {uri} (using neo4j driver)")
        except Exception as e:
            logger.error(f"Failed to connect to Memgraph with neo4j driver: {e}")
            raise
    
    def _execute(self, cypher: str, params: Dict[str, Any] = None) -> List[Dict]:
        """
        执行 Cypher 查询并返回结果
        
        Args:
            cypher: Cypher 查询语句
            params: 查询参数
            
        Returns:
            查询结果列表
        """
        params = params or {}
        
        if self._use_mgclient:
            return self._execute_mgclient(cypher, params)
        else:
            return self._execute_neo4j(cypher, params)
    
    def _execute_mgclient(self, cypher: str, params: Dict[str, Any]) -> List[Dict]:
        """使用 mgclient 执行查询"""
        results = []
        max_retries = 1
        
        for attempt in range(max_retries + 1):
            try:
                # 检查连接状态，如果需要则重连（静默模式，不输出日志）
                if self._conn is None or self._conn.status == 0: # 0 = MG_CONNECTION_CLOSED
                     try:
                         self._init_mgclient(silent=True)
                     except Exception as e:
                         logger.error(f"Reconnection failed: {e}")
                         if attempt == max_retries:
                             raise

                cursor = self._conn.cursor()
                
                # mgclient 使用 $name 格式的参数
                if params:
                    cursor.execute(cypher, params)
                else:
                    cursor.execute(cypher)
                
                # 获取列名 - mgclient.Column 对象使用 .name 属性
                if cursor.description:
                    columns = [col.name for col in cursor.description]
                    for row in cursor.fetchall():
                        # 将 mgclient 的 Node/Relationship 转换为字典
                        record = {}
                        for i, col in enumerate(columns):
                            value = row[i]
                            if isinstance(value, mgclient.Node):
                                # 转换节点为字典
                                record[col] = dict(value.properties)
                                record[col]['_labels'] = list(value.labels)
                            elif isinstance(value, mgclient.Relationship):
                                # 转换关系为字典
                                record[col] = dict(value.properties)
                                record[col]['_type'] = value.type
                            else:
                                record[col] = value
                        results.append(record)
                
                # 成功执行，跳出重试循环
                break
                        
            except Exception as e:
                # 检查是否是连接错误
                is_conn_error = "bad session" in str(e).lower() or "connection" in str(e).lower() or "closed" in str(e).lower()
                
                if is_conn_error and attempt < max_retries:
                    logger.warning(f"Connection error detected ({e}), retrying... ({attempt + 1}/{max_retries})")
                    # 强制重置连接
                    try:
                        if self._conn:
                            self._conn.close()
                    except:
                        pass
                    self._conn = None
                    continue
                
                logger.error(f"mgclient query failed: {e}\nQuery: {cypher}")
                raise
            
        return results
    
    def _execute_neo4j(self, cypher: str, params: Dict[str, Any]) -> List[Dict]:
        """使用 neo4j 驱动执行查询"""
        results = []
        try:
            with self._driver.session(database=self.database) as session:
                result = session.run(cypher, params)
                for record in result:
                    results.append(dict(record))
        except Exception as e:
            logger.error(f"neo4j query failed: {e}\nQuery: {cypher}")
            raise
        return results
    
    def _execute_write(self, cypher: str, params: Dict[str, Any] = None) -> bool:
        """执行写入操作"""
        try:
            self._execute(cypher, params)
            return True
        except Exception as e:
            logger.error(f"Write operation failed: {e}")
            return False
    
    def _init_schema(self):
        """初始化 Schema（创建索引）"""
        indices = [
            "CREATE INDEX ON :Paper(id)",
            "CREATE INDEX ON :Topic(name)",
            "CREATE INDEX ON :SemanticEntity(id)",
        ]
        
        for idx in indices:
            try:
                self._execute(idx)
            except Exception as e:
                # 索引可能已存在
                if "already exists" not in str(e).lower():
                    logger.debug(f"Index creation note: {e}")
        
        logger.info("Memgraph schema initialized")
    
    def add_paper(self, paper_data: Dict[str, Any]) -> bool:
        """添加论文节点"""
        try:
            paper_id = paper_data.get('paper_id') or paper_data.get('id')
            if not paper_id:
                return False
            
            # 处理 method_info
            method_info = paper_data.get('method_info', {})
            if not isinstance(method_info, dict):
                method_info = {'name': '', 'description': ''}
            method_info_json = json.dumps(method_info, ensure_ascii=False)
            
            # 处理列表字段 - 转换为 JSON 字符串（mgclient 对列表支持有限）
            innovations = paper_data.get('innovations', [])
            if not isinstance(innovations, list):
                innovations = []
            innovations_json = json.dumps(innovations, ensure_ascii=False)
            
            limitations = paper_data.get('limitations', [])
            if not isinstance(limitations, list):
                limitations = []
            limitations_json = json.dumps(limitations, ensure_ascii=False)
            
            domains = paper_data.get('research_domains', [])
            if not isinstance(domains, list):
                domains = []
            domains_json = json.dumps(domains, ensure_ascii=False)
            
            cypher = """
            MERGE (p:Paper {id: $id})
            SET p.title = $title,
                p.abstract = $abstract,
                p.year = $year,
                p.citations = $citations,
                p.venue = $venue,
                p.authors = $authors,
                p.doi = $doi,
                p.pdf_url = $pdf_url,
                p.method_info = $method_info,
                p.innovations = $innovations,
                p.limitations = $limitations,
                p.research_domains = $domains,
                p.is_survey = $is_survey,
                p.created_at = $created_at
            RETURN p
            """
            
            self._execute(cypher, {
                "id": paper_id,
                "title": paper_data.get('title', ''),
                "abstract": paper_data.get('abstract', ''),
                "year": int(paper_data.get('year', 0)),
                "citations": int(paper_data.get('citations', 0)),
                "venue": paper_data.get('venue', ''),
                "authors": str(paper_data.get('authors', '')),
                "doi": paper_data.get('doi', ''),
                "pdf_url": paper_data.get('pdf_url', ''),
                "method_info": method_info_json,
                "innovations": innovations_json,
                "limitations": limitations_json,
                "domains": domains_json,
                "is_survey": paper_data.get('is_survey', False),
                "created_at": datetime.now().isoformat()
            })
            
            return True
        except Exception as e:
            logger.error(f"Failed to add paper: {e}")
            return False
    
    def add_topic(self, topic_name: str) -> bool:
        """添加或更新 Topic"""
        cypher = """
        MERGE (t:Topic {name: $name})
        SET t.last_updated = $time
        RETURN t
        """
        return self._execute_write(cypher, {
            "name": topic_name,
            "time": datetime.now().isoformat()
        })
    
    def link_paper_to_topic(self, paper_id: str, topic_name: str, score: float = 1.0) -> bool:
        """建立 Paper -> Topic 关系"""
        cypher = """
        MATCH (p:Paper {id: $pid}), (t:Topic {name: $topic})
        MERGE (p)-[r:BELONGS_TO]->(t)
        SET r.relevance_score = $score
        RETURN r
        """
        results = self._execute(cypher, {
            "pid": paper_id,
            "topic": topic_name,
            "score": score
        })
        return len(results) > 0
    
    def add_citation(self, source_id: str, target_id: str) -> bool:
        """添加引用关系"""
        cypher = """
        MATCH (a:Paper {id: $src}), (b:Paper {id: $tgt})
        MERGE (a)-[r:CITES]->(b)
        RETURN r
        """
        results = self._execute(cypher, {
            "src": source_id,
            "tgt": target_id
        })
        return len(results) > 0
    
    def add_semantic_entity(self, entity_id: str, name: str, entity_type: str) -> bool:
        """添加语义实体"""
        cypher = """
        MERGE (e:SemanticEntity {id: $id})
        SET e.name = $name, e.type = $type
        RETURN e
        """
        return self._execute_write(cypher, {
            "id": entity_id,
            "name": name,
            "type": entity_type
        })
    
    def link_paper_to_entity(self, paper_id: str, entity_id: str, relation_type: str = "PROPOSES") -> bool:
        """建立 Paper -> SemanticEntity 关系"""
        # 动态关系类型需要字符串拼接（Cypher 不支持参数化关系类型）
        cypher = f"""
        MATCH (p:Paper {{id: $pid}}), (e:SemanticEntity {{id: $eid}})
        MERGE (p)-[r:{relation_type}]->(e)
        RETURN r
        """
        results = self._execute(cypher, {
            "pid": paper_id,
            "eid": entity_id
        })
        return len(results) > 0
    
    def get_topic_status(self, topic_name: str) -> Dict[str, Any]:
        """获取 Topic 状态"""
        status = {
            'exists': False,
            'paper_count': 0,
            'last_updated': None,
            'needs_update': True
        }
        
        try:
            # 检查 Topic 是否存在
            results = self._execute(
                "MATCH (t:Topic {name: $name}) RETURN t.last_updated AS last_updated",
                {"name": topic_name}
            )
            
            if results:
                status['exists'] = True
                status['last_updated'] = results[0].get('last_updated')
                
                # 获取论文数量
                count_results = self._execute(
                    "MATCH (p:Paper)-[:BELONGS_TO]->(t:Topic {name: $name}) RETURN count(p) AS cnt",
                    {"name": topic_name}
                )
                if count_results:
                    status['paper_count'] = count_results[0].get('cnt', 0)
                
                if status['paper_count'] > 10:
                    status['needs_update'] = False
                    
        except Exception as e:
            logger.error(f"Error checking status: {e}")
        
        return status
    
    def get_all_papers(self) -> List[Dict[str, Any]]:
        """获取所有论文"""
        papers = []
        try:
            results = self._execute("MATCH (p:Paper) RETURN p")
            for record in results:
                paper = record.get('p', {})
                # 解析 JSON 字段
                for field in ['method_info', 'innovations', 'limitations', 'research_domains']:
                    if field in paper and isinstance(paper[field], str):
                        try:
                            paper[field] = json.loads(paper[field])
                        except:
                            pass
                papers.append(paper)
        except Exception as e:
            logger.error(f"Failed to get papers: {e}")
        return papers
    
    def get_paper_by_id(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取论文"""
        try:
            results = self._execute(
                "MATCH (p:Paper {id: $id}) RETURN p",
                {"id": paper_id}
            )
            if results:
                paper = results[0].get('p', {})
                # 解析 JSON 字段
                for field in ['method_info', 'innovations', 'limitations', 'research_domains']:
                    if field in paper and isinstance(paper[field], str):
                        try:
                            paper[field] = json.loads(paper[field])
                        except:
                            pass
                return paper
        except Exception as e:
            logger.error(f"Failed to get paper: {e}")
        return None

    # 兼容 PersistentGraphDB 接口
    def get_paper(self, paper_id: str) -> Optional[Dict[str, Any]]:
        return self.get_paper_by_id(paper_id)

    def add_relation(self, source_id: str, target_id: str, relation_type: str,
                    confidence: float, evidence: str = "", metadata: Dict = None) -> bool:
        """添加通用关系 (兼容 PersistentGraphDB)"""
        try:
            # 动态关系类型需要字符串拼接
            # 注意：这里假设 relation_type 是安全的（通常来自枚举）
            cypher = f"""
            MATCH (a:Paper {{id: $src}}), (b:Paper {{id: $tgt}})
            MERGE (a)-[r:{relation_type}]->(b)
            SET r.confidence = $confidence,
                r.evidence = $evidence,
                r.metadata = $metadata
            RETURN r
            """
            results = self._execute(cypher, {
                "src": source_id,
                "tgt": target_id,
                "confidence": confidence,
                "evidence": evidence,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False)
            })
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to add relation {source_id}->{target_id}: {e}")
            return False

    def get_citations(self, paper_id: str, direction: str = "citing") -> List[str]:
        """获取引用关系 (兼容 PersistentGraphDB)"""
        try:
            if direction == "citing":
                # paper_id 引用的论文
                cypher = "MATCH (a:Paper {id: $id})-[:CITES]->(b:Paper) RETURN b.id as id"
            else:
                # 引用 paper_id 的论文
                cypher = "MATCH (b:Paper)-[:CITES]->(a:Paper {id: $id}) RETURN b.id as id"
            
            results = self._execute(cypher, {"id": paper_id})
            return [r['id'] for r in results]
        except Exception as e:
            logger.error(f"Failed to get citations for {paper_id}: {e}")
            return []

    def get_neighbors(self, paper_id: str) -> List[str]:
        """获取论文的邻居 (兼容 PersistentGraphDB)"""
        try:
            cypher = """
            MATCH (a:Paper {id: $id})-[r]-(b:Paper)
            RETURN b.id as id
            """
            results = self._execute(cypher, {"id": paper_id})
            return list(set(r['id'] for r in results))
        except Exception as e:
            logger.error(f"Failed to get neighbors for {paper_id}: {e}")
            return []
    
    def update_paper(self, paper_id: str, updates: Dict[str, Any]) -> bool:
        """更新论文属性"""
        try:
            # 构建 SET 子句
            set_clauses = []
            params = {"id": paper_id}
            
            for key, value in updates.items():
                if key == 'method_info' and isinstance(value, dict):
                    value = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, list):
                    value = json.dumps(value, ensure_ascii=False)
                params[key] = value
                set_clauses.append(f"p.{key} = ${key}")
            
            if not set_clauses:
                return True
            
            cypher = f"""
            MATCH (p:Paper {{id: $id}})
            SET {', '.join(set_clauses)}
            RETURN p
            """
            results = self._execute(cypher, params)
            return len(results) > 0
        except Exception as e:
            logger.error(f"Failed to update paper: {e}")
            return False
    
    def detect_communities(self) -> Dict[int, List[str]]:
        """
        运行社区发现算法 (Leiden)
        
        Returns:
            {community_id: [paper_id_list]}
        """
        try:
            logger.info("Starting community detection...")
            
            # 1. 获取所有 Paper 节点 ID
            results = self._execute("MATCH (p:Paper) RETURN p.id AS id")
            paper_ids = [r['id'] for r in results]
            
            if not paper_ids:
                return {}
            
            # 建立 ID 到索引的映射
            id_to_idx = {pid: i for i, pid in enumerate(paper_ids)}
            idx_to_id = {i: pid for pid, i in id_to_idx.items()}
            
            # 2. 获取边 (CITES)
            edge_results = self._execute(
                "MATCH (a:Paper)-[:CITES]->(b:Paper) RETURN a.id AS src, b.id AS dst"
            )
            edges = []
            for record in edge_results:
                src, dst = record['src'], record['dst']
                if src in id_to_idx and dst in id_to_idx:
                    edges.append((id_to_idx[src], id_to_idx[dst]))
            
            logger.info(f"Graph loaded: {len(paper_ids)} nodes, {len(edges)} edges")
            
            if not edges:
                # 没有边，每个点自成一社区
                return {i: [pid] for i, pid in enumerate(paper_ids)}
            
            # 3. 构建 igraph 对象
            g = ig.Graph(len(paper_ids), edges)
            
            # 4. 运行 Leiden 算法
            partition = g.community_leiden(objective_function='modularity')
            
            # 5. 更新数据库并收集结果
            communities = {}
            for idx, comm_id in enumerate(partition.membership):
                paper_id = idx_to_id[idx]
                
                if comm_id not in communities:
                    communities[comm_id] = []
                communities[comm_id].append(paper_id)
                
                # 更新 DB
                self._execute(
                    "MATCH (p:Paper {id: $id}) SET p.community_id = $comm",
                    {"id": paper_id, "comm": comm_id}
                )
            
            logger.info(f"Detected {len(communities)} communities")
            return communities
            
        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            return {}
    
    def execute_cypher(self, cypher: str, params: Dict[str, Any] = None) -> List[Dict]:
        """执行自定义 Cypher 查询"""
        return self._execute(cypher, params)
    
    def _node_exists(self, label: str, key_field: str, key_val: str) -> bool:
        """检查节点是否存在"""
        try:
            cypher = f"MATCH (n:{label} {{{key_field}: $val}}) RETURN count(n) AS cnt"
            results = self._execute(cypher, {"val": key_val})
            return results and results[0].get('cnt', 0) > 0
        except Exception as e:
            logger.error(f"Node exists check failed: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Memgraph connection closed (mgclient)")
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Memgraph connection closed (neo4j)")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def clear_database(self) -> bool:
        """清空数据库中的所有数据"""
        try:
            logger.warning("Clearing database...")
            # 删除所有节点和关系
            self._execute_write("MATCH (n) DETACH DELETE n")
            logger.info("Database cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            return False


# 兼容性别名
GraphDB = MemgraphGraphDB


# 便捷函数
def get_graph_db(read_only: bool = False) -> MemgraphGraphDB:
    """获取图数据库实例"""
    return MemgraphGraphDB(read_only=read_only)