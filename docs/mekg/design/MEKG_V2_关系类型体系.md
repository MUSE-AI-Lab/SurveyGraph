# MEKG V2 学术论文关系类型体系

## 设计原则

1. **互斥性**：同一对论文的同一关系类型只能有一条边
2. **完备性**：覆盖所有可能的学术论文关系
3. **层次性**：分为5大类21种关系类型
4. **方向性**：明确定义每种关系的方向语义
5. **可验证性**：每种关系都有明确的判定标准

## 关系类型总览

| 类别 | 关系类型 | 方向 | 发现方式 | 说明 |
|------|---------|------|---------|------|
| **结构关系** | cites | 有向 | 规则 | A引用B |
| | cited_by | 有向 | 规则 | A被B引用 |
| | co_citation | 无向 | 规则 | A和B被同一论文引用 |
| | bibliographic_coupling | 无向 | 规则 | A和B引用相同论文 |
| **语义关系** | extends | 有向 | LLM | A扩展B的方法 |
| | improves | 有向 | LLM | A改进B的性能 |
| | applies | 有向 | LLM | A将B应用到新领域 |
| | compares | 无向 | LLM | A和B进行实验对比 |
| | combines | 有向 | LLM | A结合B和其他方法 |
| | reproduces | 有向 | LLM | A复现B的实验 |
| | refutes | 有向 | LLM | A反驳B的结论 |
| | supports | 有向 | LLM | A验证B的结论 |
| **概念关系** | is_variant_of | 有向 | LLM | A是B的变体 |
| | is_instance_of | 有向 | LLM | A是B方法类别的实例 |
| | shares_methodology | 无向 | 规则 | A和B使用相似方法 |
| | shares_task | 无向 | 规则 | A和B解决相同任务 |
| | shares_dataset | 无向 | 规则 | A和B使用相同数据集 |
| | shares_baseline | 无向 | 规则 | A和B使用相同基线 |
| | shares_architecture | 无向 | LLM | A和B使用相似架构 |
| **时序关系** | precedes | 有向 | 规则 | A是B的前序工作 |
| | succeeds | 有向 | 规则 | A是B的后续工作 |
| | concurrent | 无向 | 规则 | A和B是同期独立工作 |
| **作者关系** | same_author | 无向 | 规则 | A和B有共同作者 |
| | same_group | 无向 | 规则 | A和B来自同一研究组 |

## 详细定义

### 一、结构关系（Structural Relations）

基于引用网络的客观关系，可通过引用数据直接判定。

#### 1. cites（引用）
- **定义**：论文A的参考文献列表中包含论文B
- **方向**：A → B（A引用B）
- **置信度**：1.0（确定性关系）
- **判定标准**：B ∈ A.references

#### 2. cited_by（被引用）
- **定义**：论文A被论文B引用
- **方向**：A → B（A被B引用）
- **置信度**：1.0
- **判定标准**：A ∈ B.references

#### 3. co_citation（同被引）
- **定义**：存在论文C同时引用A和B
- **方向**：无向
- **置信度**：基于共同被引次数
- **学术意义**：表明A和B在某个研究主题上相关

#### 4. bibliographic_coupling（文献耦合）
- **定义**：A和B引用了相同的论文
- **方向**：无向
- **置信度**：|A.refs ∩ B.refs| / 10（最大1.0）
- **阈值**：共同引用≥3篇才建立关系
- **学术意义**：表明A和B基于相似的知识基础

### 二、语义关系（Semantic Relations）

基于内容分析的关系，需要LLM理解论文内容。

#### 5. extends（扩展）
- **定义**：A将B的方法/理论扩展到新的场景、任务或领域
- **方向**：A → B（A扩展B）
- **前提条件**：A的发表时间晚于B
- **示例**：BERT扩展了Transformer到预训练语言模型

#### 6. improves（改进）
- **定义**：A改进了B的方法，在相同任务上取得更好性能
- **方向**：A → B（A改进B）
- **前提条件**：A的发表时间晚于B
- **示例**：RoBERTa改进了BERT的预训练策略

#### 7. applies（应用）
- **定义**：A将B提出的方法应用到新的领域或任务
- **方向**：A → B（A应用B的方法）
- **示例**：将Transformer应用到计算机视觉（ViT）

#### 8. compares（对比）
- **定义**：A和B在实验中进行了直接对比
- **方向**：无向
- **判定标准**：A或B的实验部分包含对方作为baseline

#### 9. combines（结合）
- **定义**：A结合了B的方法和其他方法
- **方向**：A → B（A结合了B）
- **示例**：结合CNN和Transformer的混合架构

#### 10. reproduces（复现）
- **定义**：A复现了B的实验
- **方向**：A → B（A复现B）
- **学术意义**：验证B的可重复性

#### 11. refutes（反驳）
- **定义**：A的实验结果或理论分析反驳了B的结论
- **方向**：A → B（A反驳B）
- **学术意义**：学术争论和纠错

#### 12. supports（支持）
- **定义**：A的实验结果支持/验证了B的结论
- **方向**：A → B（A支持B）
- **学术意义**：增强B结论的可信度

### 三、概念关系（Conceptual Relations）

基于方法论和概念层面的关系。

#### 13. is_variant_of（变体）
- **定义**：A是B方法的变体，核心思想相同但有局部修改
- **方向**：A → B（A是B的变体）
- **示例**：RoBERTa是BERT的变体，ALBERT是BERT的变体

#### 14. is_instance_of（实例）
- **定义**：A是B所述方法类别的具体实例
- **方向**：A → B（A是B的实例）
- **示例**：GPT是自回归语言模型的实例

#### 15. shares_methodology（共享方法论）
- **定义**：A和B使用相似的核心方法
- **方向**：无向
- **判定标准**：method_entities交集≥30%
- **示例**：都使用Transformer架构

#### 16. shares_task（共享任务）
- **定义**：A和B解决相同的任务或问题
- **方向**：无向
- **示例**：都做机器翻译任务

#### 17. shares_dataset（共享数据集）
- **定义**：A和B使用相同的数据集
- **方向**：无向
- **示例**：都在ImageNet上评估

#### 18. shares_baseline（共享基线）
- **定义**：A和B使用相同的基线方法进行对比
- **方向**：无向

#### 19. shares_architecture（共享架构）
- **定义**：A和B使用相似的模型架构
- **方向**：无向
- **需要LLM**：判断架构相似性

### 四、时序关系（Temporal Relations）

基于时间演进的关系。

#### 20. precedes（前序）
- **定义**：A是B的前序工作，B引用了A
- **方向**：A → B（A先于B）
- **判定标准**：year_A < year_B 且 A ∈ B.references

#### 21. succeeds（后续）
- **定义**：A是B的后续工作，A引用了B
- **方向**：A → B（A后于B）
- **判定标准**：year_A > year_B 且 B ∈ A.references

#### 22. concurrent（同期）
- **定义**：A和B是同期独立发表的相关工作
- **方向**：无向
- **判定标准**：|year_A - year_B| ≤ 1 且 共同引用≥5篇

### 五、作者关系（Authorship Relations）

基于作者信息的关系。

#### 23. same_author（共同作者）
- **定义**：A和B有共同作者
- **方向**：无向
- **学术意义**：可能是同一研究线的延续

#### 24. same_group（同一研究组）
- **定义**：A和B来自同一研究组/实验室
- **方向**：无向

## 多关系共存

两篇论文之间可以同时存在多种不同类型的关系。例如：

```
论文A: "RoBERTa: A Robustly Optimized BERT Pretraining Approach" (2019)
论文B: "BERT: Pre-training of Deep Bidirectional Transformers" (2018)

关系：
1. A cites B (结构关系)
2. A improves B (语义关系)
3. A is_variant_of B (概念关系)
4. A succeeds B (时序关系)
5. A same_author B (作者关系，如果有共同作者)
```

## 置信度计算

| 关系类型 | 置信度来源 |
|---------|-----------|
| 规则发现 | 基于规则的确定性或统计计算 |
| LLM发现 | LLM输出的置信度（0.6-1.0） |

## 使用示例

```python
from src.modules.mekg.enhanced_relation_discoverer import EnhancedRelationDiscoverer
from src.models.LLM.ChatAgent import ChatAgent

# 初始化
chat_agent = ChatAgent()
discoverer = EnhancedRelationDiscoverer(
    db=db,
    chat_agent=chat_agent,
    use_llm=True,
    use_rules=True,
    max_workers=50  # 50线程并发
)

# 批量发现关系
result = discoverer.batch_discover_concurrent(
    paper_ids=paper_ids,
    max_pairs=1000,
    min_confidence=0.5,
    save_to_db=True
)

print(f"发现关系: {len(result.relations)}")
print(f"  结构关系: {result.structural_count}")
print(f"  语义关系: {result.semantic_count}")
print(f"  概念关系: {result.conceptual_count}")
print(f"  时序关系: {result.temporal_count}")
print(f"  作者关系: {result.authorship_count}")
```

## 学术严谨性保证

1. **可追溯性**：每条关系都记录发现方式（rule/llm）和证据
2. **可验证性**：规则发现的关系可通过数据直接验证
3. **置信度**：LLM发现的关系有置信度阈值（≥0.6）
4. **去重机制**：同一关系类型只保留置信度最高的一条
5. **方向一致性**：有向关系严格遵循定义的方向语义