# Memgraph 图数据库部署指南

本项目已从 KuzuDB（嵌入式图数据库）迁移到 Memgraph（客户端-服务器架构图数据库），以支持**多进程并发访问**。

## 为什么选择 Memgraph？

| 特性 | KuzuDB | Memgraph |
|------|--------|----------|
| 并发访问 | ❌ 单进程独占 | ✅ 多客户端并发 |
| 部署方式 | 嵌入式（文件） | 客户端-服务器 |
| 查询语言 | Cypher | Cypher (兼容) |
| 性能 | 高（本地） | 高（内存优先） |
| 适用场景 | 单用户/脚本 | 生产环境/多服务 |

## 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 拉取并启动 Memgraph
docker run -d \
  --name memgraph \
  -p 7687:7687 \
  -p 7444:7444 \
  -v memgraph_data:/var/lib/memgraph \
  memgraph/memgraph-platform

# 验证连接
docker logs memgraph
```

Memgraph 默认端口：
- `7687`: Bolt 协议（应用连接）
- `7444`: Web 控制台（Memgraph Lab）

### 方式二：本地安装

#### Windows
1. 下载安装包：https://memgraph.com/download
2. 运行安装程序
3. 启动服务：`memgraph`

#### Linux (Ubuntu/Debian)
```bash
curl https://install.memgraph.com | sh
sudo systemctl start memgraph
```

#### macOS
```bash
brew install memgraph
memgraph
```

## 配置连接

### 环境变量（推荐）

在项目根目录创建 `.env` 文件：

```env
# Memgraph 连接配置
MEMGRAPH_URI=bolt://localhost:7687
MEMGRAPH_USER=
MEMGRAPH_PASSWORD=
```

### 代码中配置

```python
from src.modules.mekg.storage.memgraph_graph_db import MemgraphGraphDB

# 使用默认配置（从环境变量读取）
db = MemgraphGraphDB()

# 或显式指定
db = MemgraphGraphDB(
    uri="bolt://localhost:7687",
    user="admin",
    password="your_password"
)
```

## 验证安装

运行以下命令验证 Memgraph 连接：

```bash
python -c "
from src.modules.mekg.storage.memgraph_graph_db import MemgraphGraphDB
db = MemgraphGraphDB()
print('✅ Memgraph 连接成功!')
result = db.execute_cypher('RETURN 1 AS test')
print(f'查询结果: {result}')
"
```

## 数据迁移

如果你有旧的 KuzuDB 数据需要迁移，可以：

1. **导出旧数据**（如果 KuzuDB 还能访问）
2. **使用脚本导入到 Memgraph**

由于 KuzuDB 和 Memgraph 都使用 Cypher，大部分查询可以直接复用。

## 常用操作

### 查看数据库状态

```cypher
// 查看节点数量
MATCH (n) RETURN labels(n) AS label, count(n) AS count;

// 查看关系数量
MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count;
```

### 清空数据库

```cypher
// ⚠️ 危险操作！会删除所有数据
MATCH (n) DETACH DELETE n;
```

### 创建索引

```cypher
CREATE INDEX ON :Paper(id);
CREATE INDEX ON :Topic(name);
CREATE INDEX ON :SemanticEntity(id);
```

## Web 控制台

Memgraph 提供了 Web 控制台 **Memgraph Lab**：

1. 访问 http://localhost:7444
2. 连接到 `bolt://localhost:7687`
3. 可视化查询和管理数据

## 故障排除

### 连接失败

```
neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information
```

**解决方案**：
1. 确认 Memgraph 服务正在运行
2. 检查端口 7687 是否被占用
3. 检查防火墙设置

### 认证失败

```
neo4j.exceptions.AuthError: The client is unauthorized
```

**解决方案**：
1. 检查用户名和密码
2. Memgraph 默认无需认证，如果设置了认证需要提供正确凭据

### 内存不足

Memgraph 是内存优先数据库，大数据集需要足够内存。

**解决方案**：
```bash
# Docker 中限制内存
docker run -d --memory=4g memgraph/memgraph-platform
```

## 与 Neo4j 的兼容性

Memgraph 兼容 Neo4j Bolt 协议，因此：
- 使用相同的 `neo4j` Python 驱动
- 大部分 Cypher 查询通用
- 可以使用 Neo4j 生态工具

如果需要切换到 Neo4j，只需更改连接 URI 即可。

## 参考链接

- [Memgraph 官方文档](https://memgraph.com/docs)
- [Memgraph Cypher 手册](https://memgraph.com/docs/cypher-manual)
- [Neo4j Python 驱动文档](https://neo4j.com/docs/python-manual/current/)