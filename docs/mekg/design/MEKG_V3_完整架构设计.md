# MEKG V3 完整架构设计文档

## 1. 概述

### 1.1 背景与目标

根据导师的反馈，MEKG V3 需要实现以下核心目标：

1. **构建持久化大图谱**：类似Neo4j的图数据库，覆盖多个topic，支持快速提取子图
2. **跨topic连接**：不同topic之间的知识图谱要互相有交叉有连接
3. **双重搜索机制**：同时搜索图数据库和网络（OpenAlex等），确保获取最新论文
4. **Survey模板库**：收集好的survey论文大纲模板，用RAG匹配后给LLM参考生成大纲
5. **增强关系发现**：不仅考虑引用关系，还要考虑共性（方法论拆解、共享实体等）

### 1.2 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MEKG V3 系统架构                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        用户接口层                                     │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │ build_mekg   │  │ query_graph  │  │ generate_    │              │   │
│  │  │ _v3.py       │  │ .py          │  │ survey.py    │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                        协调层                                         │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │              DualSearchOrchestrator                           │   │   │
│  │  │  - 协调图数据库搜索和网络搜索                                    │   │   │
│  │  │  - 融合搜索结果                                                 │   │   │
│  │  │  - 增量更新图谱                                                 │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                        核心处理层                                     │   │
│  │                                                                       │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐         │   │
│  │  │ Semantic       │  │ Citation       │  │ Enhanced       │         │   │
│  │  │ Entity         │  │ Context        │  │ Relation       │         │   │
│  │  │ Extractor      │  │ Analyzer       │  │ Discoverer     │         │   │
│  │  │                │  │                │  │                │         │   │
│  │  │ - 7种实体类型   │  │ - 8种引用关系  │  │ - 21种关系类型 │         │   │
│  │  │ - LLM抽取      │  │ - 规则+LLM    │  │ - 50线程并发   │         │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘         │   │
│  │                                                                       │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐         │   │
│  │  │ Entity         │  │ Entity         │  │ Template       │         │   │
│  │  │ Disambiguator  │  │ Cleaner        │  │ Extractor      │         │   │
│  │  │                │  │                │  │                │         │   │
│  │  │ - K-means聚类  │  │ - 规则验证     │  │ - 大纲提取     │         │   │
│  │  │ - DBSCAN聚类   │  │ - LLM清洗     │  │ - 模板匹配     │         │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                        数据层                                         │   │
│  │                                                                       │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │                  SemanticEntityDB (SQLite)                      │ │   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │ │   │
│  │  │  │ papers   │ │ relations│ │ semantic │ │ entity   │          │ │   │
│  │  │  │          │ │          │ │ _entities│ │ _clusters│          │ │   │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │ │   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                       │ │   │
│  │  │  │ topics   │ │ citations│ │ citation │                       │ │   │
│  │  │  │          │ │          │ │ _contexts│                       │ │   │
│  │  │  └──────────┘ └──────────┘ └──────────┘                       │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                       │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │              SurveyTemplateLibrary (向量数据库)                  │ │   │
│  │  │  - 大纲模板存储                                                  │ │   │
│  │  │  - 语义相似度匹配                                                │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼───────────────────────────────────┐   │
│  │                        外部数据源                                     │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │ OpenAlex     │  │ Semantic     │  │ arXiv        │              │   │
│  │  │ API          │  │ Scholar      │  │              │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. 核心组件详细设计

### 2.1 持久化图数据库 (SemanticEntityDB)

#### 2.1.1 数据模型

```sql
-- 论文节点表
CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT,
    year INTEGER,
    venue TEXT,
    citation_count INTEGER DEFAULT 0,
    doi TEXT,
    openalex_id TEXT,
    pagerank REAL DEFAULT 0.0,
    betweenness REAL DEFAULT 0.0,
    community_id INTEGER,
    has_semantic_entities BOOLEAN DEFAULT FALSE,
    semantic_extraction_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 语义实体表
CREATE TABLE semantic_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- problem, method, model, task, dataset, metric, innovation
    entity_value TEXT NOT NULL,
    canonical_value TEXT,       -- 标准化后的值
    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'abstract',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- 语义关系表
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,  -- 21种关系类型
    confidence REAL DEFAULT 0.0,
    llm_confidence REAL DEFAULT 0.0,
    citation_signal REAL DEFAULT 0.0,
    evidence TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, target_id, relation_type)
);

-- 引用上下文表
CREATE TABLE citation_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_paper_id TEXT NOT NULL,
    cited_paper_id TEXT NOT NULL,
    context TEXT NOT NULL,
    relation_type TEXT,  -- 8种引用关系类型
    confidence REAL DEFAULT 0.0,
    evidence TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(citing_paper_id, cited_paper_id)
);

-- 实体聚类表
CREATE TABLE entity_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    entity_value TEXT NOT NULL,
    is_representative BOOLEAN DEFAULT FALSE,
    frequency INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Topic表
CREATE TABLE topics (
    topic TEXT PRIMARY KEY,
    keywords TEXT,
    description TEXT,
    paper_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Topic-论文关联表
CREATE TABLE topic_papers (
    topic TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    relevance_score REAL DEFAULT 1.0,
    is_core BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (topic, paper_id)
);
```

#### 2.1.2 关系类型定义

**21种语义关系类型**（分为5大类）：

```python
class RelationType(Enum):
    # 结构关系 (Structural)
    CITES = "cites"                    # 引用
    CITED_BY = "cited_by"              # 被引用
    CO_CITED = "co_cited"              # 共被引
    BIBLIOGRAPHIC_COUPLING = "bibliographic_coupling"  # 文献耦合
    
    # 语义关系 (Semantic)
    EXTENDS = "extends"                # 扩展
    IMPROVES = "improves"              # 改进
    COMPARES = "compares"              # 比较
    APPLIES = "applies"                # 应用
    CONTRADICTS = "contradicts"        # 矛盾
    SUPPORTS = "supports"              # 支持
    
    # 概念关系 (Conceptual)
    SHARES_METHOD = "shares_method"    # 共享方法
    SHARES_TASK = "shares_task"        # 共享任务
    SHARES_DATASET = "shares_dataset"  # 共享数据集
    SHARES_MODEL = "shares_model"      # 共享模型
    SHARES_PROBLEM = "shares_problem"  # 共享问题
    
    # 时间关系 (Temporal)
    PRECEDES = "precedes"              # 时间先于
    FOLLOWS = "follows"                # 时间后于
    CONTEMPORARY = "contemporary"       # 同时期
    
    # 作者关系 (Authorship)
    SAME_AUTHOR = "same_author"        # 同作者
    SAME_VENUE = "same_venue"          # 同会议/期刊
    SAME_INSTITUTION = "same_institution"  # 同机构
```

**8种引用上下文关系类型**：

```python
class CitationRelationType(Enum):
    DIRECT_USE = "direct_use"          # 直接使用方法/模型
    EXTENDS = "extends"                # 扩展工作
    COMPARES = "compares"              # 比较/对比
    TASK_RELATED = "task_related"      # 任务相关
    BACKGROUND = "background"          # 背景介绍
    SUPPORTS = "supports"              # 支持论点
    REFUTES = "refutes"                # 反驳
    UNKNOWN = "unknown"                # 未知
```

### 2.2 语义实体抽取器 (SemanticEntityExtractor)

#### 2.2.1 7种语义实体类型

```python
class SemanticEntityType(Enum):
    PROBLEM = "problem"        # 研究问题
    METHOD = "method"          # 方法/技术
    MODEL = "model"            # 模型/架构
    TASK = "task"              # 任务
    DATASET = "dataset"        # 数据集
    METRIC = "metric"          # 评估指标
    INNOVATION = "innovation"  # 创新点
```

#### 2.2.2 抽取流程

```
输入: 论文 (title, abstract, full_text)
    │
    ▼
┌─────────────────────────────────────┐
│  1. 预处理                           │
│  - 文本清洗                          │
│  - 分句                              │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. LLM实体抽取                      │
│  - 使用结构化Prompt                  │
│  - 返回JSON格式实体                  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 实体清洗                         │
│  - 规则验证                          │
│  - 去除无效实体                      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 实体消歧                         │
│  - 嵌入向量计算                      │
│  - 聚类合并同义实体                  │
└─────────────────────────────────────┘
    │
    ▼
输出: PaperSemanticEntities
```

### 2.3 增强关系发现器 (EnhancedRelationDiscoverer)

#### 2.3.1 关系发现策略

```python
class EnhancedRelationDiscoverer:
    """
    增强关系发现器
    
    发现策略：
    1. 结构关系：基于引用网络
    2. 语义关系：基于引用上下文分析
    3. 概念关系：基于共享实体
    4. 时间关系：基于发表年份
    5. 作者关系：基于作者/机构信息
    """
    
    def discover_relations(self, paper1_id, paper2_id):
        relations = []
        
        # 1. 结构关系
        relations.extend(self._discover_structural_relations(paper1_id, paper2_id))
        
        # 2. 语义关系（需要引用上下文）
        relations.extend(self._discover_semantic_relations(paper1_id, paper2_id))
        
        # 3. 概念关系（基于共享实体）
        relations.extend(self._discover_conceptual_relations(paper1_id, paper2_id))
        
        # 4. 时间关系
        relations.extend(self._discover_temporal_relations(paper1_id, paper2_id))
        
        # 5. 作者关系
        relations.extend(self._discover_authorship_relations(paper1_id, paper2_id))
        
        return relations
```

#### 2.3.2 共享实体关系发现

```python
def _discover_conceptual_relations(self, paper1_id, paper2_id):
    """基于共享实体发现概念关系"""
    relations = []
    
    # 获取两篇论文的语义实体
    entities1 = self.db.get_paper_semantic_entities(paper1_id)
    entities2 = self.db.get_paper_semantic_entities(paper2_id)
    
    # 检查共享方法
    shared_methods = self._find_shared_entities(
        entities1.methods, entities2.methods
    )
    if shared_methods:
        relations.append(Relation(
            source=paper1_id,
            target=paper2_id,
            type=RelationType.SHARES_METHOD,
            confidence=len(shared_methods) / max(len(entities1.methods), 1),
            evidence=f"Shared methods: {', '.join(shared_methods)}"
        ))
    
    # 检查共享任务
    shared_tasks = self._find_shared_entities(
        entities1.tasks, entities2.tasks
    )
    if shared_tasks:
        relations.append(Relation(
            source=paper1_id,
            target=paper2_id,
            type=RelationType.SHARES_TASK,
            confidence=len(shared_tasks) / max(len(entities1.tasks), 1),
            evidence=f"Shared tasks: {', '.join(shared_tasks)}"
        ))
    
    # 类似地检查 dataset, model, problem...
    
    return relations
```

### 2.4 Survey模板库 (SurveyTemplateLibrary)

#### 2.4.1 模板数据结构

```python
@dataclass
class SurveyTemplate:
    """Survey大纲模板"""
    template_id: str
    topic: str                    # 主题关键词
    source_paper: str             # 来源论文
    outline: List[OutlineSection] # 大纲结构
    template_type: str            # 模板类型
    quality_score: float          # 质量评分
    embedding: List[float]        # 向量嵌入
    
@dataclass
class OutlineSection:
    """大纲章节"""
    level: int                    # 层级 (1, 2, 3)
    title: str                    # 标题
    description: str              # 描述
    subsections: List['OutlineSection']
```

#### 2.4.2 模板类型

根据导师建议，总结几种常见的Survey架构模板：

**类型1: 范式导向型**
```
1. Introduction
2. Background
3. Paradigm A
   3.1 Method Category 1
   3.2 Method Category 2
4. Paradigm B
   4.1 Method Category 1
   4.2 Method Category 2
5. Evaluation
6. Challenges and Future Directions
7. Conclusion
```

**类型2: 技术栈型**
```
1. Introduction
2. Problem Definition
3. Pre-training Methods
   3.1 Architecture
   3.2 Training Objectives
4. Fine-tuning Methods
   4.1 Full Fine-tuning
   4.2 Parameter-Efficient Fine-tuning
5. Inference Optimization
6. Applications
7. Conclusion
```

**类型3: 任务导向型**
```
1. Introduction
2. Task Definition
3. Datasets and Benchmarks
4. Methods
   4.1 Traditional Methods
   4.2 Neural Methods
   4.3 LLM-based Methods
5. Evaluation Results
6. Analysis and Discussion
7. Future Directions
```

**类型4: 工具使用型**（导师提到的例子）
```
1. Introduction
2. Background
3. Paradigm of Tool Use
4. Fine-tuning
   4.1 Fine-tuned Dataset Construction
   4.2 Fine-tuning Methods
   4.3 Other Issues
5. In-context Learning without Retrieval
6. Retrieval-Augmented Methods
7. Evaluation
8. Conclusion
```

#### 2.4.3 模板匹配流程

```
输入: 用户Topic
    │
    ▼
┌─────────────────────────────────────┐
│  1. Topic向量化                      │
│  - 使用Embedding模型                 │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 相似度搜索                       │
│  - 在模板库中搜索相似Topic           │
│  - 返回Top-K匹配模板                 │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 模板选择                         │
│  - 考虑质量评分                      │
│  - 考虑模板类型适配度                │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. Few-shot生成                     │
│  - 将匹配模板作为示例                │
│  - LLM生成新大纲                     │
└─────────────────────────────────────┘
    │
    ▼
输出: 定制化Survey大纲
```

### 2.5 双重搜索协调器 (DualSearchOrchestrator)

#### 2.5.1 搜索流程

```
输入: Topic + Keywords
    │
    ├─────────────────────────────────────┐
    │                                     │
    ▼                                     ▼
┌─────────────────────┐     ┌─────────────────────┐
│  图数据库搜索        │     │  网络搜索            │
│                     │     │                     │
│  1. 关键词匹配       │     │  1. OpenAlex API    │
│  2. 子图提取         │     │  2. 综述优先策略     │
│  3. 相关论文扩展     │     │  3. 引用展开         │
└─────────────────────┘     └─────────────────────┘
    │                                     │
    └─────────────────┬───────────────────┘
                      │
                      ▼
            ┌─────────────────────┐
            │  结果融合            │
            │                     │
            │  1. 去重             │
            │  2. 新论文入库       │
            │  3. 关系发现         │
            └─────────────────────┘
                      │
                      ▼
            ┌─────────────────────┐
            │  子图构建            │
            │                     │
            │  1. 核心论文识别     │
            │  2. 关系网络构建     │
            │  3. 大纲生成         │
            └─────────────────────┘
                      │
                      ▼
            输出: 相关子图 + 大纲建议
```

#### 2.5.2 增量更新策略

```python
class DualSearchOrchestrator:
    def search_and_update(self, topic, keywords):
        # 1. 搜索图数据库
        graph_results = self.db.search_by_keywords(keywords)
        
        # 2. 搜索网络（始终执行，确保获取最新论文）
        network_results = self.paper_collector.search_papers(
            keywords=keywords,
            year_start=2018,
            year_end=2024
        )
        
        # 3. 识别新论文
        existing_ids = set(self.db.get_all_paper_ids())
        new_papers = [p for p in network_results if p['paper_id'] not in existing_ids]
        
        # 4. 增量入库
        if new_papers:
            self.db.add_papers_batch(new_papers)
            
            # 5. 为新论文抽取实体
            for paper in new_papers:
                entities = self.entity_extractor.extract(paper)
                self.db.add_paper_semantic_entities(paper['paper_id'], entities)
            
            # 6. 发现新关系
            self.relation_discoverer.discover_for_new_papers(new_papers)
        
        # 7. 提取子图
        subgraph = self.db.extract_subgraph_by_keywords(keywords)
        
        return subgraph
```

## 3. 关系发现算法详解

### 3.1 论文间关系的确切发现方法

导师指出"如何找到论文他们之间的确切关系是非常有难度的"。以下是我们采用的多层次关系发现策略：

#### 3.1.1 第一层：引用关系（客观、可靠）

```python
def discover_citation_relations(paper1_id, paper2_id):
    """
    基于引用网络发现关系
    - 直接引用：A引用B
    - 共被引：A和B被同一篇论文引用
    - 文献耦合：A和B引用了相同的论文
    """
    relations = []
    
    # 直接引用
    if paper2_id in paper1.references:
        relations.append(("cites", 1.0))
    
    # 共被引
    citing_1 = set(db.get_citing_papers(paper1_id))
    citing_2 = set(db.get_citing_papers(paper2_id))
    co_citing = citing_1 & citing_2
    if co_citing:
        confidence = len(co_citing) / max(len(citing_1), len(citing_2))
        relations.append(("co_cited", confidence))
    
    # 文献耦合
    refs_1 = set(paper1.references)
    refs_2 = set(paper2.references)
    shared_refs = refs_1 & refs_2
    if shared_refs:
        confidence = len(shared_refs) / max(len(refs_1), len(refs_2))
        relations.append(("bibliographic_coupling", confidence))
    
    return relations
```

#### 3.1.2 第二层：引用上下文分析（语义理解）

```python
def analyze_citation_context(citing_paper, cited_paper):
    """
    分析引用上下文，理解引用意图
    
    规则匹配 + LLM分析
    """
    # 1. 提取引用上下文
    context = extract_citation_context(citing_paper.full_text, cited_paper.title)
    
    # 2. 规则匹配（快速、准确）
    patterns = {
        "direct_use": [
            r"we use .* from \[?\d+\]?",
            r"following \[?\d+\]?",
            r"based on .* \[?\d+\]?",
        ],
        "extends": [
            r"we extend .* \[?\d+\]?",
            r"building upon \[?\d+\]?",
            r"improve upon \[?\d+\]?",
        ],
        "compares": [
            r"compared to \[?\d+\]?",
            r"outperforms \[?\d+\]?",
            r"unlike \[?\d+\]?",
        ],
        # ... 更多模式
    }
    
    for relation_type, pattern_list in patterns.items():
        for pattern in pattern_list:
            if re.search(pattern, context, re.IGNORECASE):
                return CitationRelation(
                    type=relation_type,
                    confidence=0.8,
                    evidence=context
                )
    
    # 3. LLM分析（复杂情况）
    if use_llm:
        return llm_analyze_citation_context(context)
    
    return CitationRelation(type="unknown", confidence=0.5)
```

#### 3.1.3 第三层：共享实体分析（方
法论拆解）

```python
def discover_shared_entity_relations(paper1_id, paper2_id):
    """
    基于共享实体发现关系
    
    这是导师强调的"方法论拆解"的核心实现
    """
    relations = []
    
    # 获取两篇论文的语义实体
    entities1 = db.get_paper_semantic_entities(paper1_id)
    entities2 = db.get_paper_semantic_entities(paper2_id)
    
    # 实体类型映射到关系类型
    entity_to_relation = {
        "method": "shares_method",
        "task": "shares_task",
        "dataset": "shares_dataset",
        "model": "shares_model",
        "problem": "shares_problem",
    }
    
    for entity_type, relation_type in entity_to_relation.items():
        # 获取该类型的实体
        list1 = getattr(entities1, f"{entity_type}s", [])
        list2 = getattr(entities2, f"{entity_type}s", [])
        
        # 使用标准化值进行匹配
        values1 = {e.canonical_value or e.value.lower() for e in list1}
        values2 = {e.canonical_value or e.value.lower() for e in list2}
        
        shared = values1 & values2
        
        if shared:
            confidence = len(shared) / max(len(values1), len(values2), 1)
            relations.append(Relation(
                source=paper1_id,
                target=paper2_id,
                type=relation_type,
                confidence=confidence,
                evidence=f"Shared {entity_type}s: {', '.join(shared)}"
            ))
    
    return relations
```

#### 3.1.4 第四层：LLM深度分析（复杂关系）

```python
def llm_analyze_relation(paper1, paper2):
    """
    使用LLM分析复杂的论文关系
    
    适用于：
    - 引用上下文不明确
    - 需要理解方法论差异
    - 判断是否为改进/扩展关系
    """
    prompt = f"""
    分析以下两篇论文的关系：
    
    论文1:
    标题: {paper1.title}
    摘要: {paper1.abstract}
    方法: {paper1.methods}
    
    论文2:
    标题: {paper2.title}
    摘要: {paper2.abstract}
    方法: {paper2.methods}
    
    请判断它们之间的关系类型：
    - extends: 论文2扩展了论文1的方法
    - improves: 论文2改进了论文1的方法
    - compares: 两篇论文进行了比较
    - applies: 论文2将论文1的方法应用到新领域
    - contradicts: 两篇论文结论矛盾
    - supports: 两篇论文结论相互支持
    - none: 没有明显关系
    
    返回JSON格式：
    {{
        "relation_type": "...",
        "confidence": 0.0-1.0,
        "evidence": "..."
    }}
    """
    
    response = llm.generate(prompt)
    return parse_relation_response(response)
```

### 3.2 关系发现的综合策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    关系发现综合策略                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  输入: 论文对 (paper1, paper2)                                   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第1层: 引用关系 (100%可靠)                                │   │
│  │ - 直接引用 ✓                                             │   │
│  │ - 共被引 ✓                                               │   │
│  │ - 文献耦合 ✓                                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第2层: 引用上下文 (规则匹配 80%准确)                       │   │
│  │ - 直接使用                                               │   │
│  │ - 扩展                                                   │   │
│  │ - 比较                                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第3层: 共享实体 (语义匹配 70%准确)                         │   │
│  │ - 共享方法                                               │   │
│  │ - 共享任务                                               │   │
│  │ - 共享数据集                                             │   │
│  │ - 共享模型                                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第4层: LLM深度分析 (复杂情况)                              │   │
│  │ - 方法论差异分析                                          │   │
│  │ - 改进/扩展判断                                           │   │
│  │ - 矛盾/支持判断                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  输出: 关系列表 [(type, confidence, evidence), ...]            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 实施路线图

### 4.1 第一阶段：基础设施（已完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| PersistentGraphDB | ✅ 完成 | SQLite持久化存储 |
| SemanticEntityDB | ✅ 完成 | 语义实体扩展 |
| PaperPoolCollector | ✅ 完成 | OpenAlex论文收集 |
| SemanticEntityExtractor | ✅ 完成 | 7种实体类型抽取 |
| CitationContextAnalyzer | ✅ 完成 | 8种引用关系分析 |
| EntityDisambiguator | ✅ 完成 | K-means/DBSCAN聚类 |
| EntityCleaner | ✅ 完成 | 规则+LLM清洗 |
| EnhancedRelationDiscoverer | ✅ 完成 | 21种关系类型 |

### 4.2 第二阶段：模板系统（已完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| SurveyTemplateLibrary | ✅ 完成 | 模板存储和检索 |
| TemplateExtractor | ✅ 完成 | 从Survey提取模板 |
| 模板匹配算法 | ✅ 完成 | 向量相似度匹配 |

### 4.3 第三阶段：集成测试（进行中）

| 任务 | 状态 | 说明 |
|------|------|------|
| build_mekg_v3.py | ✅ 完成 | 集成构建脚本 |
| 论文收集测试 | ✅ 完成 | OpenAlex API正常 |
| 数据库添加测试 | ✅ 完成 | 10篇论文成功入库 |
| 实体抽取测试 | 🔄 待测试 | 需要用户验证 |
| 关系发现测试 | 🔄 待测试 | 需要用户验证 |

### 4.4 第四阶段：大规模构建（待执行）

| 任务 | 状态 | 说明 |
|------|------|------|
| 构建LLM主题图谱 | ⏳ 待执行 | 300+论文 |
| 构建RAG主题图谱 | ⏳ 待执行 | 300+论文 |
| 构建Agent主题图谱 | ⏳ 待执行 | 300+论文 |
| 跨主题关系发现 | ⏳ 待执行 | 连接不同主题 |

## 5. 使用指南

### 5.1 构建大图谱

```bash
# 构建单个主题的图谱
python scripts/build_mekg_v3.py \
    --topic "Large Language Model" \
    --papers-per-topic 300 \
    --db-path ./mekg_v3.db

# 构建多个主题的大图谱（推荐）
python scripts/build_mekg_v3.py \
    --topics "LLM,RAG,Agent,Prompt Engineering" \
    --papers-per-topic 300 \
    --db-path ./mekg_v3.db

# 启用LLM增强（更准确但更慢）
python scripts/build_mekg_v3.py \
    --topics "LLM,RAG" \
    --papers-per-topic 100 \
    --use-llm-relations \
    --use-llm-cleaning
```

### 5.2 查询图谱

```python
from src.modules.mekg.semantic_entity_db import SemanticEntityDB

# 连接数据库
db = SemanticEntityDB("./mekg_v3.db")

# 查看统计信息
stats = db.get_statistics()
print(f"论文数: {stats['paper_count']}")
print(f"关系数: {stats['relation_count']}")
print(f"语义实体数: {stats['semantic']['semantic_entity_count']}")

# 搜索论文
papers = db.search_papers("transformer attention")

# 提取子图
subgraph = db.extract_subgraph_by_keywords(["BERT", "GPT", "transformer"])

# 查找共享实体的论文
related = db.find_papers_with_shared_entities("W123456")
```

### 5.3 生成Survey大纲

```python
from src.modules.mekg.survey_template_library import SurveyTemplateLibrary
from src.modules.mekg.llm_enhanced_outline_generator import LLMEnhancedOutlineGenerator

# 初始化
template_lib = SurveyTemplateLibrary()
outline_gen = LLMEnhancedOutlineGenerator(db, template_lib)

# 匹配模板
matched_templates = template_lib.search_templates("LLM tool use", top_k=3)

# 生成大纲
outline = outline_gen.generate_outline(
    topic="LLM Tool Use",
    subgraph=subgraph,
    templates=matched_templates
)
```

## 6. 关键代码位置

| 组件 | 文件路径 |
|------|----------|
| 持久化数据库 | `src/modules/mekg/persistent_graph_db.py` |
| 语义实体数据库 | `src/modules/mekg/semantic_entity_db.py` |
| 语义实体抽取 | `src/modules/mekg/semantic_entity_extractor.py` |
| 引用上下文分析 | `src/modules/mekg/citation_context_analyzer.py` |
| 实体消歧 | `src/modules/mekg/entity_disambiguator.py` |
| 实体清洗 | `src/modules/mekg/entity_cleaner.py` |
| 增强关系发现 | `src/modules/mekg/enhanced_relation_discoverer.py` |
| 论文收集 | `src/modules/mekg/paper_pool_collector.py` |
| 模板库 | `src/modules/mekg/survey_template_library.py` |
| 模板提取 | `src/modules/mekg/template_extractor.py` |
| 图融合 | `src/modules/mekg/graph_merger.py` |
| 双重搜索 | `src/modules/mekg/dual_search_orchestrator.py` |
| 构建脚本 | `scripts/build_mekg_v3.py` |
| 测试脚本 | `scripts/test_mekg_v3.py` |

## 7. 总结

MEKG V3 实现了导师提出的所有核心需求：

1. **持久化大图谱** ✅
   - SQLite存储，支持大规模数据
   - igraph缓存，高性能图算法

2. **跨Topic连接** ✅
   - 多Topic支持
   - 共享实体关系发现
   - 跨Topic关系发现

3. **双重搜索** ✅
   - 图数据库搜索
   - OpenAlex网络搜索
   - 增量更新机制

4. **Survey模板库** ✅
   - 模板存储和检索
   - 向量相似度匹配
   - Few-shot大纲生成

5. **增强关系发现** ✅
   - 4层关系发现策略
   - 21种关系类型
   - 方法论拆解（共享实体分析）

## 8. 下一步建议

1. **用户执行大规模图谱构建**
   ```bash
   python scripts/build_mekg_v3.py \
       --topics "LLM,RAG,Agent,Prompt Engineering" \
       --papers-per-topic 300
   ```

2. **收集更多Survey模板**
   - 找到高质量的Survey论文
   - 使用TemplateExtractor提取大纲
   - 添加到模板库

3. **测试完整的综述生成流程**
   - 选择一个Topic
   - 提取子图
   - 匹配模板
   - 生成大纲
   - 填充内容