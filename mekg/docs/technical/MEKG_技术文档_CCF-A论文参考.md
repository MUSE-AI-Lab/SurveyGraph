# MEKG 知识图谱技术文档

> **适用场景**: CCF-A 论文撰写、PPT 制作、导师汇报
> 
> **文档版本**: v1.0

---

## 目录

1. [图谱整体架构](#1-图谱整体架构)
2. [节点与边的数据结构](#2-节点与边的数据结构)
3. [关系类型体系与方向判定](#3-关系类型体系与方向判定)
4. [图谱构建流程](#4-图谱构建流程)
5. [评测指标体系](#5-评测指标体系)
6. [与现有Survey图谱的对比分析](#6-与现有survey图谱的对比分析)
7. [图谱应用场景](#7-图谱应用场景)
8. [实验建议](#8-实验建议)

---

## 1. 图谱整体架构

### 1.1 MEKG 定义

**MEKG (Method Entity Knowledge Graph)** 是一种面向学术论文的方法实体知识图谱，其核心设计理念是：

```
将学术论文视为"方法实体"，通过论文间的方法关系构建知识图谱，
用于支持自动化综述生成、研究脉络追踪、核心论文发现等任务。
```

### 1.2 图谱结构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        MEKG 知识图谱                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────┐    employs     ┌─────────┐                       │
│   │ Paper A │ ─────────────→ │ Paper B │                       │
│   │ (GPT-3) │                │(Transf.)│                       │
│   └─────────┘                └─────────┘                       │
│        │                          ↑                            │
│        │ evolved_from             │ is_a_type_of               │
│        ↓                          │                            │
│   ┌─────────┐                ┌─────────┐                       │
│   │ Paper C │ ─────────────→ │ Paper D │                       │
│   │ (GPT-2) │  is_applied_to │  (NLP)  │                       │
│   └─────────┘                └─────────┘                       │
│                                                                 │
│   节点属性: paper_id, title, abstract, year, citations,        │
│            pagerank, community_id, method_entities...          │
│                                                                 │
│   边属性: relation_type, confidence, evidence,                 │
│          llm_confidence, citation_signal...                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 底层存储

- **图结构**: NetworkX DiGraph（有向图）
- **持久化**: SQLite 数据库 + JSON 导出
- **可视化**: GraphML 格式（支持 Gephi）
- **高性能计算**: 可选 igraph 加速（比 NetworkX 快 100 倍）

---

## 2. 节点与边的数据结构

### 2.1 节点结构 (MEKGNode)

每个节点代表一篇学术论文，包含以下属性：

| 属性类别 | 字段名 | 类型 | 说明 | 来源 |
|---------|--------|------|------|------|
| **基本标识** | `paper_id` | str | 论文唯一标识符（OpenAlex ID） | OpenAlex API |
| | `title` | str | 论文标题 | OpenAlex API |
| **元数据** | `abstract` | str | 论文摘要 | OpenAlex API |
| | `authors` | str | 作者列表 | OpenAlex API |
| | `year` | int | 发表年份 | OpenAlex API |
| | `venue` | str | 发表期刊/会议 | OpenAlex API |
| **文献计量** | `citation_count` | int | 被引用次数 | OpenAlex API |
| **图结构属性** | `pagerank` | float | PageRank 中心性分数 | 图算法计算 |
| | `betweenness_centrality` | float | 介数中心性分数 | 图算法计算 |
| | `community_id` | int | 所属社区编号 | 社区发现算法 |
| **语义实体** | `method_entities` | List[str] | 核心方法/技术实体 | LLM 抽取 |
| | `research_domain` | List[str] | 研究领域/应用场景 | LLM 抽取 |
| **文件路径** | `pdf_path` | str | PDF 文件本地路径 | 下载器 |
| | `md_path` | str | Markdown 解析结果路径 | PDF 解析器 |
| **链接** | `doi` | str | DOI 标识符 | OpenAlex API |
| | `url` | str | 论文链接 | OpenAlex API |

**代码位置**: `src/modules/mekg/data_structures.py:24-131`

### 2.2 边结构 (MEKGEdge)

每条边代表两篇论文之间的方法关系：

| 属性类别 | 字段名 | 类型 | 说明 |
|---------|--------|------|------|
| **基本信息** | `source` | str | 源节点 paper_id |
| | `target` | str | 目标节点 paper_id |
| | `relation_type` | RelationType | 关系类型枚举 |
| **置信度** | `confidence` | float | 融合后的最终置信度 (0.0-1.0) |
| **分项信号** | `llm_confidence` | float | LLM 推理的置信度 |
| | `citation_signal` | float | 引用网络信号 (0.0 或 1.0) |
| | `bc_score` | float | 基于介数中心性的分数 |
| | `cc_score` | float | 基于社区一致性的分数 |
| **证据** | `evidence` | str | 支持该关系的文本证据 |
| | `extracted_from` | str | 从哪篇论文中提取的关系 |

**代码位置**: `src/modules/mekg/data_structures.py:134-207`

### 2.3 置信度融合公式

边的最终置信度通过多信号融合计算：

```python
confidence = (
    llm_weight * llm_confidence +      # 默认 0.5
    citation_weight * citation_signal + # 默认 0.2
    bc_weight * bc_score +              # 默认 0.15
    cc_weight * cc_score                # 默认 0.15
)
```

**代码位置**: `src/modules/mekg/data_structures.py:209-234`

---

## 3. 关系类型体系与方向判定

### 3.1 基础关系类型（6种）

这是 MEKG V1 版本的核心关系类型：

| 关系类型 | 英文名 | 方向性 | 语义说明 | 判定依据 |
|---------|--------|--------|---------|---------|
| **采用** | `employs` | A → B | A 采用了 B 的方法/技术 | A 的 method_info 提到使用 B 的方法 |
| **演进** | `evolved_from` | A → B | A 是 B 的演进/改进版本 | A 的 innovations 提到改进 B，或方法名相似但有版本号 |
| **应用** | `is_applied_to` | A → B | A 将 B 的方法应用到新领域 | A 和 B 有不同的 research_domains，但 A 提到使用 B |
| **微调** | `is_fine_tuned_with` | A → B | A 使用 B 进行微调/优化 | A 的 method_info 明确提到 fine-tune、adapt 等 |
| **类型** | `is_a_type_of` | A → B | A 是 B 的一种特殊类型 | A 的 method_category 是 B 的子类 |
| **引用** | `cites` | A → B | A 引用了 B | 引用网络数据（辅助推理用） |

**代码位置**: `src/modules/mekg/data_structures.py:13-21`

### 3.2 扩展关系类型（21种，V2版本）

MEKG V2 版本扩展为 5 大类 21 种关系：

#### 3.2.1 结构关系（Structural）- 基于引用网络，无需 LLM

| 关系类型 | 方向性 | 说明 | 发现方法 |
|---------|--------|------|---------|
| `cites` | 有向 | A 引用 B | 引用网络直接获取 |
| `cited_by` | 有向 | A 被 B 引用 | 引用网络直接获取 |
| `co_citation` | 无向 | A 和 B 被同一论文引用 | 引用网络计算 |
| `bibliographic_coupling` | 无向 | A 和 B 引用相同论文 ≥3 篇 | 引用网络计算 |

#### 3.2.2 语义关系（Semantic）- 基于内容分析，需要 LLM

| 关系类型 | 方向性 | 说明 | 判定依据 |
|---------|--------|------|---------|
| `extends` | 有向 | A 扩展 B 的方法 | LLM 分析摘要和方法 |
| `improves` | 有向 | A 改进 B 的性能 | LLM 分析摘要和方法 |
| `applies` | 有向 | A 将 B 应用到新领域 | LLM 分析摘要和方法 |
| `compares` | 无向 | A 和 B 进行实验对比 | LLM 分析摘要和方法 |
| `combines` | 有向 | A 结合 B 和其他方法 | LLM 分析摘要和方法 |
| `reproduces` | 有向 | A 复现 B 的实验 | LLM 分析摘要和方法 |
| `refutes` | 有向 | A 反驳 B 的结论 | LLM 分析摘要和方法 |
| `supports` | 有向 | A 验证 B 的结论 | LLM 分析摘要和方法 |

#### 3.2.3 概念关系（Conceptual）- 基于方法论

| 关系类型 | 方向性 | 说明 | 判定依据 |
|---------|--------|------|---------|
| `is_variant_of` | 有向 | A 是 B 的变体 | LLM 分析 |
| `is_instance_of` | 有向 | A 是 B 方法类别的实例 | LLM 分析 |
| `shares_methodology` | 无向 | A 和 B 使用相似方法 | 方法实体重叠 ≥30% |
| `shares_task` | 无向 | A 和 B 解决相同任务 | 任务实体重叠 |
| `shares_dataset` | 无向 | A 和 B 使用相同数据集 | 数据集实体重叠 |
| `shares_baseline` | 无向 | A 和 B 使用相同基线 | 数据集+指标重叠 |
| `shares_architecture` | 无向 | A 和 B 使用相似架构 | LLM 分析 |

#### 3.2.4 时序关系（Temporal）- 基于时间演进

| 关系类型 | 方向性 | 说明 | 判定依据 |
|---------|--------|------|---------|
| `precedes` | 有向 | A 早于 B 且被 B 引用 | year_A < year_B 且 A ∈ refs_B |
| `succeeds` | 有向 | A 晚于 B 且引用 B | year_A > year_B 且 B ∈ refs_A |
| `concurrent` | 无向 | A 和 B 同期发表 | \|year_A - year_B\| ≤ 1 且共同引用 ≥5 |

#### 3.2.5 作者关系（Authorship）- 基于作者信息

| 关系类型 | 方向性 | 说明 | 判定依据 |
|---------|--------|------|---------|
| `same_author` | 无向 | A 和 B 有共同作者 | 作者 ID 集合有交集 |
| `same_group` | 无向 | A 和 B 来自同一研究组 | 机构信息匹配 |

**代码位置**: `src/modules/mekg/enhanced_relation_discoverer.py:39-97`

### 3.3 关系方向判定逻辑（重要！）

#### 3.3.1 有向关系的方向判定原则

**核心原则**: 
- **时间顺序**: 新论文 → 旧论文（新论文采用/改进旧论文的方法）
- **引用方向**: 引用者 → 被引用者

**LLM 判定流程**:

```python
# LLM 返回的 direction 字段决定方向
if direction == "A->B":
    src, tgt = pid_a, pid_b  # A 是源，B 是目标
elif direction == "B->A":
    src, tgt = pid_b, pid_a  # B 是源，A 是目标
```

**代码位置**: `src/modules/mekg/enhanced_relation_discoverer.py:309-318`

#### 3.3.2 无向关系的处理

对于无向关系（如 `shares_methodology`、`co_citation`），统一按字典序排列：

```python
if not is_directed:
    src, tgt = sorted([pid_a, pid_b])  # 字典序排列，保证唯一性
```

#### 3.3.3 关系方向的语义解释（PPT 可用示例）

**示例 1: evolved_from 关系**

```
GPT-3 (2020) --[evolved_from]--> GPT-2 (2019)

语义解读: GPT-3 是从 GPT-2 演进而来的
箭头方向: 新论文 → 旧论文
时间关系: 2020 → 2019
判定依据: GPT-3 论文中提到 "building upon GPT-2..."
```

**示例 2: employs 关系**

```
BERT-QA (2019) --[employs]--> BERT (2018)

语义解读: BERT-QA 采用了 BERT 的预训练方法
箭头方向: 应用论文 → 基础方法论文
判定依据: BERT-QA 的 method_info 中提到使用 BERT
```

**示例 3: is_applied_to 关系**

```
ViT (2020) --[is_applied_to]--> Transformer (2017)

语义解读: ViT 将 Transformer 应用到计算机视觉领域
箭头方向: 应用论文 → 原始方法论文
判定依据: 不同 research_domain，但 ViT 使用 Transformer 架构
```

### 3.4 关系提取的 LLM Prompt（核心）

**系统提示词**:

```
You are an academic relationship analysis expert.

**Relationship Types**:
1. **employs**: A employs B's method/technique
   - Judgment: A's method_info mentions using B's method
   
2. **evolved_from**: A is an improved/evolved version of B
   - Judgment: A's innovations mention improving B, or 
     method_name similar but with version number

3. **is_applied_to**: A applies B's method to new domain
   - Judgment: Different research_domains, but A uses B

4. **is_fine_tuned_with**: A fine-tunes using B
   - Judgment: A explicitly mentions fine-tune, adapt

5. **is_a_type_of**: A is a special type of B
   - Judgment: A's method_category is subclass of B's

**Confidence Standards**:
- 0.9-1.0: Explicit statement, direct evidence
- 0.7-0.9: Strong implication, indirect evidence
- 0.5-0.7: Possible, weak evidence
- <0.5: Uncertain, should not output
```

**代码位置**: `src/modules/mekg/attribute_based_relation_extractor.py:54-97`

---

## 4. 图谱构建流程

### 4.1 双循环自演化构建方法（核心创新）

MEKG 采用"三阶段流水线"构建方法，这是论文的核心创新点：

```
┌─────────────────────────────────────────────────────────────────┐
│                    三阶段流水线构建方法                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第一阶段：广泛播种与网络初始化                            │   │
│  │                                                         │   │
│  │  1.1 关键词扩展 (LLM)                                   │   │
│  │      "LLM Agents" → ["LLM", "Agent", "Tool Use", ...]   │   │
│  │                                                         │   │
│  │  1.2 论文池收集 (OpenAlex API)                          │   │
│  │      - 综述优先策略：先找 Survey，再展开 References      │   │
│  │      - 目标：1500 篇论文                                │   │
│  │                                                         │   │
│  │  1.3 构建引文网络                                       │   │
│  │      - 节点：论文                                       │   │
│  │      - 边：引用关系                                     │   │
│  │                                                         │   │
│  │  1.4 下载 PDF 并提取属性 (可选)                         │   │
│  │      - PDF 解析 → 全文                                  │   │
│  │      - LLM 属性提取 → method_info, innovations 等       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第二阶段：核心发现与骨架构建（第一个循环）                 │   │
│  │                                                         │   │
│  │  2.1 识别核心论文 (PageRank + 引用数 + 年份)            │   │
│  │      - 核心论文比例：10%                                │   │
│  │      - 评分公式：                                       │   │
│  │        score = 0.4*log(citations) + 0.3*year_score      │   │
│  │              + 0.2*method_score + 0.1*type_score        │   │
│  │                                                         │   │
│  │  2.2 创建 MEKG 节点                                     │   │
│  │      - 为每篇论文创建 MEKGNode                          │   │
│  │      - 填充属性信息                                     │   │
│  │                                                         │   │
│  │  2.3 提取骨架关系（核心-核心候选对）                     │   │
│  │      - 核心论文之间完全连接                             │   │
│  │      - LLM 提取方法关系                                 │   │
│  │      - 形成图谱骨架                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 第三阶段：全面扩展与最终图谱形成（第二个循环）             │   │
│  │                                                         │   │
│  │  3.1 生成扩展候选对                                     │   │
│  │      - 普通论文 → 核心论文（每篇连接 top-5 相关核心）    │   │
│  │      - 文献耦合对（共同引用 ≥3 篇）                     │   │
│  │      - 同被引对（被同一论文引用 ≥3 次）                 │   │
│  │                                                         │   │
│  │  3.2 提取扩展关系                                       │   │
│  │      - LLM 批量分析候选对                               │   │
│  │      - 50 线程并发                                      │   │
│  │                                                         │   │
│  │  3.3 分析最终图谱                                       │   │
│  │      - 计算 WCR, CC, SC 指标                            │   │
│  │      - 社区发现                                         │   │
│  │                                                         │   │
│  │  3.4 生成 Survey 大纲                                   │   │
│  │      - 基于社区结构生成章节                             │   │
│  │      - 基于演进路径组织内容                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**代码位置**: `src/modules/mekg/dual_loop_builder.py:107-214`

### 4.2 智能候选对生成策略（复杂度优化）

**核心创新**: 将 O(N²) 复杂度降低到 O(N*K)

```
传统方法: 1500 篇论文 → 1,124,250 对 → 全部用 LLM 分析
我们的方法: 1500 篇论文 → ~8,000 对 → 减少 99.3%
```

**分层策略**:

| 层级 | 候选对类型 | 生成规则 | 预期命中率 |
|------|-----------|---------|-----------|
| Layer 1 | 核心-核心 | 核心论文之间完全连接 | 30-40% |
| Layer 2 | 普通→核心 | 每篇普通论文连接 top-5 相关核心 | 20-30% |
| Layer 3 | 文献耦合 | 共同引用 ≥3 篇的论文对 | 15-25% |
| Layer 3 | 同被引 | 被同一论文引用 ≥3 次的论文对 | 10-20% |

**代码位置**: `src/modules/mekg/attribute_based_relation_extractor.py:367-466`

### 4.3 语义实体抽取（V3 新增）

借鉴 NLP-AKG 的设计，从论文中抽取 7 类细粒度语义实体：

| 实体类型 | 说明 | 抽取来源 | 示例 |
|---------|------|---------|------|
| `Problem` | 论文解决的问题 | 摘要 | "long-range dependencies in text" |
| `Method` | 提出的方法 | 摘要 | "transformer-based architecture" |
| `Model` | 模型名称 | 摘要 | "BERT", "GPT-3" |
| `Task` | 应用任务 | 摘要 | "question answering", "NER" |
| `Dataset` | 使用的数据集 | 摘要/实验 | "SQuAD", "GLUE" |
| `Metric` | 评估指标 | 摘要/实验 | "F1-score", "accuracy" |
| `Innovation` | 主要创新点 | 综合生成 | "To solve X, proposes Y..." |

**代码位置**: `src/modules/mekg/semantic_entity_extractor.py:33-99`

---

## 5. 评测指标体系

### 5.1 图谱质量评测指标

#### 5.1.1 WCR (Weighted Centrality Recall)

**定义**: 评估图谱是否覆盖了最重要的论文

**计算公式**:

```
WCR = Σ(PageRank of Top-K papers) / Σ(PageRank of all papers)
```

**代码实现**:

```python
def calculate_wcr(self, top_k: int = 50) -> float:
    sorted_nodes = sorted(
        self.graph.nodes.values(),
        key=lambda n: n.pagerank or 0.0,
        reverse=True
    )
    top_nodes = sorted_nodes[:top_k]
    top_weight = sum(n.pagerank or 0.0 for n in top_nodes)
    total_weight = sum(n.pagerank or 0.0 for n in self.graph.nodes.values())
    wcr = top_weight / total_weight if total_weight > 0 else 0.0
    return wcr
```

**代码位置**: `src/modules/mekg/analyzer.py:320-363`

**解释**: WCR 越高，说明图谱越好地覆盖了领域内的核心论文。

#### 5.1.2 CC (Community Coverage)

**定义**: 评估图谱是否覆盖了所有研究社区

**计算公式**:

```
CC = (num_communities / 10) * normalized_entropy

其中:
normalized_entropy = entropy / log2(num_communities)
entropy = -Σ(p_i * log2(p_i))  # p_i 是社区 i 的论文比例
```

**代码位置**: `src/modules/mekg/analyzer.py:365-401`

**解释**: CC 同时考虑社区数量和分布均匀性。社区数量多且分布均匀时，CC 值高。

#### 5.1.3 SC (Structural Coherence)

**定义**: 评估演进路径的逻辑性

**计算公式**:

```
SC = 0.6 * normalized_path_length + 0.4 * path_coverage

其中:
normalized_path_length = min(avg_path_length / 5.0, 1.0)
path_coverage = nodes_in_paths / total_nodes
```

**代码位置**: `src/modules/mekg/analyzer.py:403-435`

**解释**: SC 越高，说明图谱中的方法演进脉络越清晰。

### 5.2 候选对生成评测指标

| 指标 | 公式 | 说明 |
|------|------|------|
| Precision | TP / (TP + FP) | 生成的候选对中真正有关系的比例 |
| Recall | TP / (TP + FN) | 真实关系对被召回的比例 |
| F1-Score | 2 * P * R / (P + R) | 精确率和召回率的调和平均 |
| Coverage | covered_papers / total_papers | 被候选对覆盖的论文比例 |
| Hit Rate | actual_edges / num_pairs | LLM 调用的命中率 |
| Reduction Ratio | 1 - (num_pairs / N²) | 相比完全图减少的比例 |

**代码位置**: `src/modules/mekg/evaluation_metrics.py:29-191`

---

## 6. 与现有 Survey 图谱的对比分析

### 6.1 现有 Survey 的图谱构建方式

| Survey 类型 | 图谱构建方式 | 优点 | 缺点 |
|------------|-------------|------|------|
| **手工综述** | 作者手动整理方法关系 | 准确性高 | 耗时、主观性强、难以更新 |
| **引用网络** | 仅基于引用关系 | 客观、易获取 | 无法区分关系类型 |
| **关键词聚类** | 基于关键词相似度 | 简单快速 | 语义理解浅、噪声多 |
| **知识图谱** | 实体-关系三元组 | 结构化、可推理 | 需要大量标注数据 |

### 6.2 MEKG 的创新点

| 对比维度 | 传统方法 | MEKG |
|---------|---------|------|
| **关系类型** | 单一（引用） | 21 种细粒度关系 |
| **关系方向** | 无/固定 | 语义驱动的有向关系 |
| **构建方式** | 手工/规则 | LLM + 图算法自动化 |
| **可扩展性** | 差 | 增量更新支持 |
| **评测指标** | 无 | WCR, CC, SC 三维评测 |

### 6.3 建议的对比实验设计

**实验 1: 关系准确性对比**

```
选择 3-5 个 topic（如 LLM, RAG, Agent）
每个 topic 收集 100 篇论文
人工标注 ground truth 关系
对比:
- MEKG 自动提取的关系
- 仅基于引用的关系
- 基于关键词相似度的关系
指标: Precision, Recall, F1
```

**实验 2: 与现有 Survey 的图谱对比**

```
选择 3 篇高引 Survey（如 LLM Survey, Agent Survey）
提取 Survey 中的方法关系图（手工）
用 MEKG 对相同 topic 构建图谱
对比:
- 覆盖的论文数量
- 关系类型丰富度
- 演进路径完整性
- 社区结构合理性
```

**实验 3: 图谱质量评测**

```
对比不同候选对生成策略:
- 完全图（baseline）
- 仅引用邻居
- MEKG 分层策略
指标: WCR, CC, SC, Hit Rate, Cost
```

### 6.4 预期结论

1. **关系准确性**: MEKG 的 LLM 驱动方法在语义关系识别上优于规则方法
2. **覆盖完整性**: MEKG 能发现 Survey 遗漏的重要论文和关系
3. **效率**: 分层候选对策略在保持质量的同时大幅降低成本
4. **可解释性**: 每条关系都有 evidence 支持，便于验证

---

## 7. 图谱应用场景

### 7.1 自动化综述生成

```
MEKG → 社区发现 → 章节划分
     → 演进路径 → 内容组织
     → 核心论文 → 重点介绍
```

### 7.2 研究脉络追踪

```
输入: 一篇论文
输出: 
- 该论文的方法来源（evolved_from 反向追溯）
- 该论文的后续发展（evolved_from 正向追踪）
- 相关方法（shares_methodology）
```

### 7.3 核心论文发现

```
基于 PageRank + 社区中心性
识别每个研究方向的奠基性论文
```

### 7.4 研究空白发现

```
分析社区间的连接稀疏区域
发现潜在的跨领域研究机会
```

---

## 8. 实验建议

### 8.1 推荐的实验 Topic

| Topic | 论文数量 | 预期社区数 | 特点 |
|-------|---------|-----------|------|
| Large Language Models | 500+ | 8-12 | 热门、演进快 |
| Retrieval-Augmented Generation | 200+ | 4-6 | 新兴、结构清晰 |
| LLM Agents | 300+ | 6-8 | 跨领域、关系复杂 |
| Graph Neural Networks | 400+ | 6-10 | 成熟、有经典 Survey |
| Vision Transformers | 300+ | 5-8 | 跨模态、演进明确 |

### 8.2 实验步骤

```bash
# 1. 构建图谱
python scripts/build_mekg_v3.py --topic "Large Language Models" --papers-per-topic 500

# 2. 查看统计
python scripts/view_graph_stats.py

# 3. 导出可视化
python scripts/export_mekg.py --format graphml

# 4. 用 Gephi 打开 mekg.graphml 进行可视化
```

### 8.3 可视化建议

**Gephi 设置**:
- 布局: Force Atlas 2 或 Fruchterman Reingold
- 节点大小: 按 PageRank
- 节点颜色: 按 community_id
- 边颜色: 按 relation_type
- 边粗细: 按 confidence

### 8.4 论文写作建议

**图谱展示**:
1. 整体图谱概览（展示社区结构）
2. 核心论文子图（展示骨架）
3. 演进路径示例（展示时间线）
4. 关系类型分布（饼图/柱状图）

**表格建议**:
1. 关系类型定义表
2. 评测指标对比表
3. 与 baseline 的性能对比表
4. Case Study 表

---

## 9. 常见问题解答

### Q1: 关系方向是否正确？

**验证方法**:
1. 检查 `evolved_from` 关系的时间顺序（新→旧）
2. 检查 `employs` 关系的引用关系（引用者→被引用者）
3. 抽样检查 evidence 字段是否支持关系判定

**代码验证**:
```python
# 检查 evolved_from 关系的时间顺序
for edge in mekg.edges:
    if edge.relation_type == RelationType.EVOLVED_FROM:
        source_node = mekg.get_node(edge.source)
        target_node = mekg.get_node(edge.target)
        if source_node.year < target_node.year:
            print(f"警告: {edge.source} ({source_node.year}) -> {edge.target} ({target_node.year})")
```

### Q2: 如何评估图谱质量？

**三维评测**:
- WCR: 是否覆盖核心论文？
- CC: 是否覆盖所有研究方向？
- SC: 演进路径是否清晰？

### Q3: 图谱中哪些元素最有用？

**核心元素**:
1. **核心论文节点**: PageRank top-10%
2. **演进关系边**: evolved_from, extends, improves
3. **社区结构**: 对应不同研究方向
4. **演进路径**: 方法发展脉络

### Q4: 如何与现有 Survey 对比？

**对比维度**:
1. 论文覆盖率: MEKG 覆盖了 Survey 中多少论文？
2. 关系覆盖率: MEKG 发现了 Survey 中多少关系？
3. 新发现: MEKG 发现了哪些 Survey 遗漏的论文/关系？
4. 结构差异: 社区划分是否与 Survey 章节对应？

---

## 10. 附录

### A. 输出文件结构

```
output/
├── papers/
│   ├── paper_pool.json          # 论文池
│   └── pdfs/                    # PDF 文件
├── mekg/
│   ├── mekg.json                # 知识图谱（JSON）
│   ├── mekg.graphml             # 知识图谱（GraphML）
│   ├── analysis_report.json     # 分析报告
│   ├── outline.json             # 大纲（JSON）
│   ├── outline.md               # 大纲（Markdown）
│   └── core_discovery_report.json
└── dual_loop_builder.log        # 构建日志
```

### B. 关键代码文件索引

| 功能 | 文件路径 |
|------|---------|
| 数据结构定义 | `src/modules/mekg/data_structures.py` |
| 双循环构建器 | `src/modules/mekg/dual_loop_builder.py` |
| 关系提取器 | `src/modules/mekg/attribute_based_relation_extractor.py` |
| 增强关系发现 | `src/modules/mekg/enhanced_relation_discoverer.py` |
| 图谱分析器 | `src/modules/mekg/analyzer.py` |
| 评测指标 | `src/modules/mekg/evaluation_metrics.py` |
| 语义实体抽取 | `src/modules/mekg/semantic_entity_extractor.py` |
| V3 构建脚本 | `scripts/build_mekg_v3.py` |

### C. 参考文献格式

如果在论文中引用本系统，建议格式：

```bibtex
@software{mekg2024,
  title = {MEKG: Method Entity Knowledge Graph for Automated Survey Generation},
  year = {2024},
  description = {A knowledge graph system for academic papers with 21 relation types}
}
```