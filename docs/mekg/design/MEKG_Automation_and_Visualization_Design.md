# MEKG 自动化维护与增强可视化设计方案

## 1. 系统架构概览

本方案旨在扩展现有的 MEKG (Multi-modal Evolutionary Knowledge Graph) 系统，增加自动化维护能力和交互式可视化功能。

### 核心组件
1.  **AutoMaintenanceManager (自动化维护管理器)**: 负责定期扫描图谱，识别社区，调用 LLM 分析 Topic，并自动补充缺失内容。
2.  **TopicGraphBuilder (Topic 驱动构建器)**: 负责从指定 Topic 出发，执行"爬取 -> 关系提取 -> 图谱编织"的全流程。
3.  **EChartsVisualizer (交互式可视化引擎)**: 生成基于 Web 的高质量交互式图表（树状图和力导向图）。

---

## 2. 模块一：自动化图谱维护 (Auto-Maintenance)

### 目标
自动读取现有大图谱，识别社区结构，分析 Topic 活跃度，并对陈旧或稀疏的 Topic 进行自动补充。

### 流程设计
1.  **图谱加载与社区检测**:
    *   从 `PersistentGraphDB` 加载完整图谱。
    *   调用 `MEKGAnalyzer.detect_communities(algorithm='louvain')` 识别论文社区。
2.  **社区 Topic 语义化 (LLM)**:
    *   对每个社区，提取核心论文（PageRank 高分）的标题和摘要。
    *   **Prompt**: "分析这组论文的共同主题，生成一个简短的 Topic 名称和描述。"
    *   将生成的 Topic 信息回写到 `topics` 表中。
3.  **查漏补缺 (Gap Analysis)**:
    *   **时间检查**: 检查该 Topic 下最新论文的年份。如果 `current_year - last_paper_year > 1`，标记为"需更新"。
    *   **密度检查**: 如果社区内部连接稀疏（密度低于阈值），标记为"需补充"。
4.  **自动补充执行**:
    *   对标记为"需更新/补充"的 Topic，生成搜索关键词。
    *   调用 `PaperPoolCollector` 爬取新论文（限制数量，如 top-10）。
    *   调用关系提取模块，将新论文编织入库。

### 新增文件
*   `src/modules/mekg/maintenance_manager.py`: 核心逻辑实现。

---

## 3. 模块二：Topic 驱动构建 (Topic-Driven Build)

### 目标
给定一个 Topic，从零开始或基于现有基础，构建完整的知识子图，为综述生成做准备。

### 流程设计
1.  **输入**: 用户给定 Topic (如 "Large Language Model Agents")。
2.  **深度爬取**:
    *   调用 `PaperPoolCollector` 进行多跳搜索（关键词搜索 + 综述引用扩展）。
3.  **关系提取与编织**:
    *   使用 `SemanticEntityExtractor` (需确认是否存在或需新建) 或 LLM 提取论文间的 `evolved_from`, `contrasts_with` 等关系。
    *   将论文和关系存入 `PersistentGraphDB`。
4.  **子图提取**:
    *   使用 `db.extract_subgraph_by_topic()` 提取相关子图。
    *   输出结构化数据供综述生成模块使用。

### 新增文件
*   `src/modules/mekg/topic_builder.py`: 封装构建流程。

---

## 4. 模块三：增强可视化 (Enhanced Visualization)

### 技术选型
*   **前端库**: Apache ECharts (通过 CDN 引入)。
*   **实现方式**: Python 生成包含数据和 JS 代码的独立 HTML 文件。
*   **优势**: 交互性强（缩放、拖拽、点击）、无需 Python 后端服务、浏览器直接打开。

### 图表设计 1：动态力导向图 (Force-Directed Graph)
*   **用途**: 展示论文间的引用和语义关系，看清"为什么这个关系是这么定义的"。
*   **功能**:
    *   **节点**: 代表论文，大小映射 PageRank，颜色映射 Community/Topic。
    *   **边**: 代表关系，不同颜色/线型代表不同关系类型 (`evolved_from`, `cites` 等)。
    *   **交互**:
        *   **Hover**: 显示论文标题、年份、作者。
        *   **Click**: 侧边栏弹出详细信息（摘要、属性、关系证据 `evidence`）。
        *   **Filter**: 按年份或关系类型过滤显示。

### 图表设计 2：层级树状图 (Tree/Sunburst Chart)
*   **用途**: 展示 Topic -> Subtopic -> Paper 的层级结构，理清知识脉络。
*   **结构**:
    *   根节点: 总图谱/查询 Topic。
    *   第一层: 自动检测出的社区 (Topics)。
    *   第二层: 核心论文 (按影响力排序)。
    *   第三层 (可选): 衍生论文。
*   **交互**: 点击节点展开/折叠，查看分支详情。

### 新增文件
*   `src/modules/visualization/echarts_builder.py`: 负责生成 HTML。
*   `src/modules/visualization/templates/`: 存放 HTML 模板字符串。

---

## 5. 执行计划

1.  **Step 1**: 实现 `EChartsVisualizer` 基础版，先跑通从 DB 读取数据生成力导向图的功能。（优先满足"看清关系"的需求）
2.  **Step 2**: 实现 `AutoMaintenanceManager` 的社区检测和 Topic 语义化部分。
3.  **Step 3**: 实现 `TopicGraphBuilder` 和自动补充逻辑。
4.  **Step 4**: 整合所有功能，提供一个统一的 CLI 入口。
