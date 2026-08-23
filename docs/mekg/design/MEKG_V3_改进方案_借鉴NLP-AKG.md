# MEKG V3 改进方案 - 借鉴NLP-AKG

## 一、背景分析

### 1.1 NLP-AKG的核心优势

NLP-AKG是一个针对NLP领域的学术知识图谱，其核心优势在于：

1. **丰富的语义实体**：不仅有元数据，还从论文内容中抽取了Problem、Method、Model、Task、Dataset等语义信息
2. **精确的关系分类**：通过引用上下文+分类器来判断论文间关系类型
3. **实体消歧**：使用K-means聚类对相似实体进行合并
4. **质量控制**：使用XLNet检测器进行实体清洗

### 1.2 我们当前MEKG V2的不足

1. **实体粒度粗**：主要是论文级别的实体，缺少细粒度语义实体
2. **关系发现不够精确**：主要基于规则和简单的LLM推断
3. **缺少实体消歧**：相同概念可能有不同表述
4. **缺少引用上下文分析**：没有利用引用的上下文来判断关系类型

---

## 二、改进方案设计

### 2.1 扩展实体类型（从5种扩展到12种）

#### 现有实体类型
1. **Paper** - 论文
2. **Author** - 作者
3. **Institution** - 机构
4. **Conference/Journal** - 会议/期刊
5. **Topic** - 主题

#### 新增语义实体类型
6. **Problem** - 论文解决的问题
7. **Method** - 提出的方法
8. **Model** - 提出的模型名称
9. **Task** - 应用的任务
10. **Dataset** - 使用的数据集
11. **Metric** - 评估指标
12. **Innovation** - 主要创新点

### 2.2 扩展关系类型（从21种扩展到35种）

#### 论文内关系（新增14种）
```
# 作者关系
writes: Author → Paper
works_for: Author → Institution

# 发表关系
published_in: Paper → Conference/Journal
published_at: Paper → Year

# 内容关系
solves: Paper → Problem
adopts: Paper → Method
proposes: Paper → Model
works_on: Paper → Task
experiments_on: Paper → Dataset
uses_metric: Paper → Metric
innovates: Paper → Innovation

# 方法-问题关系
method_solves: Method → Problem
model_for_task: Model → Task
```

#### 论文间关系（保留并优化21种）
保持现有的5大类21种关系，但改进发现方式。

### 2.3 改进关系发现流程

#### 当前流程
```
论文A, 论文B → 规则检测 → 简单LLM推断 → 关系
```

#### 改进后流程
```
论文A, 论文B → 引用上下文提取 → 上下文分类 → 精确关系
                    ↓
              共享实体检测 → 基于共享实体的关系推断
```

#### 引用上下文分类
从引用上下文中判断关系类型：

| 关系类型 | 典型上下文模式 |
|---------|---------------|
| **Direct use** | "we use the dataset from [X]", "following [X]'s method" |
| **Extends** | "we extend [X] by", "building upon [X]" |
| **Compares** | "compared with [X]", "outperforms [X]" |
| **Task related** | "similar to [X]", "[X] also addresses this task" |

### 2.4 实体消歧机制

#### 消歧对象
- Task（任务名称可能有多种表述）
- Dataset（数据集名称可能有缩写）
- Method（方法名称可能有变体）
- Model（模型名称可能有版本）

#### 消歧流程
```
1. 实体向量化（使用embedding模型）
2. K-means聚类
3. 选择频率最高的实体作为代表
4. 合并同一聚类的实体
```

### 2.5 实体清洗机制

#### 错误类型
1. **无效数据**：如"21 document corpus"不是具体数据集名称
2. **格式错误**：如"dataset: MNIST"应该只保留"MNIST"
3. **不够具体**：如"a neural network"太泛化
4. **冗余信息**：如"the proposed method achieves..."

#### 清洗流程
```
1. LLM检测错误类型
2. 无效数据 → 删除
3. 其他错误 → 重新抽取
```

---

## 三、技术实现方案

### 3.1 新增模块

```
src/modules/mekg/
├── semantic_entity_extractor.py    # 语义实体抽取器
├── citation_context_analyzer.py    # 引用上下文分析器
├── entity_disambiguator.py         # 实体消歧器
├── entity_cleaner.py               # 实体清洗器
└── enhanced_relation_discoverer.py # 增强关系发现器（已有，需优化）
```

### 3.2 SemanticEntityExtractor（语义实体抽取器）

```python
class SemanticEntityExtractor:
    """
    从论文中抽取语义实体
    
    抽取流程：
    1. 从摘要+引言抽取：Problem, Method, Model, Task
    2. 从实验部分抽取：Dataset, Metric
    3. 综合生成：Innovation
    """
    
    async def extract_from_paper(self, paper: Dict) -> Dict[str, List[str]]:
        """
        从单篇论文抽取语义实体
        
        Args:
            paper: 论文信息（含abstract, full_text等）
        
        Returns:
            {
                "problem": ["..."],
                "method": ["..."],
                "model": ["..."],
                "task": ["..."],
                "dataset": ["..."],
                "metric": ["..."],
                "innovation": ["..."]
            }
        """
        pass
    
    async def extract_from_abstract(self, abstract: str) -> Dict[str, List[str]]:
        """从摘要抽取实体"""
        pass
    
    async def extract_from_tables(self, tables: List[str]) -> Dict[str, List[str]]:
        """从表格抽取Dataset, Metric"""
        pass
```

### 3.3 CitationContextAnalyzer（引用上下文分析器）

```python
class CitationContextAnalyzer:
    """
    分析引用上下文，判断论文间关系类型
    
    关系类型：
    - direct_use: 直接使用被引论文的内容
    - extends: 扩展被引论文的方法
    - compares: 与被引论文进行比较
    - task_related: 与被引论文处理相似任务
    - background: 作为背景知识引用
    """
    
    def __init__(self):
        self.relation_patterns = {
            "direct_use": [
                r"we use .* from \[?\d+\]?",
                r"following \[?\d+\]?",
                r"based on \[?\d+\]?'s",
            ],
            "extends": [
                r"we extend \[?\d+\]?",
                r"building upon \[?\d+\]?",
                r"improve upon \[?\d+\]?",
            ],
            "compares": [
                r"compared with \[?\d+\]?",
                r"outperforms \[?\d+\]?",
                r"better than \[?\d+\]?",
            ],
            "task_related": [
                r"similar to \[?\d+\]?",
                r"\[?\d+\]? also address",
                r"related work .* \[?\d+\]?",
            ],
        }
    
    async def analyze_citation_context(
        self, 
        citing_paper: Dict, 
        cited_paper: Dict,
        context: str
    ) -> Tuple[str, float]:
        """
        分析引用上下文，返回关系类型和置信度
        
        Args:
            citing_paper: 引用论文
            cited_paper: 被引论文
            context: 引用上下文（引用句子及前后文）
        
        Returns:
            (relation_type, confidence)
        """
        pass
    
    def extract_citation_context(
        self, 
        full_text: str, 
        citation_marker: str
    ) -> str:
        """
        从全文中提取引用上下文
        
        Args:
            full_text: 论文全文
            citation_marker: 引用标记（如"[1]"或"Smith et al."）
        
        Returns:
            引用上下文（引用句子及前后1-2句）
        """
        pass
```

### 3.4 EntityDisambiguator（实体消歧器）

```python
class EntityDisambiguator:
    """
    实体消歧器
    
    使用向量聚类对相似实体进行合并
    """
    
    def __init__(self, embed_model: str = "text-embedding-3-small"):
        self.embed_model = embed_model
    
    async def disambiguate(
        self, 
        entities: List[str], 
        entity_type: str,
        n_clusters: int = None
    ) -> Dict[str, str]:
        """
        对实体进行消歧
        
        Args:
            entities: 实体列表
            entity_type: 实体类型（task, dataset, method, model）
            n_clusters: 聚类数量（None则自动确定）
        
        Returns:
            {原实体: 代表实体} 的映射
        """
        # 1. 向量化
        embeddings = await self._embed_entities(entities)
        
        # 2. 聚类
        clusters = self._cluster_entities(embeddings, n_clusters)
        
        # 3. 选择代表实体
        mapping = self._select_representatives(entities, clusters)
        
        return mapping
    
    async def _embed_entities(self, entities: List[str]) -> np.ndarray:
        """向量化实体"""
        pass
    
    def _cluster_entities(
        self, 
        embeddings: np.ndarray, 
        n_clusters: int
    ) -> List[int]:
        """K-means聚类"""
        pass
    
    def _select_representatives(
        self, 
        entities: List[str], 
        clusters: List[int]
    ) -> Dict[str, str]:
        """选择频率最高的实体作为代表"""
        pass
```

### 3.5 EntityCleaner（实体清洗器）

```python
class EntityCleaner:
    """
    实体清洗器
    
    检测并修复抽取错误
    """
    
    ERROR_TYPES = [
        "invalid_data",      # 无效数据
        "incorrect_format",  # 格式错误
        "not_specific",      # 不够具体
        "redundant_info",    # 冗余信息
    ]
    
    async def clean_entity(
        self, 
        entity: str, 
        entity_type: str,
        context: str = None
    ) -> Tuple[str, bool]:
        """
        清洗单个实体
        
        Args:
            entity: 实体值
            entity_type: 实体类型
            context: 抽取上下文
        
        Returns:
            (清洗后的实体, 是否有效)
        """
        # 1. 检测错误类型
        error_type = await self._detect_error(entity, entity_type)
        
        if error_type == "invalid_data":
            return None, False
        elif error_type:
            # 重新抽取
            cleaned = await self._re_extract(entity, entity_type, context, error_type)
            return cleaned, True
        else:
            return entity, True
    
    async def _detect_error(self, entity: str, entity_type: str) -> Optional[str]:
        """检测错误类型"""
        pass
    
    async def _re_extract(
        self, 
        entity: str, 
        entity_type: str, 
        context: str,
        error_type: str
    ) -> str:
        """重新抽取"""
        pass
```

---

## 四、数据库Schema扩展

### 4.1 新增表

```sql
-- 语义实体表
CREATE TABLE semantic_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- problem, method, model, task, dataset, metric, innovation
    entity_value TEXT NOT NULL,
    canonical_value TEXT,       -- 消歧后的标准值
    confidence REAL DEFAULT 1.0,
    source TEXT,                -- abstract, table, full_text
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- 实体聚类表（用于消歧）
CREATE TABLE entity_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    entity_value TEXT NOT NULL,
    is_representative BOOLEAN DEFAULT FALSE,
    frequency INTEGER DEFAULT 1
);

-- 引用上下文表
CREATE TABLE citation_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_paper_id TEXT NOT NULL,
    cited_paper_id TEXT NOT NULL,
    context TEXT NOT NULL,
    relation_type TEXT,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (citing_paper_id) REFERENCES papers(paper_id),
    FOREIGN KEY (cited_paper_id) REFERENCES papers(paper_id)
);

-- 论文内关系表
CREATE TABLE intra_paper_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT NOT NULL,
    source_type TEXT NOT NULL,   -- paper, method, model
    source_value TEXT NOT NULL,
    relation_type TEXT NOT NULL, -- solves, adopts, proposes, works_on, experiments_on, uses_metric
    target_type TEXT NOT NULL,   -- problem, method, model, task, dataset, metric
    target_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- 索引
CREATE INDEX idx_semantic_entities_paper ON semantic_entities(paper_id);
CREATE INDEX idx_semantic_entities_type ON semantic_entities(entity_type);
CREATE INDEX idx_semantic_entities_value ON semantic_entities(entity_value);
CREATE INDEX idx_citation_contexts_citing ON citation_contexts(citing_paper_id);
CREATE INDEX idx_citation_contexts_cited ON citation_contexts(cited_paper_id);
```

### 4.2 扩展现有表

```sql
-- 在papers表中添加字段
ALTER TABLE papers ADD COLUMN has_semantic_entities BOOLEAN DEFAULT FALSE;
ALTER TABLE papers ADD COLUMN semantic_extraction_date TIMESTAMP;
```

---

## 五、实施路线图

### Phase 1: 基础设施（1周）
- [ ] 扩展数据库Schema
- [ ] 实现SemanticEntityExtractor基础框架
- [ ] 实现CitationContextAnalyzer基础框架

### Phase 2: 实体抽取（2周）
- [ ] 实现从摘要抽取Problem, Method, Model, Task
- [ ] 实现从表格抽取Dataset, Metric
- [ ] 实现Innovation综合生成
- [ ] 集成到论文收集流程

### Phase 3: 实体质量控制（1周）
- [ ] 实现EntityCleaner
- [ ] 实现EntityDisambiguator
- [ ] 建立实体质量评估指标

### Phase 4: 关系发现优化（2周）
- [ ] 实现引用上下文提取
- [ ] 实现基于上下文的关系分类
- [ ] 实现基于共享实体的关系推断
- [ ] 优化EnhancedRelationDiscoverer

### Phase 5: 集成与测试（1周）
- [ ] 集成所有模块
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档更新

---

## 六、预期效果

### 6.1 实体丰富度提升
- 从5种实体类型扩展到12种
- 每篇论文平均抽取10+个语义实体

### 6.2 关系精确度提升
- 通过引用上下文分析，关系分类准确率预期达到90%+
- 通过共享实体检测，发现更多隐含关系

### 6.3 知识图谱质量提升
- 实体消歧减少重复实体50%+
- 实体清洗提高实体质量20%+

### 6.4 下游任务效果提升
- Survey大纲生成更加精准
- 论文推荐更加相关
- 知识问答更加准确

---

## 七、与现有系统的兼容性

### 7.1 向后兼容
- 现有的论文数据和关系数据保持不变
- 新增的语义实体和关系作为增强层
- 现有的API和脚本继续可用

### 7.2 渐进式升级
- 可以选择性地对部分论文进行语义实体抽取
- 可以选择性地启用引用上下文分析
- 可以选择性地启用实体消歧

### 7.3 配置选项
```python
# 在构建图谱时可以选择启用的功能
builder = LargeGraphBuilder(
    db_path="data/graph_db/mekg_v3.db",
    enable_semantic_extraction=True,   # 启用语义实体抽取
    enable_citation_context=True,      # 启用引用上下文分析
    enable_entity_disambiguation=True, # 启用实体消歧
    enable_entity_cleaning=True,       # 启用实体清洗
)
```

---

## 八、总结

借鉴NLP-AKG的设计思路，我们可以将MEKG V2升级为MEKG V3，主要改进包括：

1. **扩展实体类型**：从论文级别扩展到语义级别（Problem, Method, Task等）
2. **改进关系发现**：通过引用上下文分析和共享实体检测提高精确度
3. **增加质量控制**：实体清洗和消歧确保知识图谱质量
4. **保持兼容性**：渐进式升级，不影响现有功能

这些改进将使我们的知识图谱更加丰富、精确、可靠，为Survey自动生成提供更好的知识支撑。