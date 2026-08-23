# MEKG V2: 持久化图数据库与Survey模板库设计方案

> **版本**: 2.0  
> **日期**: 2025-11-25  
> **目标**: 构建可复用的大规模知识图谱系统，支持跨Topic子图提取和Survey大纲模板匹配

---

## 📋 目录

1. [需求分析](#1-需求分析)
2. [整体架构](#2-整体架构)
3. [持久化图数据库](#3-持久化图数据库)
4. [Survey模板库](#4-survey模板库)
5. [增强关系发现](#5-增强关系发现)
6. [子图提取与融合](#6-子图提取与融合)
7. [实施路线图](#7-实施路线图)
8. [代码复用分析](#8-代码复用分析)

---

## 1. 需求分析

### 1.1 导师核心需求

| 需求 | 描述 | 优先级 |
|------|------|--------|
| **持久化图数据库** | 构建类似Neo4j的大图，覆盖多topic，支持快速子图提取 | P0 |
| **跨Topic连接** | 不同topic的知识图谱要互相有交叉连接 | P0 |
| **双重搜索** | 同时搜索图数据库（已有知识）和网络（最新论文） | P0 |
| **Survey模板库** | 从好的survey提取大纲模板，用于RAG匹配和Few-shot | P1 |
| **层次化知识** | topic → 分类 → 方法，构建树状/图状结构 | P1 |
| **增强关系发现** | 不仅引用关系，还要方法论共性、拆解分析 | P1 |

### 1.2 现有系统 vs 目标系统

```
【当前系统】每次独立构建，无法复用
  Topic A → 构建MEKG_A → 生成Survey → (MEKG_A丢弃)
  Topic B → 构建MEKG_B → 生成Survey → (MEKG_B丢弃)

【目标系统】持久化大图，增量构建，跨Topic复用
  ┌─────────────────────────────────────────────┐
  │            持久化大图数据库                  │
  │  ┌───────┐   ┌───────┐   ┌───────┐        │
  │  │Topic A│←─→│Topic B│←─→│Topic C│        │
  │  │ 子图  │   │ 子图  │   │ 子图  │        │
  │  └───────┘   └───────┘   └───────┘        │
  │       ↑          ↑          ↑              │
  │       └──────────┼──────────┘              │
  │            共享节点和边                     │
  └─────────────────────────────────────────────┘
                     ↓
  新Topic → 搜索图数据库 + 网络 → 融合 → 匹配模板 → 生成Survey
```

### 1.3 可复用组件分析

| 组件 | 位置 | 复用方式 |
|------|------|----------|
| `PaperPoolCollector` | `mekg/paper_pool_collector.py` | ✅ 直接复用 |
| `CitationNetworkBuilder` | `mekg/citation_network_builder.py` | ✅ 直接复用 |
| `CorePaperDiscoverer` | `mekg/core_paper_discoverer.py` | ✅ 直接复用 |
| `AttributeBasedRelationExtractor` | `mekg/attribute_based_relation_extractor.py` | 🔧 扩展增强 |
| `IntelligentCandidateGenerator` | `mekg/intelligent_candidate_generator.py` | 🔧 扩展增强 |
| `MEKGAnalyzer` | `mekg/analyzer.py` | ✅ 直接复用 |
| `DualLoopMEKGBuilder` | `mekg/dual_loop_builder.py` | 🔧 重构适配 |

---

## 2. 整体架构

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     MEKG V2 系统架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【用户层】                                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐              │
│  │ Topic输入 │  │ Survey生成│  │ 图谱浏览  │              │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘              │
│        └──────────────┼──────────────┘                     │
│                       ↓                                     │
│  【协调层】 DualSearchOrchestrator                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ┌─────────────┐        ┌─────────────┐            │   │
│  │  │ 图数据库搜索│   +    │ 网络搜索    │            │   │
│  │  │ (已有知识)  │        │ (最新论文)  │            │   │
│  │  └─────────────┘        └─────────────┘            │   │
│  └─────────────────────────────────────────────────────┘   │
│                       ↓                                     │
│  【服务层】                                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ 图数据库   │ │ 模板库     │ │ 关系发现   │             │
│  │ 服务       │ │ 服务       │ │ 服务       │             │
│  │ - 节点CRUD │ │ - 模板提取 │ │ - 引用分析 │             │
│  │ - 子图提取 │ │ - 模板匹配 │ │ - 方法共性 │             │
│  │ - 图融合   │ │ - Few-shot │ │ - LLM增强  │             │
│  └────────────┘ └────────────┘ └────────────┘             │
│                       ↓                                     │
│  【存储层】                                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ SQLite     │ │ ChromaDB   │ │ 文件系统   │             │
│  │ (图结构)   │ │ (向量)     │ │ (PDF/文本) │             │
│  └────────────┘ └────────────┘ └────────────┘             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心流程

```
新Topic Survey生成流程:

1. 输入Topic: "Large Language Model Agents"
                    ↓
2. 双重搜索 (并行执行)
   ├─→ 图数据库搜索
   │   ├─ 关键词匹配
   │   ├─ 语义相似度
   │   └─ 邻域扩展 (2跳)
   │   → 返回: 已有论文500篇
   │
   └─→ 网络搜索 (OpenAlex)
       ├─ 搜索2023-2024最新论文
       └─ 补充图数据库缺失
       → 返回: 新论文200篇
                    ↓
3. 子图融合
   ├─ 合并去重: 700篇
   ├─ 新论文入库
   ├─ 补充关系
   └─ 标记Topic关联
                    ↓
4. 模板匹配
   ├─ 向量检索相似Survey模板
   ├─ 选择Top-3模板
   └─ 构建Few-shot Prompt
                    ↓
5. 大纲生成
   ├─ 输入: 子图 + 模板
   └─ LLM生成层次化大纲
                    ↓
6. Survey写作
```

---

## 3. 持久化图数据库

### 3.1 数据库Schema

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
    openalex_id TEXT UNIQUE,
    pagerank REAL DEFAULT 0.0,
    community_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 论文属性表 (JSON灵活存储)
CREATE TABLE paper_attributes (
    paper_id TEXT PRIMARY KEY,
    paper_type TEXT,
    method_info JSON,
    innovations JSON,
    research_domains JSON,
    application_scenarios JSON,
    has_pdf BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- 语义关系表
CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    evidence TEXT,
    UNIQUE(source_id, target_id, relation_type)
);

-- 引用关系表
CREATE TABLE citations (
    citing_id TEXT NOT NULL,
    cited_id TEXT NOT NULL,
    PRIMARY KEY (citing_id, cited_id)
);

-- Topic表
CREATE TABLE topics (
    topic TEXT PRIMARY KEY,
    keywords JSON,
    paper_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Topic-论文关联
CREATE TABLE topic_papers (
    topic TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    relevance_score REAL DEFAULT 1.0,
    is_core BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (topic, paper_id)
);

-- 索引
CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);

-- 全文搜索
CREATE VIRTUAL TABLE papers_fts USING fts5(paper_id, title, abstract);
```

### 3.2 目录结构

```
data/
├── graph_db/
│   ├── mekg_v2.db              # SQLite主数据库
│   └── cache/
│       └── igraph_cache.pkl    # 内存图缓存
├── papers/
│   ├── pdfs/{paper_id}.pdf
│   ├── texts/{paper_id}.txt
│   └── metadata/{paper_id}.json
├── templates/
│   ├── templates.db
│   └── chroma/                 # 向量存储
└── outputs/
    └── {topic}_{timestamp}/
```

### 3.3 图数据库服务接口

```python
class PersistentGraphDB:
    """持久化图数据库"""
    
    # 节点操作
    def add_paper(self, paper: Dict) -> bool
    def add_papers_batch(self, papers: List[Dict]) -> int
    def get_paper(self, paper_id: str) -> Optional[Dict]
    def paper_exists(self, paper_id: str) -> bool
    
    # 边操作
    def add_relation(self, source, target, type, confidence)
    def add_citation(self, citing, cited)
    
    # Topic操作
    def add_topic(self, topic, keywords)
    def link_paper_to_topic(self, paper_id, topic, relevance, is_core)
    def get_topic_papers(self, topic) -> List[str]
    
    # 子图提取
    def extract_subgraph_by_topic(self, topic, expand_hops=2) -> SubGraph
    def extract_subgraph_by_keywords(self, keywords, max_papers=500) -> SubGraph
    
    # 图算法
    def compute_pagerank() -> Dict[str, float]
    def detect_communities() -> Dict[str, int]
```

---

## 4. Survey模板库

### 4.1 模板类型

根据导师建议，总结常见Survey架构：

**类型1: 范式导向型**
```
LLM Tool Use Survey
├── Introduction
├── Background
├── Paradigm of Tool Use
│   ├── Tool Definition
│   ├── Tool Selection
│   └── Tool Execution
├── Fine-tuning Approaches
├── In-context Learning
├── Applications
└── Conclusion
```

**类型2: 方法论导向型**
```
Graph Neural Networks Survey
├── Introduction
├── Preliminaries
├── Spectral Methods
├── Spatial Methods
├── Hybrid Methods
├── Applications
└── Conclusion
```

**类型3: 问题导向型**
```
LLM Hallucination Survey
├── Introduction
├── Definition and Taxonomy
├── Causes of Hallucination
├── Detection Methods
├── Mitigation Strategies
├── Evaluation
└── Conclusion
```

**类型4: 时间线导向型**
```
Pre-trained Language Models Survey
├── Introduction
├── Early Approaches (2013-2017)
├── Contextualized (2018-2019)
├── Large Language Models (2020+)
├── Current Trends
└── Conclusion
```

### 4.2 模板数据结构

```python
@dataclass
class SurveyTemplate:
    template_id: str
    source_paper_title: str
    topic: str
    template_type: str  # paradigm/methodology/problem/timeline
    sections: List[OutlineSection]
    year: int
    citation_count: int
    quality_score: float

@dataclass
class OutlineSection:
    level: int  # 1, 2, 3
    title: str
    description: str
    keywords: List[str]
    subsections: List['OutlineSection']
```

### 4.3 模板匹配流程

```
1. 模板提取 (离线)
   Survey PDF → LLM提取大纲 → 结构化模板 → 存储

2. 模板匹配 (在线)
   新Topic → Embedding → 向量检索 → Top-K模板

3. Few-shot生成
   模板示例 + 图谱上下文 → LLM → 新大纲
```

---

## 5. 增强关系发现

### 5.1 多维度关系发现

导师指出只考虑引用关系不够，需要更全面的关系发现：

```
维度1: 引用关系 (Citation-based)
├─ 直接引用: A cites B
├─ 文献耦合: A和B引用相同论文
└─ 同被引: A和B被相同论文引用

维度2: 方法论共性 (Methodology-based) [新增]
├─ 方法类别相同: 都是Transformer-based
├─ 技术栈相似: 都用Attention机制
├─ 问题设定相似: 都解决长文本问题
└─ 评估方式相似: 都在GLUE上评测

维度3: 演进关系 (Evolution-based)
├─ 版本演进: GPT → GPT-2 → GPT-3
├─ 改进关系: B改进了A的缺陷
└─ 扩展关系: B将A扩展到新领域

维度4: 应用关系 (Application-based)
├─ 相同应用场景
├─ 相同数据集
└─ 相同基准对比
```

### 5.2 关系类型定义

```python
class RelationType(Enum):
    # 引用关系
    CITES = "cites"
    
    # 方法关系
    EMPLOYS = "employs"           # A采用B的方法
    EVOLVED_FROM = "evolved_from" # A是B的演进
    EXTENDS = "extends"           # A扩展了B
    IMPROVES = "improves"         # A改进了B
    
    # 类型关系
    IS_A_TYPE_OF = "is_a_type_of"
    IS_VARIANT_OF = "is_variant_of"
    
    # 应用关系
    IS_APPLIED_TO = "is_applied_to"
    SHARES_APPLICATION = "shares_application"
    
    # 共性关系
    SHARES_METHODOLOGY = "shares_methodology"
    SHARES_DATASET = "shares_dataset"
```

### 5.3 增强关系发现器

```python
class EnhancedRelationDiscoverer:
    """增强的关系发现器"""
    
    async def discover_relations(self, paper_a, paper_b) -> List[Relation]:
        relations = []
        
        # 维度1: 引用关系 (无需LLM)
        citation_rel = self._check_citation(paper_a, paper_b)
        if citation_rel:
            relations.append(citation_rel)
        
        # 维度2: 方法论共性 (规则 + LLM)
        method_rel = await self._analyze_methodology(paper_a, paper_b)
        if method_rel:
            relations.append(method_rel)
        
        # 维度3: 演进关系 (LLM)
        evolution_rel = await self._detect_evolution(paper_a, paper_b)
        if evolution_rel:
            relations.append(evolution_rel)
        
        # 维度4: 应用关系 (规则)
        app_rel = self._check_application(paper_a, paper_b)
        if app_rel:
            relations.append(app_rel)
        
        return relations
```

---

## 6. 子图提取与融合

### 6.1 子图提取策略

```python
class SubgraphExtractor:
    """子图提取器"""
    
    def extract_by_topic(self, topic, expand_hops=2, max_nodes=1000):
        """
        基于Topic提取子图
        
        1. 获取Topic关联的种子论文
        2. 扩展N跳邻居
        3. 按PageRank裁剪到max_nodes
        4. 保留子图内部的边
        """
        seed_papers = self.db.get_topic_papers(topic)
        
        all_papers = set(seed_papers)
        frontier = set(seed_papers)
        
        for hop in range(expand_hops):
            next_frontier = set()
            for paper_id in frontier:
                neighbors = self.db.get_neighbors(paper_id)
                next_frontier.update(neighbors)
            all_papers.update(next_frontier)
            frontier = next_frontier - all_papers
        
        # 裁剪
        if len(all_papers) > max_nodes:
            scored = [(self.db.get_pagerank(p), p) for p in all_papers]
            scored.sort(reverse=True)
            all_papers = set(p for _, p in scored[:max_nodes])
        
        edges = self.db.get_internal_edges(all_papers)
        return SubGraph(nodes=list(all_papers), edges=edges)
```

### 6.2 图融合策略

```python
class GraphMerger:
    """图融合器"""
    
    def merge_new_papers(self, new_papers, topic):
        """
        将新论文融合到大图
        
        1. 去重: 检查paper_id是否已存在
        2. 入库: 添加新节点
        3. 关联: 标记Topic关联
        4. 补边: 发现新论文与已有论文的关系
        """
        added_count = 0
        
        for paper in new_papers:
            if not self.db.paper_exists(paper['paper_id']):
                self.db.add_paper(paper)
                added_count += 1
            
            # 关联到Topic
            self.db.link_paper_to_topic(
                paper['paper_id'], 
                topic,
                relevance=paper.get('relevance', 1.0)
            )
        
        # 补充关系
        await self._discover_relations_for_new_papers(new_papers)
        
        return added_count
```

---

## 7. 实施路线图

### 7.1 阶段划分

```
阶段1: 持久化图数据库 (2周)
├─ 实现PersistentGraphDB
├─ 实现SQLite存储层
├─ 实现igraph内存层
└─ 测试基本CRUD和子图提取

阶段2: 双重搜索机制 (1周)
├─ 实现DualSearchOrchestrator
├─ 集成图数据库搜索
├─ 集成OpenAlex网络搜索
└─ 实现结果融合

阶段3: Survey模板库 (2周)
├─ 实现TemplateExtractor
├─ 实现SurveyTemplateLibrary
├─ 集成ChromaDB向量存储
├─ 实现模板匹配
└─ 收集10-20个高质量Survey模板

阶段4: 增强关系发现 (1周)
├─ 实现EnhancedRelationDiscoverer
├─ 添加方法论共性分析
├─ 添加演进关系检测
└─ 集成到图构建流程

阶段5: 集成测试 (1周)
├─ 端到端测试
├─ 性能优化
└─ 文档完善
```

### 7.2 里程碑

| 里程碑 | 时间 | 交付物 |
|--------|------|--------|
| M1 | Week 2 | 持久化图数据库可用 |
| M2 | Week 3 | 双重搜索机制可用 |
| M3 | Week 5 | 模板库可用，含10+模板 |
| M4 | Week 6 | 增强关系发现可用 |
| M5 | Week 7 | 完整系统集成测试通过 |

### 7.3 优先级排序

```
P0 (必须):
├─ 持久化图数据库
├─ 子图提取
└─ 双重搜索

P1 (重要):
├─ Survey模板库
├─ 模板匹配
└─ 增强关系发现

P2 (可选):
├─ 图谱可视化
└─ Web界面
```

---

## 8. 代码复用分析

### 8.1 直接复用

```python
# 这些组件可以直接复用，无需修改

from src.modules.mekg.paper_pool_collector import PaperPoolCollector
from src.modules.mekg.citation_network_builder import CitationNetworkBuilder
from src.modules.mekg.core_paper_discoverer import CorePaperDiscoverer
from src.modules.mekg.analyzer import MEKGAnalyzer
```

### 8.2 需要扩展

```python
# AttributeBasedRelationExtractor
# 扩展: 添加方法论共性分析、演进关系检测

# IntelligentCandidateGenerator
# 扩展: 支持从持久化图数据库生成候选对

# DualLoopMEKGBuilder
# 重构: 适配持久化存储，支持增量构建
```

### 8.3 需要新增

```python
# 新增组件
src/modules/mekg/
├── persistent_graph_db.py      # 持久化图数据库
├── subgraph_extractor.py       # 子图提取器
├── graph_merger.py             # 图融合器
├── dual_search_orchestrator.py # 双重搜索协调器
├── survey_template_library.py  # 模板库
├── template_extractor.py       # 模板提取器
└── enhanced_relation_discoverer.py # 增强关系发现
```

---

## 总结

本设计方案针对导师提出的需求，设计了MEKG V2系统：

1. **持久化图数据库**: 使用SQLite + igraph分层存储，支持大规模图的持久化和高效查询
2. **跨Topic连接**: 通过Topic-论文关联表和共享节点实现跨Topic连接
3. **双重搜索**: 同时搜索图数据库和网络，确保知识复用和时效性
4. **Survey模板库**: 从优秀Survey提取模板，用于Few-shot大纲生成
5. **增强关系发现**: 多维度关系发现，不仅限于引用关系

预计实施周期: 7周