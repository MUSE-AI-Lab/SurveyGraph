
# SurveyGraph 技术体系全景总结

> **文档目的**：为开题答辩和论文投稿提供精炼、准确、系统的技术总结
> 
> **核心定位**：SurveyGraph 是一个**基于多层进化知识图谱（MEKG）的自主科研智能体**，通过模拟人类顶尖学者的认知过程，实现从"资料汇总"到"知识创造"的质的飞跃。

---

## 目录

1. [MEKG 知识图谱构建全流程](#1-mekg-知识图谱构建全流程)
2. [双重大纲生成创新（Top-down + Bottom-up）](#2-双重大纲生成创新top-down--bottom-up)
3. [基于大纲的论文重分类机制](#3-基于大纲的论文重分类机制)
4. [基于 MEKG 的智能写作机制](#4-基于-mekg-的智能写作机制)
5. [基于 MEKG 的多维评测体系](#5-基于-mekg-的多维评测体系)
6. [系统架构与流水线设计](#6-系统架构与流水线设计)

---

## 1. MEKG 知识图谱构建全流程

### 1.1 什么是 MEKG

**MEKG (Methods-Entity Knowledge Graph)** 是一个以**方法实体**为核心的学术知识图谱。与传统的引用网络不同，MEKG 不仅记录论文之间的引用关系，还深入分析论文的语义内容，提取方法、任务、数据集等实体，并发现它们之间的语义关系。

### 1.2 语义实体类型（7种）

MEKG 从论文中抽取以下 7 种语义实体：

| 实体类型 | 英文名 | 描述 |
|---------|--------|------|
| **研究问题** | PROBLEM | 论文试图解决的核心问题 |
| **方法/技术** | METHOD | 论文提出或使用的方法 |
| **模型/架构** | MODEL | 具体的模型名称或架构 |
| **任务** | TASK | 论文针对的具体任务 |
| **数据集** | DATASET | 使用的数据集 |
| **评估指标** | METRIC | 使用的评估指标 |
| **创新点** | INNOVATION | 论文的主要创新贡献 |

### 1.3 关系类型（21种）

MEKG 支持 5 大类共 21 种关系类型：

#### 结构关系（基于引用网络）
- `cites` / `cited_by` - 引用关系
- `co_cited` - 共被引（两篇论文被同一篇论文引用）
- `bibliographic_coupling` - 文献耦合（两篇论文引用相同的论文）

#### 语义关系（基于内容分析）
- `extends` - 扩展（B 扩展了 A 的方法）
- `improves` - 改进（B 改进了 A 的方法）
- `compares` - 比较（B 与 A 进行了对比实验）
- `applies` - 应用（B 将 A 的方法应用到新领域）
- `contradicts` - 矛盾（B 的结论与 A 矛盾）
- `supports` - 支持（B 的结论支持 A）

#### 概念关系（基于共享实体）
- `shares_method` - 共享方法
- `shares_task` - 共享任务
- `shares_dataset` - 共享数据集
- `shares_model` - 共享模型
- `shares_problem` - 共享问题

#### 时间关系
- `precedes` / `follows` - 时间先后
- `contemporary` - 同时期

#### 作者关系
- `same_author` - 同作者
- `same_venue` - 同会议/期刊
- `same_institution` - 同机构

### 1.4 四层关系发现策略

MEKG 采用**分层过滤机制**，先用低成本的规则过滤出"潜在关联对"，再用高成本的 LLM 进行语义确认：

```
┌─────────────────────────────────────────────────────────────────┐
│                    四层关系发现策略                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  第一层：引用关系 (100% 可靠, O(1) 复杂度)                        │
│  ├── 直接从论文元数据获取                                        │
│  └── 包括：直接引用、共被引、文献耦合                             │
│                                                                 │
│  第二层：引用上下文分析 (规则 + LLM)                              │
│  ├── 分析引用句的上下文                                          │
│  ├── 使用规则匹配常见模式                                        │
│  └── 复杂情况使用 LLM 判断                                       │
│                                                                 │
│  第三层：共享实体分析 (语义匹配, O(N) 复杂度)                      │
│  ├── 比较两篇论文的语义实体                                      │
│  ├── 发现共享方法、任务、数据集等关系                             │
│  └── 这是"方法论拆解"的核心实现                                  │
│                                                                 │
│  第四层：LLM 深度分析 (复杂关系)                                  │
│  ├── 对于无法通过规则判断的关系                                  │
│  ├── 使用 LLM 分析论文摘要和方法描述                              │
│  └── 判断是否存在扩展、改进等语义关系                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**代码实现**（[`mekg/src/survey/pipeline.py`](../mekg/src/survey/pipeline.py:1653)）：

```python
async def _build_mekg(self) -> Dict:
    """构建MEKG图谱"""
    # 1. 论文采集（支持用户上传 + arXiv 搜索）
    uploaded_papers = await self._process_uploaded_files(self.config.uploaded_files)
    arxiv_papers = await self._collect_arxiv_papers(remaining_count)
    
    # 2. 论文分类
    classifier = PaperClassifier()
    classified = classifier.classify_papers(papers)
    
    # 3. 关系发现（支持 Memgraph 加速）
    if self.config.use_memgraph:
        relations = await self._discover_relations_with_memgraph(papers, classified)
    else:
        discoverer = RelationDiscoverer(use_llm=True, max_workers=50)
        relations = discoverer.discover_relations(papers, classified, max_pairs=500)
    
    # 4. 构建 MEKG 数据结构
    return self._build_mekg_data(papers, relations, classified)
```

### 1.5 核心论文发现算法

SurveyGraph 采用**加权 PageRank 变体算法**来识别核心论文：

$$Score(P_i) = \alpha \cdot PageRank(G_{cite}) + \beta \cdot \log(Citations) + \gamma \cdot Recency(Year) + \delta \cdot Centrality(G_{semantic})$$

**代码实现**（[`mekg/src/core/analyzer.py`](../mekg/src/core/analyzer.py:72)）：

```python
def calculate_centrality_metrics(self) -> Dict[str, Dict[str, float]]:
    """计算所有节点的中心性指标"""
    # 使用 igraph 加速（比 NetworkX 快 100 倍）
    if self.use_igraph and self.ig_adapter:
        pagerank_normalized = self.ig_adapter.pagerank(damping=0.85)
        betweenness = self.ig_adapter.betweenness_centrality(directed=True)
    else:
        # 回退到 NetworkX
        pagerank = nx.pagerank(self.nx_graph, alpha=0.85, max_iter=100)
        betweenness = nx.betweenness_centrality(self.nx_graph, normalized=True)
    
    # 更新节点属性
    for node_id, m in metrics.items():
        node = self.graph.get_node(node_id)
        node.pagerank = m["pagerank"]
        node.betweenness_centrality = m["betweenness"]
```

---

## 2. 双重大纲生成创新（Top-down + Bottom-up）

### 2.1 创新点概述

传统方法存在两个极端问题：
- **纯 Top-down 的问题**：容易产生"幻觉"或陈词滥调，忽略领域最新进展
- **纯 Bottom-up 的问题**：容易导致结构松散，缺乏逻辑主线

SurveyGraph 的创新在于**融合两种策略**，确保大纲既有**逻辑的严密性**，又有**内容的覆盖度**。

### 2.2 混合大纲生成流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    混合大纲生成流程 (Hybrid Outline Generation)           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────┐         ┌─────────────────────┐              │
│   │   Top-down 规划      │         │   Bottom-up 涌现     │              │
│   │   (宏观框架)         │         │   (微观聚类)         │              │
│   │                     │         │                     │              │
│   │  LLM 生成标准框架    │         │  Embedding + 聚类    │              │
│   │  - Introduction     │         │  - HDBSCAN (推荐)   │              │
│   │  - Background       │         │  - K-Means (备选)   │              │
│   │  - Methods          │         │  - Agglomerative    │              │
│   │  - Evaluation       │         │                     │              │
│   │  - Conclusion       │         │  自动发现研究主题    │              │
│   └──────────┬──────────┘         └──────────┬──────────┘              │
│              │                               │                          │
│              └───────────────┬───────────────┘                          │
│                              ▼                                          │
│                    ┌─────────────────────┐                              │
│                    │   Intelligent Merge  │                              │
│                    │   (智能融合)         │                              │
│                    │                     │                              │
│                    │  语义相似度匹配      │                              │
│                    │  消除重复主题        │                              │
│                    │  补充遗漏方向        │                              │
│                    └──────────┬──────────┘                              │
│                               ▼                                          │
│                    ┌─────────────────────┐                              │
│                    │   Final Outline      │                              │
│                    │   (三级大纲结构)     │                              │
│                    └─────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Top-down 规划

**代码实现**（[`src/modules/outline/hybrid_outline_generator.py`](../src/modules/outline/hybrid_outline_generator.py:1)）：

```python
def _generate_top_down_outline(self, topic: str, reference_surveys: List[Dict] = None) -> TopDownOutline:
    """Top-down 大纲生成"""
    prompt = f"""
    You are an expert in writing comprehensive academic survey papers.
    Given the topic: "{topic}"
    Generate a high-level survey outline following standard academic survey structure.
    Requirements:
    1. Include Introduction, main body sections (4-6 sections), and Conclusion
    2. Main body sections should cover: Background, Core Methods, Applications,
       Evaluation/Benchmarks, Challenges and Future Directions
    """
    return LLM.generate(prompt)
```

### 2.4 Bottom-up 涌现（核心创新）

**技术架构**：

1. **Embedding 向量化**：使用 HuggingFace Sentence Transformer 对 "Title + Abstract" 进行向量化
2. **聚类算法选择**：
   - **HDBSCAN（推荐）**：自动发现聚类数量，支持任意形状聚类，自动识别噪声点
   - **K-Means（备选）**：需要预设 K 值，适合已知聚类数的场景
3. **主题提取**：使用 LLM 分析每个聚类的论文，提取主题标题、描述、关键词

**算法选择策略**：

| 论文数量 | 推荐算法 | 原因 |
|---------|---------|------|
| < 20 | K-Means | 论文太少，HDBSCAN 可能无法形成有效聚类 |
| 20-50 | K-Means | 中等数量，K-Means 更稳定 |
| 50-200 | HDBSCAN | 适合 HDBSCAN 自动发现聚类 |
| > 200 | HDBSCAN | 大量论文，HDBSCAN 效果最好 |

**代码实现**：

```python
def _cluster_papers_with_embedding(self, topic: str, papers: List[Dict]) -> ClusteringResult:
    """基于 Embedding 的论文聚类"""
    # Step 1: 生成 Embedding
    texts = [f"Title: {p['title']}\nAbstract: {p['abstract']}" for p in papers]
    embeddings = self.embed_agent.batch_local_embed(texts)
    embeddings = normalize(embeddings, norm='l2')  # L2 归一化
    
    # Step 2: 执行聚类
    if self.algorithm == "hdbscan":
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=max(3, len(papers) // 20),
            min_samples=2,
            metric='euclidean',
            cluster_selection_method='eom'
        )
    else:
        n_clusters = min(7, len(papers) // 3)
        clusterer = KMeans(n_clusters=n_clusters, random_state=42)
    
    labels = clusterer.fit_predict(embeddings)
    
    # Step 3: 使用 LLM 提取主题
    for cluster in clusters:
        cluster.title, cluster.description = self._extract_topic_with_llm(cluster, papers)
    
    # Step 4: 计算聚类质量（轮廓系数）
    silhouette = silhouette_score(embeddings, labels)
    
    return ClusteringResult(clusters=clusters, silhouette_score=silhouette)
```

### 2.5 智能融合算法

```python
def _merge_outlines(self, topic: str, top_down: TopDownOutline, bottom_up_themes: List[Theme]) -> HybridOutline:
    """智能融合两种大纲"""
    final_outline = top_down.copy()
    
    for theme in bottom_up_themes:
        # 计算主题与骨架各章节的语义相似度
        similarities = [
            cosine_similarity(theme.embedding, section.embedding)
            for section in top_down.sections
        ]
        
        best_match_section = top_down.sections[argmax(similarities)]
        
        if max(similarities) > threshold:
            # 相似度高，作为子章节插入
            best_match_section.add_subsection(theme)
        else:
            # 发现了新颖方向，新建独立章节
            final_outline.insert_new_section(theme, position="before_conclusion")
    
    return final_outline
```

---

## 3. 基于大纲的论文重分类机制

### 3.1 设计动机

初始的论文分类基于 `PaperClassifier` 的硬编码分类体系，可能与生成的大纲结构不匹配。论文重分类机制在大纲生成后，基于大纲结构重新生成分类体系（Taxonomy），并对所有论文进行多标签分类。

### 3.2 重分类流程

**代码实现**（[`mekg/scripts/tools/reclassify_papers_with_llm.py`](../mekg/scripts/tools/reclassify_papers_with_llm.py:1)）：

```
┌─────────────────────────────────────────────────────────────────┐
│                    论文重分类流程                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Step 1: 读取大纲，生成 Taxonomy                                 │
│  ├── 提取技术性章节（排除 Introduction/Conclusion/Background）   │
│  ├── 使用 LLM 生成 5-8 个主分类，每个 2-4 个子分类               │
│  └── 确保每个技术章节都有对应的分类                              │
│                                                                 │
│  Step 2: 200 并发 LLM 分类                                       │
│  ├── 对每篇论文进行多标签分类（1-3 个分类）                      │
│  ├── 使用论文标题 + 摘要作为输入                                 │
│  └── 使用模糊匹配确保分类名称的鲁棒性（阈值 0.7）                │
│                                                                 │
│  Step 3: 更新 MEKG 数据                                          │
│  ├── 每篇论文的 all_categories 字段保存所有分类                  │
│  ├── 第一个分类作为主分类                                        │
│  └── 更新 categories 统计                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 核心代码

```python
class LLMPaperClassifier:
    def generate_taxonomy(self, outline_data: Dict, topic: str) -> List[TaxonomyNode]:
        """使用 LLM 基于大纲生成分类体系"""
        prompt = GENERATE_TAXONOMY_PROMPT.format(
            topic=topic,
            outline_text=outline_text
        )
        # 生成 5-8 个主分类，每个 2-4 个子分类
        return taxonomy
    
    def classify_paper(self, paper: Dict) -> PaperClassification:
        """使用 LLM 分类单篇论文（支持多标签，1-3 个分类）"""
        prompt = CLASSIFY_PAPER_PROMPT.format(
            title=paper["title"],
            abstract=paper["abstract"],
            taxonomy_text=self.taxonomy_text
        )
        # 返回 1-3 个分类，按置信度排序
        return classifications
    
    def classify_papers_concurrent(self, papers: List[Dict]) -> Dict[str, PaperClassification]:
        """200 并发分类所有论文"""
        with ThreadPoolExecutor(max_workers=200) as executor:
            futures = {executor.submit(self.classify_paper, paper): paper for paper in papers}
            for future in tqdm(as_completed(futures), total=len(futures)):
                result = future.result()
                results[paper_id] = result
        return results
```

---

## 4. 基于 MEKG 的智能写作机制

### 4.1 演化叙事分析（Evolutionary Narrative）

SurveyGraph 不仅仅是罗列论文，它还能讲述"科学故事"。通过 `EvolutionaryAnalyzer` 模块，将离散的论文数据转化为连贯的历史叙事。

**五步分析法**（[`src/modules/analysis/evolutionary_analyzer.py`](../src/modules/analysis/evolutionary_analyzer.py:1)）：

```python
class EvolutionaryAnalyzer:
    def analyze(self, topic: str, papers: List[Dict], relations: List[Dict] = None) -> EvolutionaryAnalysis:
        # Step 1: 基础统计（年份分布、增长率）
        statistics = self._compute_statistics(sorted_papers)
        
        # Step 2: 里程碑识别（LLM 识别关键技术突破）
        milestones = self._identify_milestones(topic, sorted_papers)
        
        # Step 3: 阶段划分（划分演化阶段如"萌芽期"、"爆发期"）
        phases = self._analyze_phases(topic, milestones, statistics)
        
        # Step 4: 趋势预测（基于近两年论文预测未来方向）
        trends = self._predict_trends(topic, sorted_papers, phases)
        
        # Step 5: 叙事生成（生成连贯的学术历史故事）
        narrative = self._generate_narrative(topic, phases, milestones, trends)
        
        return EvolutionaryAnalysis(
            timeline=milestones,
            phases=phases,
            trends=trends,
            narrative=narrative,
            statistics=statistics
        )
```

**输出示例**：

```json
{
  "phases": [
    {"name": "萌芽期", "start": 2018, "end": 2020, "description": "预训练语言模型兴起"},
    {"name": "爆发期", "start": 2020, "end": 2022, "description": "提示工程方法涌现"},
    {"name": "成熟期", "start": 2023, "end": "至今", "description": "Agent 系统成为主流"}
  ],
  "milestones": [
    {"year": 2018, "event": "BERT 发布", "paper": "BERT: Pre-training of Deep Bidirectional Transformers"},
    {"year": 2020, "event": "GPT-3 展示 Few-shot 能力", "paper": "Language Models are Few-Shot Learners"}
  ],
  "narrative": "大语言模型工具使用领域的发展可以追溯到 2018 年..."
}
```

### 4.2 写-评-改一体化机制（Reflective Content Generation）

SurveyGraph 采用**闭环反思机制**，实现"写-评-改"的迭代优化循环。

**代码实现**（[`src/models/generator/reflective_content_generator.py`](../src/models/generator/reflective_content_generator.py:1)）：

```python
@dataclass
class ReflectionConfig:
    """反思配置"""
    enable_section_reflection: bool = True      # 启用章节级反思
    section_reflection_max_turns: int = 3       # 最大迭代次数
    quality_threshold: float = 3.5              # 质量阈值 (1-5 分制)
    enable_global_evaluation: bool = True       # 启用全局评估
    enable_parallel_reflection: bool = True     # 启用并行反思
    parallel_reflection_workers: int = 10       # 并行工作线程数
    
    skip_sections: List[str] = field(default_factory=lambda: [
        "Introduction", "Conclusion", "Abstract", "References"
    ])
```

**反思流程**：

```
┌─────────────────────────────────────────────────────────────────┐
│                    章节级反思状态机                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐                                              │
│   │ Draft        │ ──────────────────────────────────────┐      │
│   │ Generation   │                                       │      │
│   └──────┬───────┘                                       │      │
│          │                                               │      │
│          ▼                                               │      │
│   ┌──────────────┐                                       │      │
│   │ Evaluation   │ ◄─────────────────────────────────────┤      │
│   │ (评分细则)   │                                       │      │
│   └──────┬───────┘                                       │      │
│          │                                               │      │
│          ▼                                               │      │
│   ┌──────────────┐     Yes    ┌──────────────┐          │      │
│   │ Score >=     │ ──────────►│ Finalize     │          │      │
│   │ Threshold?   │            │ (完成)       │          │      │
│   └──────┬───────┘            └──────────────┘          │      │
│          │ No                                            │      │
│          ▼                                               │      │
│   ┌──────────────┐                                       │      │
│   │ Analysis     │                                       │      │
│   │ Feedback     │                                       │      │
│   └──────┬───────┘                                       │      │
│          │                                               │      │
│          ▼                                               │      │
│   ┌──────────────┐                                       │      │
│   │ Regeneration │ ──────────────────────────────────────┘      │
│   │ (重写)       │                                              │
│   └──────────────┘                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**并行反思模式**：

```python
def _content_fulfill_with_parallel_reflection(self, ...):
    """并行反思模式：先串行生成所有内容，然后并行反思所有章节"""
    
    # Phase 1: 串行生成所有章节内容（不进行反思）
    for section in outlines.sections:
        content = self.write_content_iteratively(...)
        sections_to_reflect.append((section.title, content_index, papers))
    
    # Phase 2: 并行反思所有章节
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(reflect_task, task_info): task_info for task_info in sections_to_reflect}
        for future in tqdm(as_completed(futures), total=len(futures)):
            content_index, reflected_content, history = future.result()
            mainbody[content_index] = reflected_content
```

### 4.3 批判性分析增强（Critical Analysis Refiner）

**代码实现**（[`src/modules/post_refine/critical_analysis_refiner.py`](../src/modules/post_refine/critical_analysis_refiner.py:1)）：

后处理模块，用于增强综述内容的批判性分析深度：

1. **识别缺乏定量证据的段落**：检测"显著优于"等模糊表述，建议补充具体数字
2. **识别缺乏批判性分析的段落**：检测纯描述性内容，建议添加"为什么有效"的解释
3. **添加失败模式分析**：检测方法描述段落，建议添加局限性讨论
4. **添加方法间的权衡分析**：检测比较段落，建议添加权衡分析

```python
class CriticalAnalysisRefiner:
    def analyze_content(self, content: str, paper_info: Dict = None) -> RefineResult:
        # 1. 分割段落
        paragraphs = self._split_paragraphs(content)
        
        # 2. 分析每个段落
        for para in paragraphs:
            issues = self._analyze_paragraph(para)
            # 检查：定量证据、批判性分析、失败模式、权衡分析
        
        # 3. 如果启用增强，进行内容优化
        if self.enable_enhancement and all_issues:
            refined_content, improvements = self._enhance_content(content, paragraphs, all_issues)
        
        return RefineResult(
            original_content=content,
            refined_content=refined_content,
            issues_found=all_issues,
            improvements_made=improvements,
            statistics=statistics
        )
```

---

## 5. 基于 MEKG 的多维评测体系

### 5.1 五大核心评估指标

SurveyGraph 提出了 5 个基于图谱的评估指标，从多个维度评估综述质量：

| 指标 | 全称 | 描述 | 公式 |
|------|------|------|------|
| **WCR** | Weighted Centrality Recall | 加权中心性召回率，评估核心论文覆盖 | `WCR = Σ(centrality(p) for p in cited ∩ core) / Σ(centrality(p) for p in core)` |
| **CC** | Community Coverage | 社区覆盖率，评估研究方向覆盖 | `CC = |covered_communities| / |total_communities|` |
| **SC** | Structural Coherence | 结构一致性，评估大纲与图谱结构的对应 | 基于演进路径长度和覆盖率的综合指标 |
| **RA** | Relation Accuracy | 关系准确性，验证综述中描述的论文关系是否与图谱一致 | 基于关系匹配的准确率 |
| **TC** | Temporal Coverage | 时间覆盖率，评估时间范围覆盖 | 基于年份分布的覆盖率 |

### 5.2 WCR（加权中心性召回率）

**设计动机**：评估综述是否覆盖了领域内的核心论文。

**代码实现**（[`mekg/src/survey/evaluator.py`](../mekg/src/survey/evaluator.py:1)）：

```python
def _calculate_wcr(self, cited_papers: Set[str]) -> Tuple[float, Dict]:
    """计算加权中心性召回率"""
    # 获取核心论文（按 PageRank 排序的 Top-K）
    core_papers = self._get_core_papers(top_k=50)
    
    # 计算被引用的核心论文的权重和
    cited_core_weight = sum(
        self.paper_centrality.get(p, 0)
        for p in cited_papers if p in core_papers
    )
    
    # 计算所有核心论文的权重和
    total_core_weight = sum(
        self.paper_centrality.get(p, 0)
        for p in core_papers
    )
    
    wcr = cited_core_weight / total_core_weight if total_core_weight > 0 else 0.0
    
    return wcr, {
        "cited_core_count": len(cited_papers & core_papers),
        "total_core_count": len(core_papers),
        "cited_core_weight": cited_core_weight,
        "total_core_weight": total_core_weight
    }
```

### 5.3 CC（社区覆盖率）

**设计动机**：评估综述是否覆盖了所有主要研究方向。

**代码实现**（[`mekg/src/core/analyzer.py`](../mekg/src/core/analyzer.py:365)）：

```python
def calculate_cc(self) -> float:
    """计算 CC (Community Coverage)"""
    # 统计每个社区的论文数
    community_sizes = defaultdict(int)
    for node in self.graph.nodes.values():
        if node.community_id is not None:
            community_sizes[node.community_id] += 1
    
    # 计算熵（Shannon Entropy）来衡量分布均匀性
    total = sum(community_sizes.values())
    entropy = 0.0
    for size in community_sizes.values():
        if size > 0:
            p = size / total
            entropy -= p * np.log2(p)
    
    # 归一化熵
    max_entropy = np.log2(len(community_sizes))
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
    
    # CC: 社区数量 * 分布均匀性
    num_communities = len(community_sizes)
    cc = (num_communities / 10.0) * normalized_entropy  # 假设理想社区数约 10
    cc = min(cc, 1.0)
    
    return cc
```

### 5.4 SC（结构一致性）

**设计动机**：评估综述结构是否与知识图谱的拓扑结构一致。

```python
def calculate_sc(self) -> float:
    """计算 SC (Structural Coherence)"""
    # 找到演进路径
    paths = self.find_evolution_paths()
    
    if not paths:
        return 0.0
    
    # 计算路径的平均长度（越长说明演进脉络越清晰）
    avg_path_length = np.mean([len(p) for p in paths])
    
    # 计算路径覆盖的节点比例
    nodes_in_paths = set()
    for path in paths:
        nodes_in_paths.update(path)
    
    coverage = len(nodes_in_paths) / self.graph.node_count()
    
    # SC 综合考虑路径长度和覆盖率
    normalized_length = min(avg_path_length / 5.0, 1.0)
    sc = 0.6 * normalized_length + 0.4 * coverage
    
    return sc
```

### 5.5 综合评估流程

**代码实现**（[`mekg/src/survey/evaluator.py`](../mekg/src/survey/evaluator.py:1)）：

```python
class MEKGEvaluator:
    """基于 MEKG 知识图谱的综述评估器"""
    
    def __init__(self, mekg_data: Dict, weights: Dict[str, float] = None):
        self.mekg_data = mekg_data
        self.weights = weights or {
            "wcr": 0.25,  # 核心论文覆盖
            "cc": 0.25,   # 社区覆盖
            "sc": 0.20,   # 结构一致性
            "ra": 0.15,   # 关系准确性
            "tc": 0.15    # 时间覆盖
        }
    
    def evaluate(self, survey_content: str, survey_outline: Dict = None) -> EvaluationResult:
        """执行综合评估"""
        # 1. 提取综述中引用的论文
        cited_papers, unknown_citations = self._extract_citations(survey_content)
        
        # 2. 计算各项指标
        wcr, wcr_details = self._calculate_wcr(cited_papers)
        cc, cc_details = self._calculate_cc(cited_papers)
        sc, sc_details = self._calculate_sc(cited_papers, survey_outline)
        ra, ra_details = self._calculate_ra(survey_content, cited_papers)
        tc, tc_details = self._calculate_tc(cited_papers)
        
        # 3. 计算综合得分
        overall_score = (
            self.weights["wcr"] * wcr +
            self.weights["cc"] * cc +
            self.weights["sc"] * sc +
            self.weights["ra"] * ra +
            self.weights["tc"] * tc
        )
        
        return EvaluationResult(
            overall_score=overall_score,
            wcr=wcr,
            cc=cc,
            sc=sc,
            ra=ra,
            tc=tc,
            details={...}
        )
```

---

## 6. 系统架构与流水线设计

### 6.1 完整流水线步骤

**代码实现**（[`mekg/src/survey/pipeline.py`](../mekg/src/survey/pipeline.py:45)）：

```python
class PipelineStep(Enum):
    """流水线步骤枚举"""
    NOT_STARTED = 0
    MEKG_BUILT = 1              # Step 1: MEKG 数据构建完成
    OUTLINE_GENERATED = 2       # Step 2: 大纲生成完成
    PAPERS_RECLASSIFIED = 3     # Step 2.5: 论文重分类完成
    CONTENT_GENERATED = 4       # Step 3: Survey 主体内容生成完成
    POST_REFINED = 5            # Step 4: PostRefiner 文本优化完成
    TABLES_GENERATED = 6        # Step 5: 表格生成完成
    VISUALS_GENERATED = 7       # Step 6: 动态视觉元素生成完成
    EVALUATED = 8               # Step 7: 评估完成
    CRITICAL_ANALYZED = 9       # Step 7.5: 批判性分析增强完成
    LATEX_GENERATED = 10        # Step 8: LaTeX 生成完成
    VISUALIZATION_DONE = 11     # Step 9: 可视化数据导出完成
    COMPLETED = 12              # 全部完成
```

### 6.2 流水线配置

```python
@dataclass
class PipelineConfig:
    """流水线配置"""
    # 基本配置
    topic: str
    output_dir: Path
    task_id: str = ""
    
    # 论文采集配置
    max_papers: int = 100
    year_start: int = 2020
    year_end: int = 2024
    
    # 增强论文收集配置
    use_enhanced_collector: bool = True
    use_survey_strategy: bool = False
    use_embedding_filter: bool = True
    embedding_threshold: float = 0.3
    
    # 图谱构建配置
    use_llm_relations: bool = True
    max_relation_pairs: int = 500
    use_memgraph: bool = False
    
    # 反思机制配置
    enable_reflection: bool = True
    reflection_max_iterations: int = 3
    reflection_quality_threshold: float = 3.5
    enable_global_evaluation: bool = True
    
    # 新模块配置
    use_hybrid_outline: bool = True
    use_global_reflector: bool = True
    use_evolutionary_analyzer: bool = True
    
    # 批判性分析配置
    enable_critical_analysis: bool = True
    critical_analysis_auto_enhance: bool = True
```

### 6.3 断点续传机制

SurveyGraph 支持**断点续传**，每个步骤完成后自动保存检查点，72 小时内有效：

```python
def _save_checkpoint(self, step: PipelineStep, **kwargs):
    """保存检查点"""
    checkpoint = CheckpointData(
        step=step,
        timestamp=datetime.now().isoformat(),
        task_id=self.config.task_id,
        topic=self.config.topic,
        papers_count=kwargs.get("papers_count", 0),
        relations_count=kwargs.get("relations_count", 0),
        sections_count=kwargs.get("sections_count", 0)
    )
    
    with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
    
    # 备份 survey.tex 和 mainbody 文件
    self._backup_survey_tex(step)
    self._backup_mainbody_files(step)
```

### 6.4 并行评估优化

为了提升效率，评估阶段采用**并行执行**：

```python
async def _run_evaluation_parallel(self, mekg_data, content_result, outline) -> tuple:
    """并行执行评估任务"""
    with ThreadPoolExecutor(max_workers=3) as executor:
        # 提交所有任务
        future_basic = loop.run_in_executor(executor, run_basic_evaluation)
        future_global = loop.run_in_executor(executor, run_global_reflection)
        future_evolution = loop.run_in_executor(executor, run_evolutionary_analysis)
        
        # 等待所有任务完成
        evaluation, global_result, evolution_result = await asyncio.gather(
            future_basic, future_global, future_evolution
        )
    
    return evaluation, global_result, evolution_result
```

---

## 7. 创新点总结

### 7.1 MEKG 知识图谱创新

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| **7 种语义实体** | 从论文中抽取 PROBLEM、METHOD、MODEL、TASK、DATASET、METRIC、INNOVATION | LLM + 规则混合抽取 |
| **21 种关系类型** | 覆盖结构、语义、概念、时间、作者 5 大类关系 | 四层关系发现策略 |
| **加权 PageRank** | 综合考虑引用、时间、中心性的核心论文发现 | igraph 加速（100 倍性能提升） |

### 7.2 大纲生成创新

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| **Top-down + Bottom-up 融合** | 结合宏观框架和微观聚类 | HDBSCAN/K-Means + 语义相似度匹配 |
| **自动聚类数发现** | HDBSCAN 自动发现研究主题数量 | 无需预设 K 值 |
| **轮廓系数评估** | 自动评估聚类质量 | silhouette_score |
| **论文重分类** | 基于大纲结构重新生成 Taxonomy | 200 并发 LLM 多标签分类 |

### 7.3 写作机制创新

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| **演化叙事分析** | 五步分析法生成领域发展历史 | 里程碑识别 + 阶段划分 + 趋势预测 |
| **写-评-改一体化** | 章节级反思机制 | 质量阈值 3.5 分，最多 3 次迭代 |
| **并行反思模式** | 先串行生成，再并行反思 | ThreadPoolExecutor |
| **批判性分析增强** | 检测并增强薄弱段落 | 定量证据 + 失败模式 + 权衡分析 |

### 7.4 评测体系创新

| 创新点 | 描述 | 技术实现 |
|--------|------|----------|
| **5 大评估指标** | WCR、CC、SC、RA、TC | 基于图谱的多维评估 |
| **图原生评估** | 直接基于 MEKG 结构评估 | 无需人工标注 |
| **可解释性** | 每个指标都有明确的证据链 | 详细的 details 输出 |

---

## 8. 使用示例

### 8.1 命令行运行

```bash
# 从头开始
python tasks/mekg_run.py --topic "Large Language Model Agents" --max_papers 200

# 从断点恢复
python tasks/mekg_run.py --resume --task_id "2025-12-15-1933_Large_Language_Model"

# 启用所有增强功能
python tasks/mekg_run.py \
    --topic "LLM Tool Use" \
    --max_papers 200 \
    --enable-reflection \
    --reflection-max-iter 3 \
    --reflection-threshold 3.5 \
    --use-hybrid-outline \
    --use-evolutionary-analyzer \
    --run-evaluation
```

### 8.2 Python API

```python
from mekg.src.survey.pipeline import MEKGSurveyPipeline, PipelineConfig

config = PipelineConfig(
    topic="Large Language Model Agents",
    output_dir=Path("outputs"),
    max_papers=200,
    enable_reflection=True,
    use_hybrid_outline=True,
    use_evolutionary_analyzer=True
)

pipeline = MEKGSurveyPipeline(config)
result = await pipeline.run()

print(f"综合得分: {result.evaluation.overall_score:.4f}")
print(f"WCR: {result.evaluation.wcr:.4f}")
print(f"CC: {result.evaluation.cc:.4f}")
```

---

## 9. 参考文献

1. **SciSage**: Section Reflection Optimization - `refer/SciSage-main/core/section_reflection_opt.py`
2. **ARISE**: Full Detailed Review Rubric - `refer/ARISE-main/full_detailed_review_rubric.json`
3. **NetworkX**: Graph Analysis Library
4. **igraph**: High-Performance Graph Library
5. **HDBSCAN**: Hierarchical Density-Based Spatial Clustering