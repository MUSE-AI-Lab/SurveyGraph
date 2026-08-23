# MEKG V3 使用指南

## 概述

MEKG V3 是对原有MEKG系统的重大升级，借鉴了NLP-AKG的设计理念，增加了以下核心功能：

1. **语义实体抽取** - 从论文中抽取7种细粒度语义实体
2. **引用上下文分析** - 分析引用上下文确定论文间关系类型
3. **实体消歧** - 使用向量聚类合并相似实体
4. **实体清洗** - 验证和清洗抽取的实体
5. **共享实体关系发现** - 基于共享实体推断论文间关系

## 快速开始

### 1. 运行测试

首先确保所有功能正常：

```bash
python scripts/test_mekg_v3.py
```

预期输出：
```
============================================================
测试结果汇总
============================================================
  ✓ 通过: 语义实体抽取器
  ✓ 通过: 引用上下文分析器
  ✓ 通过: 实体消歧器
  ✓ 通过: 实体清洗器
  ✓ 通过: 语义实体数据库
  ✓ 通过: 共享实体检测

总计: 6 通过, 0 失败, 0 跳过

🎉 所有测试通过！MEKG V3 功能正常
```

### 2. 构建知识图谱

#### 构建单个topic的图谱

```bash
python scripts/build_mekg_v3.py --topic "Large Language Models" --papers-per-topic 50
```

#### 构建多个topic的大图谱

```bash
python scripts/build_mekg_v3.py --topics "LLM,RAG,Agent,Prompt Engineering" --papers-per-topic 30
```

#### 从文件读取topic列表

创建 `topics.txt` 文件：
```
Large Language Models
Retrieval Augmented Generation
AI Agents
Prompt Engineering
Chain of Thought
```

然后运行：
```bash
python scripts/build_mekg_v3.py --topics-file topics.txt --papers-per-topic 50
```

### 3. 查看图谱统计

```bash
python scripts/view_graph_stats.py --db-path ./mekg_v3.db
```

## 命令行参数详解

### build_mekg_v3.py

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--topic` | 单个研究主题 | - |
| `--topics` | 多个主题，逗号分隔 | - |
| `--topics-file` | 主题文件路径 | - |
| `--papers-per-topic` | 每个topic收集的论文数 | 50 |
| `--db-path` | 数据库路径 | ./mekg_v3.db |
| `--model` | LLM模型名称 | 配置文件默认值 |
| `--max-workers` | 最大并发数 | 10 |
| `--no-relations` | 不发现论文间关系 | False |
| `--no-entities` | 不抽取语义实体 | False |
| `--use-llm-relations` | 使用LLM分析引用关系 | False |
| `--use-llm-cleaning` | 使用LLM清洗实体 | False |
| `--export` | 导出格式 (json/graphml) | - |
| `--export-path` | 导出路径 | ./mekg_v3_export |

## 核心模块说明

### 1. 语义实体抽取器 (SemanticEntityExtractor)

从论文摘要中抽取7种语义实体：

| 实体类型 | 说明 | 示例 |
|----------|------|------|
| Problem | 论文解决的问题 | "Existing methods fail to capture long-range dependencies" |
| Method | 提出的方法 | "Transformer-based architecture with multi-head attention" |
| Model | 模型名称 | "BERT", "GPT-4" |
| Task | 应用任务 | "question answering", "text classification" |
| Dataset | 使用的数据集 | "SQuAD", "GLUE", "ImageNet" |
| Metric | 评估指标 | "accuracy", "F1-score", "BLEU" |
| Innovation | 主要创新点 | 自动生成的创新点总结 |

**使用示例：**

```python
from src.modules.mekg.semantic_entity_extractor import SemanticEntityExtractor
import asyncio

extractor = SemanticEntityExtractor()

paper = {
    "paper_id": "test_001",
    "title": "BERT: Pre-training of Deep Bidirectional Transformers",
    "abstract": "We introduce a new language representation model called BERT..."
}

# 异步抽取
entities = asyncio.run(extractor.extract_from_paper(paper))

print(f"Models: {[m.value for m in entities.models]}")
print(f"Tasks: {[t.value for t in entities.tasks]}")
print(f"Datasets: {[d.value for d in entities.datasets]}")
```

### 2. 引用上下文分析器 (CitationContextAnalyzer)

分析引用上下文，确定7种关系类型：

| 关系类型 | 说明 | 示例上下文 |
|----------|------|------------|
| direct_use | 直接使用 | "We use the dataset from [1]" |
| extends | 扩展 | "Our method extends [2] by adding..." |
| compares | 比较 | "Compared with [3], our approach achieves..." |
| task_related | 任务相关 | "Similar to [4], we also focus on..." |
| background | 背景 | "Transformers [5] have been widely used..." |
| supports | 支持 | "Consistent with [6], we found..." |
| refutes | 反驳 | "Contrary to [7], our results show..." |

**使用示例：**

```python
from src.modules.mekg.citation_context_analyzer import CitationContextAnalyzer

analyzer = CitationContextAnalyzer(use_llm=False)

context = "We use the dataset from [1] for our experiments."
relation = analyzer.analyze_context(context)

print(f"Relation type: {relation.relation_type}")
print(f"Confidence: {relation.confidence}")
```

### 3. 实体消歧器 (EntityDisambiguator)

使用向量聚类合并相似实体：

```python
from src.modules.mekg.entity_disambiguator import EntityDisambiguator

disambiguator = EntityDisambiguator()

entities = ["MNIST", "mnist", "MNIST dataset", "ImageNet", "imagenet"]
clusters = disambiguator.disambiguate(entities, "dataset")

# 输出: {'MNIST': ['MNIST', 'mnist', 'MNIST dataset'], 'ImageNet': ['ImageNet', 'imagenet']}
```

### 4. 实体清洗器 (EntityCleaner)

验证和清洗抽取的实体：

```python
from src.modules.mekg.entity_cleaner import EntityCleaner

cleaner = EntityCleaner(use_llm=False)

# 清洗数据集名称
is_valid, cleaned, error_type = cleaner.clean_entity("dataset: ImageNet", "dataset")
# 输出: (True, "ImageNet", "valid")

# 无效实体
is_valid, cleaned, error_type = cleaner.clean_entity("our custom dataset", "dataset")
# 输出: (False, "our custom dataset", "not_specific")
```

### 5. 语义实体数据库 (SemanticEntityDB)

扩展的数据库，支持语义实体存储：

```python
from src.modules.mekg.semantic_entity_db import SemanticEntityDB

db = SemanticEntityDB("./mekg_v3.db")

# 获取论文的语义实体
entities = db.get_paper_semantic_entities("paper_id")

# 获取包含特定实体的论文
papers = db.get_papers_by_entity("dataset", "ImageNet")

# 找到共享实体的论文
shared = db.find_papers_with_shared_entities("paper_id")

# 获取统计信息
stats = db.get_statistics()
```

## 数据库Schema

MEKG V3 在原有基础上新增了以下表：

### semantic_entities 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| paper_id | TEXT | 论文ID |
| entity_type | TEXT | 实体类型 |
| entity_value | TEXT | 实体值 |
| canonical_value | TEXT | 标准化值 |
| confidence | REAL | 置信度 |
| source | TEXT | 来源 |

### entity_clusters 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| entity_type | TEXT | 实体类型 |
| cluster_id | INTEGER | 聚类ID |
| entity_value | TEXT | 实体值 |
| is_representative | BOOLEAN | 是否为代表 |

### citation_contexts 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| citing_paper_id | TEXT | 引用论文ID |
| cited_paper_id | TEXT | 被引论文ID |
| context | TEXT | 引用上下文 |
| relation_type | TEXT | 关系类型 |
| confidence | REAL | 置信度 |

## 与导师建议的对应

| 导师建议 | MEKG V3 实现 |
|----------|--------------|
| 构建大图数据库 | SemanticEntityDB + PersistentGraphDB |
| 不同topic之间有交叉连接 | 跨topic关系发现 (_discover_cross_topic_relations) |
| 同步搜索图数据库和网络 | DualSearchOrchestrator |
| 拆解文章方法论 | 语义实体抽取 (Problem, Method, Model等) |
| 考虑共性 | 共享实体关系发现 |
| Survey大纲模板库 | SurveyTemplateLibrary + TemplateExtractor |

## 综述生成

### 一次性生成完整综述

使用 `generate_survey_from_mekg.py` 脚本可以基于已构建的MEKG V3知识图谱一次性生成完整的综述论文：

```bash
# 基本用法
python scripts/generate_survey_from_mekg.py \
    --topic "LLM Function Calling" \
    --db_path data/mekg_v3/llm_function_calling.db

# 指定输出目录
python scripts/generate_survey_from_mekg.py \
    --topic "LLM Function Calling" \
    --db_path data/mekg_v3/llm_function_calling.db \
    --output_dir outputs/my_survey

# 跳过PDF编译（仅生成LaTeX）
python scripts/generate_survey_from_mekg.py \
    --topic "LLM Function Calling" \
    --db_path data/mekg_v3/llm_function_calling.db \
    --skip_compile
```

### 生成流程

综述生成包含以下步骤：

1. **加载知识图谱** - 从SQLite数据库加载MEKG V3图谱
2. **导出论文数据** - 将论文导出为独立JSON文件
3. **生成学术大纲** - 使用LLM基于图谱结构生成大纲
4. **图谱驱动挂载** - 将论文挂载到对应章节
5. **生成参考文献** - 生成BibTeX格式的参考文献
6. **迭代式内容生成** - 逐章节生成综述内容
7. **编译PDF** - 使用LaTeX编译生成PDF

### 输出文件

生成完成后，输出目录结构如下：

```
outputs/survey_xxx_20241127_120000/
├── mekg/
│   └── mekg.json           # MEKG图谱JSON格式
├── outline/
│   ├── outlines.json       # 结构化大纲
│   └── outline.md          # Markdown格式大纲
├── papers/
│   └── *.json              # 论文数据文件
├── latex/
│   ├── survey.tex          # LaTeX源文件
│   └── references.bib      # 参考文献
├── content/
│   ├── mainbody.tex        # 正文内容
│   └── abstract.txt        # 摘要
├── tmp/                    # 临时文件
└── survey.pdf              # 最终PDF
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--topic` | 综述主题 | 必填 |
| `--db_path` | MEKG V3数据库路径 | 必填 |
| `--output_dir` | 输出目录 | 自动生成 |
| `--task_id` | 任务ID | 自动生成 |
| `--skip_compile` | 跳过PDF编译 | False |

## 完整工作流程

### 1. 构建知识图谱

```bash
# 构建单个topic的图谱
python scripts/build_mekg_v3.py \
    --topic "LLM Function Calling" \
    --papers-per-topic 300 \
    --db-path data/mekg_v3/llm_function_calling.db
```

### 2. 生成综述

```bash
# 基于图谱生成综述
python scripts/generate_survey_from_mekg.py \
    --topic "LLM Function Calling" \
    --db_path data/mekg_v3/llm_function_calling.db
```

### 3. 查看结果

生成完成后，可以在输出目录找到：
- `survey.pdf` - 最终的综述PDF
- `latex/survey.tex` - LaTeX源文件（可进一步编辑）
- `outline/outline.md` - 大纲预览

## 下一步操作

1. **构建大图谱**：选择几个相关的topic，构建一个覆盖多个领域的大图谱
   ```bash
   python scripts/build_mekg_v3.py --topics "LLM,RAG,Agent,Prompt Engineering,Chain of Thought" --papers-per-topic 100
   ```

2. **提取Survey模板**：从已有的优秀Survey论文中提取大纲模板
   ```bash
   python scripts/extract_survey_templates.py --survey-dir ./surveys --output ./templates
   ```

3. **生成综述**：使用构建好的图谱生成综述
   ```bash
   python scripts/generate_survey_from_mekg.py --topic "Your Topic" --db_path ./mekg_v3.db
   ```

## 常见问题

### Q: 论文收集失败怎么办？

A: 确保安装了 `pyalex` 包：
```bash
pip install pyalex
```

### Q: 语义实体抽取很慢怎么办？

A: 可以增加并发数或跳过实体抽取：
```bash
# 增加并发
python scripts/build_mekg_v3.py --topic "LLM" --max-workers 20

# 跳过实体抽取（只构建基础图谱）
python scripts/build_mekg_v3.py --topic "LLM" --no-entities
```

### Q: 如何查看图谱中的关系？

A: 使用统计脚本或直接查询数据库：
```bash
python scripts/view_graph_stats.py --db-path ./mekg_v3.db --show-relations
```

## 相关文件

- [`scripts/build_mekg_v3.py`](../scripts/build_mekg_v3.py) - MEKG V3 构建脚本
- [`scripts/test_mekg_v3.py`](../scripts/test_mekg_v3.py) - MEKG V3 测试脚本
- [`src/modules/mekg/semantic_entity_extractor.py`](../src/modules/mekg/semantic_entity_extractor.py) - 语义实体抽取器
- [`src/modules/mekg/citation_context_analyzer.py`](../src/modules/mekg/citation_context_analyzer.py) - 引用上下文分析器
- [`src/modules/mekg/entity_disambiguator.py`](../src/modules/mekg/entity_disambiguator.py) - 实体消歧器
- [`src/modules/mekg/entity_cleaner.py`](../src/modules/mekg/entity_cleaner.py) - 实体清洗器
- [`src/modules/mekg/semantic_entity_db.py`](../src/modules/mekg/semantic_entity_db.py) - 语义实体数据库
- [`README/MEKG_V3_改进方案_借鉴NLP-AKG.md`](./MEKG_V3_改进方案_借鉴NLP-AKG.md) - 详细设计文档