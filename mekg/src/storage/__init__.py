"""
MEKG Storage Module - 存储层

包含:
- SemanticEntityDB: 语义实体数据库 (SQLite)
- KuzuGraphDB: Kuzu图数据库
- MemgraphGraphDB: Memgraph图数据库
"""

from mekg.src.storage.semantic_entity_db import SemanticEntityDB

# 可选导入 (需要额外依赖)
try:
    from mekg.src.storage.kuzu_graph_db import KuzuGraphDB
except ImportError:
    KuzuGraphDB = None

try:
    from mekg.src.storage.memgraph_graph_db import MemgraphGraphDB
except ImportError:
    MemgraphGraphDB = None

__all__ = [
    "SemanticEntityDB",
    "KuzuGraphDB",
    "MemgraphGraphDB",
]