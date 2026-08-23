# MEKG V2 完整使用指南

## 📋 目录

1. [系统概述](#系统概述)
2. [快速开始](#快速开始)
3. [查看图谱统计](#查看图谱统计)
4. [扩充大图谱](#扩充大图谱)
5. [收集Survey模板](#收集survey模板)
6. [生成综述](#生成综述)
7. [高级功能](#高级功能)
8. [常见问题](#常见问题)

---

## 系统概述

MEKG V2 是一个基于知识图谱的学术综述自动生成系统，主要特点：

- **持久化图数据库**: 类似Neo4j的图存储，支持跨Topic的知识复用
- **双重搜索**: 图数据库搜索 + 网络搜索（OpenAlex），确保获取最新论文
- **21种关系类型**: 学术严谨的关系体系（结构、语义、概念、时序、作者）
- **Survey模板库**: 从优秀survey中提取大纲模板，指导生成
- **50线程并发**: 高效的关系发现

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                      MEKG V2 系统架构                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 持久化图DB  │  │ Survey模板库 │  │ 双重搜索协调器      │  │
│  │ (SQLite+    │  │ (向量检索)   │  │ (图DB+OpenAlex)    │  │
│  │  igraph)    │  │             │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│         │                │                    │              │
│         └────────────────┼────────────────────┘              │
│                          ▼                                   │
│              ┌─────────────────────┐                        │
│              │  增强关系发现器      │                        │
│              │  (21种关系,50线程)  │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 环境准备

```bash
# 确保在项目根目录
cd d:/SurveyY-real_time

# 激活虚拟环境
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖（如果需要）
pip install pyvis  # 可视化
pip install pymupdf  # PDF处理
```

### 2. 查看现有图谱

```bash
# 查看统计信息
python scripts/view_graph_stats.py --action stats

# 生成可视化
python scripts/view_graph_stats.py --action visualize --topic "LLM Function Calling"

# 导出数据
python scripts/view_graph_stats.py --action export --topic "LLM Function Calling"
```

### 3. 一键生成综述

```bash
# 基础用法
python scripts/generate_survey_v2.py --topic "LLM Function Calling"

# 完整功能（推荐）
python scripts/generate_survey_v2.py \
    --topic "LLM Function Calling" \
    --discover-relations \
    --visualize \
    --max-papers 100
```

---

## 查看图谱统计

### 命令

```bash
python scripts/view_graph_stats.py [选项]
```

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--db` | 数据库路径 | `data/graph_db/mekg_v2.db` |
| `--action` | 操作类型: stats/visualize/export/all | `stats` |
| `--topic` | 指定Topic | 无（全部） |
| `--output` | 输出路径 | 自动生成 |
| `--max-nodes` | 可视化最大节点数 | 200 |

### 示例

```bash
# 查看统计
python scripts/view_graph_stats.py --action stats

# 输出示例:
# ============================================================
# 📊 MEKG V2 图谱统计信息
# ============================================================
# 📁 数据库路径: data/graph_db/mekg_v2.db
# 💾 数据库大小: 15.23 MB
# 📄 论文总数: 591
# 🔗 语义关系数: 62
# 📚 引用关系数: 1820
# 🏷️ Topic数: 1
# 📅 年份范围: 2017 - 2024
# ============================================================

# 生成可视化（需要安装pyvis）
python scripts/view_graph_stats.py --action visualize --topic "LLM Function Calling" --max-nodes 100

# 导出JSON数据
python scripts/view_graph_stats.py --action export --topic "LLM Function Calling"

# 执行所有操作
python scripts/view_graph_stats.py --action all --topic "LLM Function Calling"
```

---

## 扩充大图谱

### 命令

```bash
python scripts/build_large_graph.py [选项]
```

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--topics` | Topic列表（空格分隔） | 无 |
| `--config` | Topic配置文件路径（JSON） | 无 |
| `--db-path` | 数据库路径 | `data/graph_db/mekg_v2.db` |
| `--papers-per-topic` | 每个Topic目标论文数 | 200 |
| `--year-start` | 起始年份 | 2020 |
| `--year-end` | 结束年份 | 2024 |
| `--no-relations` | 不发现关系（默认会发现） | False |
| `--enrich-cited-by` | 获取被引信息（较慢） | False |
| `--use-defaults` | 使用默认5个Topic配置 | False |

### 示例

```bash
# 使用默认配置（5个预设Topic，推荐首次使用）
python scripts/build_large_graph.py --use-defaults

# 添加单个Topic
python scripts/build_large_graph.py --topics "LLM Agents" --papers-per-topic 300

# 添加多个Topic（建立跨Topic连接）
python scripts/build_large_graph.py \
    --topics "LLM Agents" "Retrieval Augmented Generation" "Prompt Engineering" \
    --papers-per-topic 200

# 不发现关系（更快）
python scripts/build_large_graph.py \
    --topics "LLM Agents" \
    --papers-per-topic 300 \
    --no-relations

# 推荐的Topic组合（相关性高，容易建立连接）
python scripts/build_large_graph.py \
    --topics \
    "LLM Function Calling" \
    "LLM Agents" \
    "Tool Learning" \
    "Retrieval Augmented Generation" \
    "Prompt Engineering" \
    "In-Context Learning" \
    --papers-per-topic 200
```

### 默认Topic配置

使用 `--use-defaults` 时会构建以下5个Topic：

1. **Large Language Model Agents** - 关键词: LLM agent, language model agent, AI agent, autonomous agent
2. **LLM Tool Calling** - 关键词: tool calling, function calling, tool use, API calling
3. **Retrieval Augmented Generation** - 关键词: RAG, retrieval augmented, knowledge retrieval
4. **Prompt Engineering** - 关键词: prompt engineering, prompt optimization, in-context learning
5. **LLM Fine-tuning** - 关键词: LLM fine-tuning, instruction tuning, RLHF

### 建议的Topic列表

以下Topic之间有较强的关联性，适合一起构建：

**LLM应用方向**:
- LLM Function Calling
- LLM Agents
- Tool Learning
- Retrieval Augmented Generation

**LLM技术方向**:
- Prompt Engineering
- In-Context Learning
- Chain of Thought
- Instruction Tuning

**多模态方向**:
- Vision Language Models
- Multimodal LLM
- Image Captioning

---

## 收集Survey模板

### 命令

```bash
python scripts/extract_survey_templates.py [选项]
```

### 选项

| 选项 | 说明 |
|------|------|
| `--list` | 列出所有模板 |
| `--add-examples` | 添加示例模板（3个预设模板） |
| `--auto-search` | **【推荐】自动从网络搜索survey并提取模板** |
| `--topic` | 单个Topic名称 |
| `--topics` | 多个Topic（空格分隔） |
| `--max-surveys` | 每个topic最多搜索的survey数量（默认3） |
| `--manual` | 手动添加模板 |
| `--pdf` | 从PDF提取 |
| `--md` | 从Markdown提取 |
| `--db` | 模板库路径 |

### 示例

```bash
# 1. 【推荐】自动搜索并提取模板（单个topic）
python scripts/extract_survey_templates.py --auto-search --topic "LLM Agents"

# 2. 【推荐】批量自动搜索多个topic
python scripts/extract_survey_templates.py --auto-search \
    --topics "LLM Agents" "RAG" "Tool Learning" "Prompt Engineering" \
    --max-surveys 2

# 3. 查看已有模板
python scripts/extract_survey_templates.py --list

# 4. 添加预设示例模板
python scripts/extract_survey_templates.py --add-examples

# 5. 手动添加模板
python scripts/extract_survey_templates.py --manual --topic "LLM Agents"
# 然后按提示输入大纲结构

# 6. 从PDF提取（需要安装pymupdf）
python scripts/extract_survey_templates.py --pdf path/to/survey.pdf --topic "RAG"

# 5. 从Markdown提取
python scripts/extract_survey_templates.py --md path/to/survey.md --topic "Tool Learning"
```

### 手动添加模板示例

```bash
python scripts/extract_survey_templates.py --manual --topic "LLM Agents"

# 输入示例（每行一个章节，用#表示层级）:
# Introduction
## Background
## Motivation
# Agent Architecture
## Planning
## Memory
## Tool Use
# Applications
## Single Agent
## Multi Agent
# Evaluation
# Conclusion
# （输入空行结束）
```

---

## 生成综述

### 命令

```bash
python scripts/generate_survey_v2.py [选项]
```

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--topic` | 综述主题 | 必填 |
| `--db` | 图数据库路径 | `data/graph_db/mekg_v2.db` |
| `--template-db` | 模板库路径 | `data/templates/survey_templates.db` |
| `--output-dir` | 输出目录 | `src/outputs/` |
| `--max-papers` | 最大论文数 | 100 |
| `--discover-relations` | 启用关系发现 | False |
| `--max-workers` | 并发线程数 | 50 |
| `--visualize` | 生成可视化 | False |
| `--skip-network-search` | 跳过网络搜索 | False |

### 示例

```bash
# 基础用法
python scripts/generate_survey_v2.py --topic "LLM Function Calling"

# 完整功能（推荐）
python scripts/generate_survey_v2.py \
    --topic "LLM Function Calling" \
    --discover-relations \
    --visualize \
    --max-papers 100

# 只使用图数据库（不搜索网络）
python scripts/generate_survey_v2.py \
    --topic "LLM Function Calling" \
    --skip-network-search

# 自定义输出目录
python scripts/generate_survey_v2.py \
    --topic "LLM Agents" \
    --output-dir "outputs/my_survey" \
    --discover-relations
```

### 输出文件

生成的文件位于 `src/outputs/YYYY-MM-DD-HHMM_topic/`:

```
src/outputs/2024-01-15-1430_llm_function_calling/
├── survey.tex          # LaTeX源文件
├── references.bib      # 参考文献
├── outline.json        # 大纲结构
├── papers.json         # 使用的论文列表
├── knowledge_graph.html # 知识图谱可视化（如果启用）
└── logs/               # 日志文件
```

---

## 高级功能

### 1. 提取子图谱

```bash
python scripts/extract_survey_subgraph.py \
    --topic "LLM Function Calling" \
    --expand-hops 2 \
    --max-nodes 500 \
    --output subgraph.json
```

### 2. 计算图指标

```bash
# 在build_large_graph.py中启用
python scripts/build_large_graph.py \
    --topics "LLM Agents" \
    --compute-metrics

# 这会计算:
# - PageRank（论文重要性）
# - 社区发现（论文聚类）
```

### 3. 关系发现详情

关系发现支持21种关系类型：

**结构关系（4种）**:
- cites, cited_by, co_citation, bibliographic_coupling

**语义关系（8种，需要LLM）**:
- extends, improves, applies, compares, combines, reproduces, refutes, supports

**概念关系（7种）**:
- is_variant_of, is_instance_of, shares_methodology, shares_task, shares_dataset, shares_baseline, shares_architecture

**时序关系（3种）**:
- precedes, succeeds, concurrent

**作者关系（2种）**:
- same_author, same_group

### 4. 自定义数据库路径

```bash
# 使用自定义数据库
python scripts/build_large_graph.py \
    --topics "My Topic" \
    --db "data/my_custom_db.db"

python scripts/generate_survey_v2.py \
    --topic "My Topic" \
    --db "data/my_custom_db.db"
```

---

## 常见问题

### Q1: 如何查看当前图谱有哪些Topic？

```bash
python scripts/view_graph_stats.py --action stats
# 会显示所有Topic及其论文数
```

### Q2: 关系发现很慢怎么办？

```bash
# 减少并发数
python scripts/generate_survey_v2.py \
    --topic "LLM Agents" \
    --discover-relations \
    --max-workers 20

# 或者跳过关系发现
python scripts/generate_survey_v2.py \
    --topic "LLM Agents"
```

### Q3: 如何只使用已有图谱，不搜索网络？

```bash
python scripts/generate_survey_v2.py \
    --topic "LLM Function Calling" \
    --skip-network-search
```

### Q4: 可视化报错怎么办？

```bash
# 安装pyvis
pip install pyvis

# 如果还是报错，可以跳过可视化
python scripts/generate_survey_v2.py \
    --topic "LLM Agents"
    # 不加 --visualize
```

### Q5: 如何添加自己的survey模板？

```bash
# 方法1: 手动添加
python scripts/extract_survey_templates.py --manual --topic "My Topic"

# 方法2: 从PDF提取
pip install pymupdf
python scripts/extract_survey_templates.py --pdf my_survey.pdf --topic "My Topic"
```

### Q6: 数据库文件在哪里？

- 图数据库: `data/graph_db/mekg_v2.db`
- 模板库: `data/templates/survey_templates.db`
- 可视化: `data/visualizations/`
- 导出数据: `data/exports/`

---

## 完整工作流程示例

```bash
# 1. 查看现有图谱状态
python scripts/view_graph_stats.py --action stats

# 2. 添加示例模板
python scripts/extract_survey_templates.py --add-examples

# 3. 扩充图谱（添加更多Topic）
python scripts/build_large_graph.py \
    --topics "LLM Agents" "Retrieval Augmented Generation" \
    --max-papers 300 \
    --discover-relations \
    --compute-metrics

# 4. 再次查看统计
python scripts/view_graph_stats.py --action stats

# 5. 生成综述
python scripts/generate_survey_v2.py \
    --topic "LLM Agents" \
    --discover-relations \
    --visualize \
    --max-papers 100

# 6. 查看输出
# 打开 src/outputs/YYYY-MM-DD-HHMM_llm_agents/ 目录
```

---

## 联系方式

如有问题，请查看：
- 设计文档: `README/MEKG_V2_设计方案.md`
- 关系类型: `README/MEKG_V2_关系类型体系.md`
- 数据库设计: `README/MEKG_V2_持久化图数据库与模板库设计方案.md`