# 全局学术图谱 (Global Academic Graph) 设计文档

## 1. 核心目标

构建一个持续增长的、跨Topic的全局学术知识图谱，实现：
1. **自动聚合**：每当一个Survey任务完成，自动将其生成的局部图谱（mekg_data.json）合并到全局图谱中。
2. **知识复用**：新任务开始时，优先从全局图谱检索相关论文和关系，减少重复爬取。
3. **跨域发现**：通过图谱分析发现不同Topic之间的潜在联系（如方法迁移、跨领域应用）。
4. **本地替代**：最终实现本地图谱搜索替代部分在线搜索，提高速度并降低成本。

## 2. 系统架构

### 2.1 数据存储层
使用现有的 `SemanticEntityDB` (基于SQLite) 作为全局存储后端。

- **数据库文件**: `data/graph_db/global_academic_graph.db`
- **核心表结构** (复用现有Schema):
  - `papers`: 存储论文元数据 (去重键: paper_id/openalex_id)
  - `relations`: 存储论文间关系 (引用、语义关系)
  - `semantic_entities`: 存储提取的实体 (Method, Task, Metric等)
  - `topics`: 存储Topic信息及与论文的关联

### 2.2 核心组件：GlobalGraphManager

位于 `mekg/src/automation/global_graph_manager.py`，负责：

1. **图谱融合 (Graph Fusion)**
   - 输入：任务生成的 `mekg_data.json`
   - 逻辑：
     - 遍历新图谱中的节点，若全局库不存在则插入，存在则更新（合并属性）。
     - 遍历新图谱中的边，若全局库不存在则插入，存在则更新置信度。
     - 建立 Paper-Topic 关联。

2. **冲突解决 (Conflict Resolution)**
   - 同一论文在不同任务中可能有不同的属性提取结果。
   - 策略：保留并集，或基于置信度更新。

3. **自动触发器 (Auto-Trigger)**
   - 在Pipeline任务完成阶段（如 `attempt_completion` 前）调用融合接口。

### 2.3 搜索服务接口

位于 `mekg/src/search/global_search_service.py`，提供：

1. **关键词搜索**: 基于FTS (Full Text Search) 搜索论文标题和摘要。
2. **实体搜索**: 查找包含特定Method或Task的论文。
3. **子图提取**: 给定Topic或关键词，提取相关的子图用于新任务。

## 3. 工作流集成

### 3.1 写入流程 (任务完成时)
```python
# 伪代码
def on_task_complete(task_id, topic):
    mekg_path = f"outputs/{task_id}/mekg/mekg_data.json"
    manager = GlobalGraphManager()
    manager.merge_task_graph(mekg_path, topic)
```

### 3.2 读取流程 (新任务开始时)
```python
# 伪代码
def start_new_task(topic):
    search_service = GlobalSearchService()
    # 1. 先查本地图谱
    local_papers = search_service.search_papers(topic)
    # 2. 再查在线 (OpenAlex)
    online_papers = openalex.search(topic)
    # 3. 合并结果
    all_papers = merge(local_papers, online_papers)
```

## 4. 目录结构变更

```
mekg/
├── src/
│   ├── automation/
│   │   └── global_graph_manager.py  # [新增] 全局图谱管理
│   ├── search/
│   │   └── global_search_service.py # [新增] 全局搜索服务
│   └── storage/
│       └── semantic_entity_db.py    # [复用] 数据库实现
└── docs/
    └── design/
        └── Global_Academic_Graph_Design.md # [新增] 本文档