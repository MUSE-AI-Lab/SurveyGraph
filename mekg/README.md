# MEKG - Methods-Entity Knowledge Graph

**方法实体知识图谱** - 一个基于方法实体的学术知识图谱系统

## 📋 概述

MEKG (Methods-Entity Knowledge Graph) 是一个用于学术论文分析的知识图谱系统，通过结构化的知识图谱分析来替代传统的RAG向量召回方案，生成更有逻辑性的综述大纲。

### 核心特性

- 🚀 **大规模论文处理** - 支持1000-2000篇论文的高质量采集和分析
- 🧠 **深度语义理解** - 提取7种语义实体类型，识别21种关系类型
- 📊 **结构化分析** - 基于社区发现和演进路径的图谱分析
- ⚡ **高效并发处理** - 50线程并发下载、解析、属性提取
- 💰 **成本优化** - 使用DeepSeek-V3降低80%成本

## 📁 目录结构

```
mekg/
├── src/                         # 核心源代码
│   ├── core/                    # 核心数据结构
│   │   ├── data_structures.py   # MEKGGraph, MEKGNode, MEKGEdge
│   │   └── analyzer.py          # MEKGAnalyzer
│   │
│   ├── extraction/              # 实体和关系抽取
│   │   ├── semantic_entity_extractor.py    # 7种语义实体
│   │   ├── citation_context_analyzer.py    # 8种引用关系
│   │   ├── enhanced_relation_discoverer.py # 21种关系类型
│   │   └── ...
│   │
│   ├── processing/              # 数据处理
│   │   ├── entity_cleaner.py    # 实体清洗
│   │   ├── entity_disambiguator.py # 实体消歧
│   │   ├── pdf_processor.py     # PDF处理
│   │   └── paper_pool_collector.py # 论文收集
│   │
│   ├── storage/                 # 存储层
│   │   ├── semantic_entity_db.py # SQLite存储
│   │   ├── kuzu_graph_db.py     # Kuzu图数据库
│   │   └── memgraph_graph_db.py # Memgraph图数据库
│   │
│   ├── analysis/                # 图谱分析
│   │   ├── community_labeler.py # 社区标注
│   │   ├── igraph_adapter.py    # 高性能图算法
│   │   └── evaluation_metrics.py # 评估指标
│   │
│   ├── automation/              # 自动化构建
│   │   ├── incremental_builder.py # 增量构建
│   │   ├── crawler_manager.py   # 爬虫管理
│   │   └── pipeline_orchestrator.py # 流水线编排
│   │
│   └── visualization/           # 可视化
│       ├── graph_visualizer.py  # 图谱可视化
│       └── web/                 # Web前端
│
├── scripts/                     # 运行脚本
│   ├── build/                   # 构建脚本
│   ├── test/                    # 测试脚本
│   ├── tools/                   # 工具脚本
│   └── web/                     # Web服务脚本
│
├── webapp/                      # FastAPI Web应用
│   ├── app.py                   # FastAPI主应用
│   ├── static/                  # 静态文件
│   └── templates/               # Jinja2模板
│
├── docs/                        # 文档
│   ├── guides/                  # 使用指南
│   ├── design/                  # 设计文档
│   ├── technical/               # 技术文档
│   └── reports/                 # 报告文档
│
└── data/                        # 数据目录
```

## 🚀 快速开始

### 安装依赖

```bash
pip install networkx python-louvain httpx loguru

# 可选：高性能图算法
pip install igraph leidenalg

# 可选：Kuzu图数据库
pip install kuzu
```

### 基本使用

```python
from mekg import MEKGGraph, MEKGAnalyzer, SemanticEntityDB

# 1. 创建/加载图谱
graph = MEKGGraph()

# 2. 连接数据库
db = SemanticEntityDB("./mekg.db")

# 3. 分析图谱
analyzer = MEKGAnalyzer(graph)
communities = analyzer.detect_communities()
top_papers = analyzer.get_top_papers("pagerank", 10)
```

### 构建图谱

```bash
# 构建单个主题的图谱
python mekg/scripts/build/build_mekg_v3.py \
    --topic "Large Language Models" \
    --papers-per-topic 300

# 构建多个主题的大图谱
python mekg/scripts/build/build_mekg_v3.py \
    --topics "LLM,RAG,Agent" \
    --papers-per-topic 300
```

### 启动Web控制台

```bash
# 启动企业级控制台
python mekg/scripts/web/start_enterprise.py

# 访问 http://localhost:8770
```

## 📊 语义实体类型

MEKG支持7种语义实体类型：

| 类型 | 说明 | 示例 |
|------|------|------|
| `PROBLEM` | 研究问题 | "text classification" |
| `METHOD` | 方法/技术 | "attention mechanism" |
| `MODEL` | 模型/架构 | "BERT", "GPT" |
| `TASK` | 任务 | "question answering" |
| `DATASET` | 数据集 | "SQuAD", "GLUE" |
| `METRIC` | 评估指标 | "F1 score", "BLEU" |
| `INNOVATION` | 创新点 | "bidirectional training" |

## 🔗 关系类型

MEKG支持21种关系类型，分为5大类：

### 结构关系
- `cites` - 引用
- `cited_by` - 被引用
- `co_cited` - 共被引
- `bibliographic_coupling` - 文献耦合

### 语义关系
- `extends` - 扩展
- `improves` - 改进
- `compares` - 比较
- `applies` - 应用
- `contradicts` - 矛盾
- `supports` - 支持

### 概念关系
- `shares_method` - 共享方法
- `shares_task` - 共享任务
- `shares_dataset` - 共享数据集
- `shares_model` - 共享模型
- `shares_problem` - 共享问题

### 时间关系
- `precedes` - 时间先于
- `follows` - 时间后于
- `contemporary` - 同时期

### 作者关系
- `same_author` - 同作者
- `same_venue` - 同会议/期刊
- `same_institution` - 同机构

## 📈 评估指标

MEKG提供三个核心评估指标：

- **WCR (Weighted Centrality Recall)** - 加权中心性召回率
- **CC (Community Coverage)** - 社区覆盖率
- **SC (Structural Coherence)** - 结构一致性

## 📚 文档

- [快速开始指南](docs/guides/MEKG_快速开始指南.md)
- [完整运行指南](docs/guides/MEKG_完整运行指南.md)
- [V3架构设计](docs/design/MEKG_V3_完整架构设计.md)
- [技术文档](docs/technical/MEKG_技术文档_CCF-A论文参考.md)
- [知识图谱调研报告](docs/reports/MEKG知识图谱调研报告.md)

## 🏗️ 系统架构

```
用户输入Topic
    ↓
┌─────────────────────────────────────────────┐
│  智能关键词处理 (IntelligentQueryProcessor) │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  多关键词搜索 + 雪球采样 (OpenAlex API)      │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  PDF下载与解析 (PDFProcessor)               │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  语义实体抽取 (SemanticEntityExtractor)     │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  关系发现 (EnhancedRelationDiscoverer)      │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  图谱分析 (MEKGAnalyzer)                    │
│  - PageRank中心性                            │
│  - 社区发现 (Louvain/Leiden)                │
│  - 演进路径追踪                              │
└─────────────────────────────────────────────┘
    ↓
输出: MEKG知识图谱 + 分析报告
```

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交Issue和Pull Request！

---

**MEKG Team** - 让学术研究更智能