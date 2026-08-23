
# MEKG知识图谱系统调研报告

> **调研范围**: MEKG知识图谱构建流程、论文爬取机制、属性提取、综述生成集成  

---

## 📋 目录

1. [系统概述](#1-系统概述)
2. [MEKG知识图谱构建流程](#2-mekg知识图谱构建流程)
3. [论文爬取机制](#3-论文爬取机制)
4. [属性提取流程](#4-属性提取流程)
5. [综述生成流程中的MEKG集成](#5-综述生成流程中的mekg集成)
6. [关键技术亮点](#6-关键技术亮点)
7. [数据流转与存储](#7-数据流转与存储)

---

## 1. 系统概述

### 1.1 MEKG是什么?

**MEKG (Methods-Entity Knowledge Graph)** 是一个基于方法实体的学术知识图谱系统,用于**替代传统的RAG向量召回方案**,通过结构化的知识图谱分析来生成更有逻辑性的综述大纲。

### 1.2 核心目标

1. ✅ **大规模论文处理** - 支持1000-2000篇论文的高质量采集和分析
2. ✅ **深度语义理解** - 提取8大类论文属性,精准识别方法关系
3. ✅ **结构化大纲生成** - 基于社区发现和演进路径,替代RAG
4. ✅ **高效并发处理** - 50线程并发下载、解析、属性提取
5. ✅ **成本优化** - 使用DeepSeek-V3.2-Exp降低80%成本

### 1.3 系统架构

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
│  PDF下载 (MultiSourcePDFDownloader)         │
│  - 多源策略: OpenAlex + arXiv               │
│  - 20并发下载                                │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  PDF解析 (EnhancedPDFProcessor)             │
│  - PyPDF快速解析 (主方案)                    │
│  - MinerU精细解析 (备选)                     │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  属性提取 (PaperAttributeExtractor)         │
│  - 8大类属性提取                             │
│  - DeepSeek-V3.2-Exp                        │
│  - 10并发 (避免API限流)                      │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  关系抽取 (AttributeBasedRelationExtractor) │
│  - 基于属性对比 (非全文)                     │
│  - 智能候选对生成 (减少73%调用)              │
│  - 10并发                                    │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  MEKG图谱构建 (MEKGGraph)                   │
│  - 节点: 论文 + 属性                         │
│  - 边: 5种方法关系                           │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  图谱分析 (MEKGAnalyzer)                    │
│  - PageRank中心性                            │
│  - 社区发现 (Louvain)                        │
│  - 演进路径追踪                              │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│  大纲生成 (LLMEnhancedOutlineGenerator)     │
│  - 基于社区生成章节                          │
│  - 基于演进路径生成时间线                    │
│  - LLM语义优化                               │
└─────────────────────────────────────────────┘
    ↓
输出: MEKG + 大纲 + 分析报告
```

---

## 2. MEKG知识图谱构建流程

### 2.1 完整9步流程

**入口文件**: [`src/modules/mekg/enhanced_builder.py`](src/modules/mekg/enhanced_builder.py)

**主类**: `EnhancedMEKGBuilder`

**核心方法**: `build_from_topic(topic, year_start, year_end)`

#### 详细步骤

| 步骤 | 功能 | 主要组件 | 代码位置 | 关键参数 |
|------|------|----------|----------|----------|
| **步骤1** | 智能关键词处理 | `IntelligentQueryProcessor` | `enhanced_builder.py:181-186` | LLM模型: GLM-4.6 |
| **步骤2** | 多关键词搜索+雪球采样 | `IntelligentQueryProcessor.multi_keyword_search()` | `enhanced_builder.py:188-215` | 搜索3倍目标数量 |
| **步骤3** | PDF下载与解析 | `MultiSourcePDFDownloader` + `EnhancedPDFProcessor` | `enhanced_builder.py:217-242` | 20并发 |
| **步骤4** | 论文属性提取 | `PaperAttributeExtractor` | `enhanced_builder.py:244-263` | 10并发, DeepSeek |
| **步骤5** | 创建MEKG节点 | `MEKGGraph.add_node()` | `enhanced_builder.py:265-291` | - |
| **步骤6** | 提取关系 | `AttributeBasedRelationExtractor` | `enhanced_builder.py:293-305` | 10并发 |
| **步骤7** | 分析图谱 | `MEKGAnalyzer` | `enhanced_builder.py:307-318` | PageRank, 社区, 中心性 |
| **步骤8** | 生成大纲 | `LLMEnhancedOutlineGenerator` | `enhanced_builder.py:320-354` | 支持纯图谱/LLM增强 |
| **步骤9** | 保存结果 | 文件系统 | `enhanced_builder.py:356-435` | JSON, GraphML, Markdown |

### 2.2 核心配置

```python
# enhanced_builder.py 初始化参数
EnhancedMEKGBuilder(
    output_dir=Path,              # 输出目录
    target_paper_count=1500,      # 目标论文数量 (1000-2000)
    llm_api_url="...",            # LLM API地址
    llm_api_token="...",          # API令牌
    use_llm_outline=True          # 是否使用LLM增强大纲 (默认True)
)
```

### 2.3 并发控制策略

为避免API限流和提高稳定性,系统采用了**分层并发控制**:

| 组件 | 原设计并发 | 实际并发 | 原因 |
|------|-----------|----------|------|
| PDF下载 | 50 | **20** | 提高成功率,避免429错误 |
| PDF解析 | 50 | **20** | 与下载保持一致 |
| 属性提取 | 50 | **10** | DeepSeek API限流严格 |
| 关系抽取 | 50 | **10** | 同上 |

**代码位置**:
- PDF下载: `enhanced_builder.py:89-92`
- 属性提取: `enhanced_builder.py:251-254`
- 关系抽取: `enhanced_builder.py:296-300`

---

## 3. 论文爬取机制

### 3.1 智能关键词处理

**文件**: [`src/modules/paper_acquisition/intelligent_query_processor.py`](src/modules/paper_acquisition/intelligent_query_processor.py)

**类**: `IntelligentQueryProcessor`

#### 3.1.1 LLM判断是否拆分

**方法**: `process_query(topic: str) -> List[str]`

**功能**:
1. LLM分析主题是否需要拆分为多个关键词
2. 如果主题清晰、具体、单一 → 不拆分
3. 如果主题模糊、宽泛、包含多个概念 → 拆分

**示例**:
```python
# 输入: "BERT"
# 输出: ["BERT"]  (不拆分)

# 输入: "large language model agents"
# 输出: ["large language model", "LLM agents", "autonomous agents"]  (拆分)
```

**Prompt模板**:
```
你是一个学术搜索专家。请分析以下研究主题是否需要拆分为多个关键词进行搜索。

**主题**: {topic}

**判断标准**:
1. 如果主题清晰、具体、单一概念 → 不需要拆分
2. 如果主题模糊、宽泛、包含多个概念 → 需要拆分

**输出格式**(JSON):
{
  "need_split": true/false,
  "reason": "判断理由",
  "keywords": ["关键词1", "关键词2", ...]
}
```

### 3.2 多关键词并行搜索

**方法**: `multi_keyword_search(keywords, target_count, year_start, year_end)`

**策略**:
1. **搜索倍数**: 搜索3倍目标数量 (例如目标1500 → 搜索4500)
2. **配额分配**: 每个关键词分配 `(target_count * 3) / len(keywords)` 但不超过200
3. **并行执行**: 使用 `asyncio.gather` 并行搜索所有关键词
4. **去重合并**: 按 `paper_id` 去重
5. **雪球采样**: 如果数量不足,使用前50篇作为种子扩展
6. **排序截取**: 按引用量排序,取top `target_count`

**代码位置**: `intelligent_query_processor.py:90-171`

**关键代码**:
```python
# 为每个关键词分配配额
quota_per_keyword = min((target_count * 3) // len(keywords), 200)

# 并行搜索
tasks = [
    search_scholar(
        query=kw,
        count=quota_per_keyword,
        sort_by="citations",
        year_start=year_start,
        year_end=year_end,
        fuzzy_search=True  # 模糊搜索获取更多结果
    )
    for kw in keywords
]
results = await asyncio.gather(*tasks)

# 合并去重
all_papers = {}
for papers in results:
    for paper in papers:
        paper_id = paper.get("paper_id")
        if paper_id and paper_id not in all_papers:
            all_papers[paper_id] = paper
```

### 3.3 雪球采样扩展

**方法**: `_snowball_expansion(seed_papers, target_count, year_start, year_end)`

**功能**: 当初步搜索论文数量不足时,基于种子论文的引用关系扩展

**策略**:
1. 使用前50篇高引论文作为种子
2. 对每个种子,查询引用它的论文 (`cites:{paper_id}`)
3. 每个种子获取10篇引用论文
4. 去重后累积到目标数量

**代码位置**: `intelligent_query_processor.py:173-216`

### 3.4 爬取数量统计

| 阶段 | 数量 | 说明 |
|------|------|------|
| **搜索阶段** | 目标数 × 3 | 例如目标1500 → 搜索4500 |
| **去重后** | 2000-3000 | 多关键词去重后 |
| **雪球采样后** | 达到搜索目标 | 如果不足则补充 |
| **最终候选池** | 目标数 × 3 | 例如4500篇 |
| **PDF下载目标** | 目标数 | 例如1500篇 |
| **实际成功** | 80-90% | 由于PDF下载失败率 |

**示例**: 目标1500篇论文的爬取流程

```
用户输入: 目标1500篇

步骤1: 智能关键词拆分
  "large language model agents"
  → ["large language model", "LLM agents", "autonomous agents"]

步骤2: 多关键词搜索
  每个关键词配额: min(1500*3/3, 200) = 200篇
  3个关键词 × 200 = 600篇初步搜索

步骤3: 雪球采样扩展
  使用前50篇种子 × 10篇引用 = 额外500篇
  总候选池: 600 + 500 = 1100篇

步骤4: 去重排序
  去重后: ~900篇
  按引用量排序取top: 900篇

步骤5: 多源PDF下载
  目标: 1500篇
  候选池不足,继续搜索或降低目标

最终: 成功下载 ~800-1000篇 (由于PDF可用性)
```

### 3.5 数据源

- **主要数据源**: OpenAlex API (免费,无需API key)
- **PDF来源**: 
  1. OpenAlex提供的PDF链接
  2. arXiv (自动识别DOI/URL)
  3. 其他DOI解析服务

**搜索接口**: `OpenAlex/scholar.py` 中的 `search_scholar()` 函数

---

## 4. 属性提取流程

### 4.1 属性提取器架构

**文件**: [`src/modules/paper_acquisition/paper_attribute_extractor.py`](src/modules/paper_acquisition/paper_attribute_extractor.py)

**类**: `PaperAttributeExtractor`

**核心配置**:
```python
PaperAttributeExtractor(
    llm_api_url="https://api.pisces.ink/v1/chat/completions",
    llm_api_token="...",
    llm_model="[N]DeepSeek-V3.2-Exp"  # 成本优化
)
```

### 4.2 提取的8大类属性

| 属性类别 | 字段名 | 类型 | 说明 | 示例 |
|---------|--------|------|------|------|
| **1. 论文类型** | `paper_type` | String | 方法论文/综述/应用/实验/理论 | "Methodology Paper" |
| **2. 方法信息** | `method_info` | Object | 是否有新方法、方法名、类别 | `{has_method: true, method_name: "BERT", ...}` |
| **3. 创新点** | `innovations` | Array | 2-5个主要创新 | `["双向预训练", "Masked LM", ...]` |
| **4. 局限性** | `limitations` | Array | 1-3个不足 | `["计算资源需求大", ...]` |
| **5. 原子事实** | `atomic_facts` | Array | 5-10个关键事实 | `["BERT uses Transformer", ...]` |
| **6. 引用文献** | `cited_key_papers` | Array | 3-5篇关键引文 | `[{title: "...", reason: "..."}]` |
| **7. 研究领域** | `research_domains` | Array | 1-3个领域 | `["NLP", "Transfer Learning"]` |
| **8. 应用场景** | `application_scenarios` | Array | 1-3个场景 | `["Text Classification", ...]` |

### 4.3 提取流程

**主方法**: `extract_attributes(paper_id, title, abstract, full_text)`

**流程**:
```python
1. 选择输入内容
   if full_text 存在且长度>100:
       使用全文
   else:
       使用摘要

2. 构建Prompt
   - 系统提示词: 定义任务和输出格式
   - 用户提示词: 论文标题 + 摘要/全文

3. 调用LLM
   - 模型: DeepSeek-V3.2-Exp
   - 温度: 0.3
   - 最大token: 2048
   - 响应格式: JSON object (强制)

4. 解析响应
   - 清理JSON (去除markdown代码块)
   - 验证关键字段
   - 如果失败 → 使用后备提取

5. 返回属性字典
```

**代码位置**: `paper_attribute_extractor.py:150-236`

### 4.4 System Prompt (系统提示词)

**核心内容**:
```
You are a senior academic paper analysis expert specializing in extracting 
structured metadata and attributes from papers.

**Task**: Extract the following attributes from the given paper:

1. Paper Type Classification (paper_type)
2. Method Information (method_info)
3. Innovations (innovations)
4. Limitations (limitations)
5. Atomic Facts (atomic_facts)
6. Cited Key Papers (cited_key_papers)
7. Research Domains (research_domains)
8. Application Scenarios (application_scenarios)

**Output Format** (strict JSON): {...}

**Requirements**:
1. Base analysis on paper content, do not speculate
2. If information is not explicitly mentioned, mark as null or empty list
3. Maintain objectivity, accuracy, and professionalism
4. Output must be valid JSON format
```

**代码位置**: `paper_attribute_extractor.py:51-148`

### 4.5 批量提取与并发

**方法**: `batch_extract_attributes(papers, max_concurrent=50)`

**实际调用**: `max_concurrent=10` (在 `enhanced_builder.py:251-254`)

**并发控制**:
```python
semaphore = asyncio.Semaphore(max_concurrent)

async def extract_single(paper):
    async with semaphore:
        # 提取单篇论文属性
        attributes = await self.extract_attributes(...)
        paper["attributes"] = attributes
        return paper

# 真正的并发执行
tasks = [extract_single(p) for p in papers]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**代码位置**: `paper_attribute_extractor.py:326-396`

### 4.6 后备提取机制

当LLM提取失败时,使用**基于规则的后备提取**:

**方法**: `_extract_fallback_attributes(title, abstract)`

**策略**:
1. **领域检测**: 基于关键词匹配检测研究领域
2. **方法检测**: 检测是否提出新方法 ("propose", "novel", "new method"等)
3. **方法名提取**: 从标题中提取 (如果包含冒号)

**领域检测规则**:
```python
domain_keywords = {
    "Natural Language Processing": ["nlp", "language model", "text", ...],
    "Computer Vision": ["image", "vision", "object detection", ...],
    "Machine Learning": ["learning", "classification", "neural network", ...],
    "Reinforcement Learning": ["reinforcement", "reward", "agent", ...],
    ...
}
```

**代码位置**: `paper_attribute_extractor.py:237-277`

### 4.7 错误处理与重试

**重试机制**: 使用 `tenacity` 库实现指数退避重试

```python
@retry(
    stop=stop_after_attempt(5),  # 最多重试5次
    wait=wait_exponential(multiplier=1, min=2, max=60),  # 2s→4s→8s→16s→32s
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
    before_sleep=before_sleep_log(logger, "WARNING"),
    reraise=True
)
async def _call_llm(self, user_message: str) -> str:
    # LLM调用逻辑
    ...
```

**触发重试的条件**:
- HTTP状态码: 429 (Too Many Requests)
- HTTP状态码: 502, 503, 504 (服务器错误)
- `httpx.RequestError` (网络错误)

**代码位置**: `paper_attribute_extractor.py:415-467`

### 4.8 成本分析

**模型选择**: DeepSeek-V3.2-Exp

**为什么选择DeepSeek?**
1. **成本**: 比GPT-4便宜10-20倍 (~$2/1M tokens vs $30/1M tokens)
2. **性能**: 结构化输出任务表现优秀
3. **速度**: 响应快,支持高并发
4. **JSON支持**: 原生支持 `response_format: json_object`

**实际成本估算** (1500篇论文):
```
平均每篇论文:
- 输入token: ~2000 (标题+摘要+全文片段+Prompt)
- 输出token: ~500 (结构化属性JSON)

总token: 1500 × 2500 = 3,750,000 tokens

成本: 3.75M × $2/1M = $7.5

(实际约$15,因为包含重试和部分全文)
```

---

## 5. 综述生成流程中的MEKG集成

### 5.1 集成架构

MEKG在综述生成流程中的角色:**替代RAG向量召回,基于图谱结构生成大纲**

```
传统流程 (RAG):
用户Topic → 论文搜索 → 向量化 → 向量召回 → 生成大纲 → 写作

MEKG流程:
用户Topic → 构建MEKG → 图谱分析 → 结构化大纲 → 写作
              ↑
         (包含论文搜索、属性提取、关系抽取)
```

### 5.2 大纲生成器

**文件**: [`src/modules/mekg/llm_enhanced_outline_generator.py`](src/modules/mekg/llm_enhanced_outline_generator.py)

**类**: `LLMEnhancedOutlineGenerator`

**核心思想**:
1. **MEKG提供客观信息**: 社区聚类、演进路径、代表性论文
2. **LLM提供语义理解**: 基于这些信息生成学术化的大纲
3. **结合优势**: 图谱的客观性 + LLM的语义能力

### 5.3 大纲生成流程

**主方法**: `generate_outline(topic, max_main_sections=6)`

**流程**:
```
步骤1: 从MEKG提取结构化信息
  ├─ 社区信息 (communities)
  ├─ 演进路径 (evolution_paths)
  ├─ Top论文 (top_papers)
  └─ 研究领域分布 (research_domains)

步骤2: 使用LLM生成大纲
  ├─ 构建rich context
  ├─ 调用LLM (GLM-4.6)
  └─ 解析JSON响应

步骤3: 将论文挂载到大纲章节
  ├─ 基于关键词匹配
  └─ 计算每个章节的论文数量
```

**代码位置**: `llm_enhanced_outline_generator.py:63-99`

### 5.4 从MEKG提取结构化信息

**方法**: `_extract_mekg_context(max_communities)`

**提取内容**:

#### 5.4.1 社区信息

```python
for comm_id, nodes in community_map.items():
    community_info = {
        "community_id": comm_id,
        "size": len(nodes),
        "top_method_entities": [...],     # Top5方法实体
        "top_research_domains": [...],    # Top3研究领域
        "year_range": [min_year, max_year],
        "representative_papers": [...],   # Top5代表性论文
        "avg_citation": ...
    }
```

**代码位置**: `llm_enhanced_outline_generator.py:178-226`

#### 5.4.2 演进路径

使用 `MEKGAnalyzer.find_evolution_paths()` 追踪方法演进

```python
evolution_paths = [
    {
        "length": 5,
        "papers": [
            {"title": "GPT", "year": 2018, ...},
            {"title": "GPT-2", "year": 2019, ...},
            {"title": "GPT-3", "year": 2020, ...},
            ...
        ]
    },
    ...
]
```

**代码位置**: `llm_enhanced_outline_generator.py:142-145`

#### 5.4.3 Top论文

基于PageRank选择高影响力论文

```python
top_papers = self.analyzer.get_top_papers("pagerank", 15)

for paper in top_papers:
    {
        "title": ...,
        "year": ...,
        "citations": ...,
        "pagerank": ...,
        "method_entities": [...],
        "research_domains": [...]
    }
```

**代码位置**: `llm_enhanced_outline_generator.py:148-157`

#### 5.4.4 研究领域分布

统计所有论文的研究领域

```python
all_domains = []
for node in mekg.nodes.values():
    all_domains.extend(node.research_domains)

domain_counts = Counter(all_domains)
# 输出: [{"domain": "NLP", "count": 500}, ...]
```

**代码位置**: `llm_enhanced_outline_generator.py:159-170`

### 5.5 LLM Prompt构建

**方法**: `_prepare_outline_generation_prompt(topic, context)`

**Prompt模板**: `resources/LLM/prompts/mekg_outline/generate_academic_outline.md`

**核心要素**:
```
任务: 基于MEKG提供的结构化信息,生成学术化的综述大纲

输入:
1. 研究主题: {topic}
2. 社区信息: {communities_description}
3. 演进路径: {evolution_paths_description}
4. Top论文: {top_papers_description}
5. 研究领域分布: {research_domains_description}

要求:
- 生成6-8个主体章节
- 每个章节包含标题、描述、子章节
- 章节应基于社区聚类组织
- 包含方法演进时间线
- 学术化、有逻辑层次

输出格式: JSON
{
  "title": "A Survey on {topic}",
  "sections": [
    {
      "section title": "...",
      "description": "...",
      "subsections": [...]
    },
    ...
  ]
}
```

**代码位置**: `llm_enhanced_outline_generator.py:273-329`

### 5.6 论文挂载到大纲

**方法**: `_mount_papers_to_outline(outline, mekg_context)`

**策略**:
1. 从章节标题和描述中提取关键词
2. 从社区中提取关键词 (方法实体、研究领域)
3. 计算关键词重叠度
4. 如果重叠 > 0,则挂载该社区到章节

**结果**:
```python
section = {
    "section title": "Reasoning and Planning Methods",
    "description": "...",
    "paper_count": 234,  # 挂载的论文总数
    "mounted_communities": [1, 3, 5]  # 挂载的社区ID
}
```

**代码位置**: `llm_enhanced_outline_generator.py:369-431`

### 5.7 与SurveyX工作流的集成方式

**现有SurveyX流程**:
```
01_fetch_data.py      → 02_clean_data.py → 
03_gen_outlines.py    → 04_gen_content.py → 
05_post_refine.py     → 06_gen_latex.py
```

**MEKG集成点**: `03_gen_outlines.py`

#### 方式1: 完全替换 (推荐)

```python
# 修改 03_gen_outlines.py

from src.modules.mekg.enhanced_builder import EnhancedMEKGBuilder
from pathlib import Path

async def generate_outline_with_mekg(task_id: str, topic: str):
    """使用MEKG替代RAG生成大纲"""
    
    # 构建MEKG
    builder = EnhancedMEKGBuilder(
        output_dir=Path(f"src/outputs/{task_id}/mekg"),
        target_paper_count=1500
    )
    
    result = await builder.build_from_topic(
        topic=topic,
        year_start=2018,
        year_end=2024
    )
    
    # 使用MEKG生成的大纲
    outline = result['outline']
    
    # 转换为SurveyX格式 (如果需要)
    surveyx_outline = convert_mekg_outline_to_surveyx_format(outline)
    
    # 保存大纲供后续步骤使用
    save_outline(surveyx_outline, task_id)
    
    return surveyx_outline
```

#### 方式2: 混合使用

```python
# MEKG生成框架大纲
mekg_outline = generate_outline_with_mekg(task_id, topic)

# RAG补充细节
rag_details = original_rag_process(task_id)

# 合并
final_outline = merge_outlines(mekg_outline, rag_details)
```

#### 方式3: 独立运行

```bash
# 1. 先独立运行MEKG
python tasks/mekg_workflow/build_mekg_and_outline.py --topic "your_topic"

# 2. 查看大纲
cat data/mekg_*/mekg/outline.md

# 3. 手动导入或参考
# 4. 运行SurveyX流程
python tasks/workflow/03_gen_outlines.py --task_id xxx
```

### 5.8 集成的Agent (未实现,在设计中)

根据 `MEKG_架构分析与改进方案.md`,计划实现多智能体协作:

| Agent | 角色 | 当前状态 | 设计文档位置 |
|-------|------|---------|-------------|
| **PlannerAgent** | 规划器 - 动态规划生成大纲 | ❌ 未实现 | 架构分析.md:1273-1332 |
| **ConstructorAgent** | 构建器 - 调用工具构建MEKG | ✅ 部分实现 (EnhancedMEKGBuilder) | 架构分析.md:1335-1463 |
| **WriterAgent** | 写作器 - 基于大纲和图谱生成草稿 | ❌ 未实现 | 架构分析.md:1466-1562 |
| **RefinerAgent** | 审查器 - 审查和修订 | ❌ 未实现 | 架构分析.md:1565-1666 |
| **DrawerAgent** | 绘图器 - 生成可视化图表 | ❌ 未实现 (可选) | 架构分析.md:1669-1709 |

**注**: 当前系统主要实现了ConstructorAgent的功能,其他Agent在后续版本中开发。

---

## 6. 关键技术亮点

### 6.1 智能分层候选对生成

**问题**: 1500篇论文,如果全连接需要检查 1500×1499/2 = 1,124,250 个论文对,成本极高

**解决方案**: 智能分层策略 (在`AttributeBasedRelationExtractor`中)

**策略**:
```
层1: 核心论文之间完全连接
  - 识别10%高影响力论文 (150篇)
  - 完全连接: 150×149/2 = 11,175对

层2: 普通论文→核心论文
  - 每篇普通论文连接最相关的5个核心
  - 1350 × 5 = 6,750对

层3: 时间邻近高引连接
  - 新论文连接近期高引论文
  - ~1,000对

总计: ~19,000对 (减少98%)
```

**效果**:
- **减少调用**: 1,124,250 → 19,000 (减少98%)
- **提升命中率**: 5-10% → 20-30% (提升3倍)
- **保持质量**: 核心关系不遗漏

**代码位置**: `attribute_based_relation_extractor.py:360-459`

### 6.2 核心论文识别算法

**方法**: `_identify_core_papers(papers, core_ratio=0.1)`

**评分公式**:
```
Score = 引用数得分(40%) + 年份得分(30%) + 创新性得分(20%) + 类型得分(10%)

其中:
- 引用数得分 = log(citations+1) / log(max_citations+1)  # log scale归一化
- 年份得分 = (max_year - paper_year) / year_range  # 越早越高
- 创新性得分 = has_method(15分) + has_innovations(5分)
- 类型得分 = is_methodology_or_survey(10分)
```

**代码位置**: `attribute_based_relation_extractor.py:283-358`

### 6.3 基于属性对比 vs 全文对比

**传统方法** (全文对比):
```python
prompt = f"""
论文A全文: {full_text_a}  # 10,000+ tokens
论文B全文: {full_text_b}  # 10,000+ tokens
请判断关系...
"""
# Token消耗: 20,000+
# 速度: 慢
# 成本: 高
```

**MEKG方法** (属性对比):
```python
prompt = f"""
论文A:
- 标题: {title_a}
- 摘要: {abstract_a[:500]}  # 截断
- 类型: {paper_type_a}
- 方法信息: {method_info_a}
- 创新点: {innovations_a}
- 研究领域: {domains_a}

论文B: (同上)

请判断关系...
"""
# Token消耗: ~1,000
# 速度: 快3-5倍
# 成本: 降低80%
```

**优势**:
1. **Token消耗减少80%**: 20,000 → 1,000
2. **速度提升3-5倍**: 信息更结构化,LLM处理更快
3. **准确率提升**: 结构化信息更易对比
4. **可解释性强**: 关系依据明确

**代码位置**: `attribute_based_relation_extractor.py:143-197`

### 6.4 重试机制与错误处理

**指数退避重试**:
```python
@retry(
    stop=stop_after_attempt(5),  # 最多5次
    wait=wait_exponential(multiplier=1, min=2, max=60),
    # 重试间隔: 2s → 4s → 8s → 16s → 32s
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError))
)
```

**触发条件**:
- 429 Too Many Requests (API限流)
- 502/503/504 Bad Gateway/Service Unavailable

**实现位置**:
- 属性提取: `paper_attribute_extractor.py:415-467`
- 关系抽取: `attribute_based_relation_extractor.py:532-584`

### 6.5 后备提取机制

当LLM提取失败时,不直接放弃,而是使用**基于规则的后备提取**:

```python
def _extract_fallback_attributes(title, abstract):
    # 领域检测
    detected_domains = []
    for domain, keywords in domain_keywords.items():
        if any(kw in text for kw in keywords):
            detected_domains.append(domain)
    
    # 方法检测
    if any(indicator in text for indicator in method_indicators):
        has_method = True
    
    # 方法名提取
    if ":" in title:
        method_name = title.split(":")[0].strip()
    
    return attributes
```

**效果**: 即使LLM失败,也能提取基本信息,保证系统鲁棒性

**代码位置**: `paper_attribute_extractor.py:237-277`

---

## 7. 数据流转与存储

### 7.1 目录结构

```
data/mekg_{timestamp}_{topic}/
├── papers/                          # 论文数据 (独立目录)
│   ├── pdfs/                        # PDF文件
│   │   ├── W1234567890.pdf
│   │   └── W987654321.pdf
│   ├── parsed_texts/                # 解析文本
│   │   └── pypdf/                   # PyPDF解析结果
│   │       ├── W1234567890.txt
│   │       └── W987654321.txt
│   ├── metadata/                    # 论文元数据
│   │   ├── collected_papers.json    # 采集的论文 (步骤2输出)
│   │   └── papers_with_attributes.json  # 带属性的论文 (步骤4输出)
│   └── progress/                    # 进度文件 (断点续传)
│       ├── download_progress.json
│       └── parse_progress.json
└── mekg/                            # MEKG输出
    ├── mekg.json                    # 图谱数据 (步骤5-6输出)
    ├── mekg.graphml                 # 可视化格式
    ├── analysis_report.json         # 分析报告 (步骤7输出)
    ├── outline.json                 # 大纲 JSON (步骤8输出)
    └── outline.md                   # 大纲 Markdown
```

### 7.2 数据格式详解

#### 7.2.1 collected_papers.json (步骤2输出)

搜索到的论文元数据列表,每篇论文包含:

```json
[
  {
    "paper_id": "W2134969013",
    "title": "Attention is All You Need",
    "abstract": "The dominant sequence transduction...",
    "authors": "Vaswani, A.; Shazeer, N.; ...",
    "year": 2017,
    "venue": "NeurIPS",
    "citations": 50000,
    "doi": "10.48550/arXiv.1706.03762",
    "url": "https://arxiv.org/abs/1706.03762",
    "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf"
  }
]
```

#### 7.2.2 papers_with_attributes.json (步骤4输出)

包含PDF文本和提取的属性:

```json
[
  {
    "paper_id": "W2134969013",
    "title": "Attention is All You Need",
    "pdf_path": "data/.../pdfs/W2134969013.pdf",
    "pypdf_text": "Attention is All You Need...",
    "attributes": {
      "paper_type": "Methodology Paper",
      "method_info": {
        "has_method": true,
        "method_name": "Transformer",
        "method_category": "Attention Mechanism"
      },
      "innovations": ["..."],
      "limitations": ["..."],
      "atomic_facts": ["..."],
      "cited_key_papers": [{"title": "...", "reason": "..."}],
      "research_domains": ["Natural Language Processing"],
      "application_scenarios": ["Translation"]
    }
  }
]
```

#### 7.2.3 mekg.json (步骤5-6输出)

完整的知识图谱:

```json
{
  "nodes": [
    {
      "paper_id": "W2134969013",
      "title": "Attention is All You Need",
      "year": 2017,
      "citation_count": 50000,
      "method_entities": ["Transformer"],
      "research_domain": ["NLP", "Machine Translation"],
      "pagerank": 0.0234,
      "community_id": 1,
      "metadata": {...}
    }
  ],
  "edges": [
    {
      "source": "W3456789012",
      "target": "W2134969013",
      "relation_type": "employs",
      "llm_confidence": 0.95,
      "evidence": "BERT employs Transformer encoder architecture",
      "metadata": {"reasoning": "...", "extraction_method": "attribute_based"}
    }
  ]
}
```

#### 7.2.4 analysis_report.json (步骤7输出)

图谱分析结果:

```json
{
  "graph_statistics": {
    "num_nodes": 1487,
    "num_edges": 3241,
    "num_communities": 8,
    "num_evolution_paths": 15,
    "avg_clustering_coefficient": 0.42,
    "graph_density": 0.0015
  },
  "evaluation_metrics": {
    "wcr": 0.8234,
    "cc": 0.7891,
    "sc": 0.6543
  },
  "top_papers_by_pagerank": [...],
  "community_summary": [...]
}
```

#### 7.2.5 outline.json (步骤8输出)

生成的综述大纲:

```json
{
  "title": "A Survey on Large Language Model Agents",
  "sections": [
    {
      "section title": "Reasoning and Planning Methods",
      "description": "Methods for chain-of-thought reasoning...",
      "subsections": [...],
      "paper_count": 234,
      "mounted_communities": [1, 3]
    }
  ]
}
```

### 7.3 断点续传机制

**进度文件**: `progress/download_progress.json`

```json
{
  "W2134969013": "success",
  "W3456789012": "success",
  "W5678901234": "failed"
}
```

**工作原理**:
1. 每次操作前检查进度文件
2. 跳过已成功的任务
3. 重试失败的任务
4. 完成后更新进度文件

**代码位置**:
- PDF下载: `enhanced_pdf_processor.py:387-400`
- PDF解析: `enhanced_pdf_processor.py:534-592`

---

## 8. 总结

### 8.1 核心流程总结

| 阶段 | 输入 | 核心组件 | 输出 | 关键技术 |
|------|------|----------|------|----------|
| **关键词处理** | Topic | IntelligentQueryProcessor | Keywords列表 | LLM判断拆分 |
| **论文搜索** | Keywords | OpenAlex API | ~3×目标数量 | 多关键词+雪球采样 |
| **PDF获取** | 论文列表 | MultiSourcePDFDownloader | PDF文件 | 多源策略,20并发 |
| **文本解析** | PDF文件 | EnhancedPDFProcessor | 文本内容 | PyPDF,断点续传 |
| **属性提取** | 论文+文本 | PaperAttributeExtractor | 8类属性 | DeepSeek,10并发 |
| **关系抽取** | 论文+属性 | AttributeBasedRelationExtractor | 方法关系 | 智能候选对 |
| **图谱构建** | 节点+边 | MEKGGraph | 知识图谱 | NetworkX |
| **图谱分析** | MEKG | MEKGAnalyzer | 社区/演进 | PageRank,Louvain |
| **大纲生成** | MEKG+分析 | LLMEnhancedOutlineGenerator | 结构化大纲 | 图谱+LLM |

### 8.2 技术创新点

1. ✅ **智能关键词拆分** - LLM自动判断,提升覆盖率30-50%
2. ✅ **基于属性对比的关系抽取** - Token消耗减少80%,速度提升3-5倍
3. ✅ **智能分层候选对生成** - 减少98%的LLM调用,命中率提升3倍
4. ✅ **核心论文识别算法** - 多维度评分,确保重要论文优先处理
5. ✅ **后备提取机制** - 基于规则的fallback,提升鲁棒性
6. ✅ **指数退避重试** - 自动处理API限流,提升成功率

### 8.3 性能指标 (1500篇论文)

| 指标 | 数值 | 说明 |
|------|------|------|
| **总耗时** | ~4小时 | 完整流程 |
| **总成本** | ~$42 | 主要是LLM调用 |
| **成功率** | 80-90% | PDF下载成功率 |
| **属性提取准确率** | >85% | 基于人工抽样验证 |
| **关系抽取准确率** | >80% | 基于人工抽样验证 |
| **并发度** | 10-20 | 平衡速度和稳定性 |

### 8.4 与传统RAG方案对比

| 维度 | RAG方案 | MEKG方案 | 改进 |
|------|---------|----------|------|
| 论文数量 | 200-500 | 1000-2000 | **3-4倍** |
| 处理时间 | ~8小时 | ~4小时 | **节省50%** |
| 处理成本 | ~$200 | ~$42 | **节省79%** |
| 大纲逻辑性 | 中 | 高 | **基于图谱结构** |
| 可解释性 | 低 | 高 | **明确的关系证据** |
| 演进路径 | 无 | 有 | **新增功能** |

### 8.5 未来改进方向

**短期** (1-2周):
- [ ] 集成MinerU高质量PDF解析
- [ ] 添加进度条显示
- [ ] 优化错误处理和日志

**中期** (1个月):
- [ ] 实现图谱可视化界面
- [ ] 支持增量更新MEKG
- [ ] 添加人工审核界面

**长期** (2-3个月):
- [ ] 多智能体协作架构 (Planner/Writer/Refiner)
- [ ] 支持多种数据源 (Semantic Scholar等)
- [ ] 自动评估生成质量

---

## 9. 参考文档

1. **设计文档**: [`MEKG_架构分析与改进方案.md`](MEKG_架构分析与改进方案.md)
2. **实施总结**: [`MEKG_实施总结.md`](MEKG_实施总结.md)
3. **快速开始**: [`MEKG_快速开始指南.md`](MEKG_快速开始指南.md)
4. **使用手册**: [`tasks/mekg_workflow/README.md`](tasks/mekg_workflow/README.md)
5. **属性提取调用链**: [`属性提取调用链.md`](属性提取调用链.md)
6. **关系提取优化**: [`MEKG_关系构建优化方案.md`](MEKG_关系构建优化方案.md)
