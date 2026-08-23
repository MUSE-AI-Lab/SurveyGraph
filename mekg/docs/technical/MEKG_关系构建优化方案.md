# MEKG 关系构建优化方案

## 🔴 当前问题

### 资源浪费严重
**现状**：每篇论文与其他所有论文配对（取top-20）
- 50篇论文：50 × 20 = 1,000个候选对 → 1,000次LLM调用
- 500篇论文：500 × 20 = 10,000个候选对 → 10,000次LLM调用
- 1500篇论文：1500 × 20 = 30,000个候选对 → **30,000次LLM调用！**

**成本估算**：
- 每次LLM调用 ≈ $0.001
- 1500篇论文 ≈ $30
- 且大部分调用都是无效的（没有关系）

### 效率低下
- 大量无关论文对被检查
- LLM需要处理大量"无关系"的判断
- 图谱稀疏但调用密集

## 🎯 优化目标

1. **减少LLM调用次数**：从O(N²)降到O(N)或O(N·log N)
2. **提高命中率**：只检查真正可能有关系的论文对
3. **保持图谱质量**：连通性、代表性不降低
4. **构建层级结构**：核心论文→衍生论文→应用论文

## 💡 优化方案

### 方案1: 两阶段过滤（推荐）⭐

**思路**：快速过滤 + 精确验证

```
阶段1: 快速过滤（不调用LLM）
  ↓ 基于规则筛选高可能性对（保留10-20%）
阶段2: LLM精确验证
  ↓ 只对筛选后的对调用LLM
结果: 显著减少LLM调用
```

**实现**：

#### 1.1 识别核心论文
```python
def identify_core_papers(papers, top_k=50):
    """识别核心论文（高影响力）"""
    # 评分标准：
    # - 高引用数（40%）
    # - 早期发表（30%）- 经典方法多是早期的
    # - 被其他论文引用（20%）- 如果有引用网络数据
    # - 方法创新性（10%）- 如果有属性数据
    
    scores = []
    for paper in papers:
        score = 0
        # 引用数归一化
        citations = paper.get('citations', 0)
        score += (citations / max(p.get('citations', 1) for p in papers)) * 40
        
        # 年份评分（越早越高）
        year = paper.get('year', 2024)
        year_score = (2024 - year) / 10  # 10年前的论文满分
        score += min(year_score, 1.0) * 30
        
        scores.append((score, paper))
    
    # 返回top-k核心论文
    scores.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in scores[:top_k]]
```

#### 1.2 构建候选对（分层策略）
```python
def build_candidate_pairs_v2(papers):
    """优化的候选对生成"""
    # 识别核心论文（10%）
    core_papers = identify_core_papers(papers, top_k=len(papers)//10)
    regular_papers = [p for p in papers if p not in core_papers]
    
    pairs = []
    
    # 策略1: 核心论文之间（完全图）
    for i, paper_a in enumerate(core_papers):
        for paper_b in core_papers[i+1:]:
            pairs.append((paper_a, paper_b))
    
    # 策略2: 普通论文 → 核心论文（单向）
    for paper in regular_papers:
        # 只和最相关的3-5个核心论文配对
        candidates = find_most_similar_cores(paper, core_papers, top_k=5)
        for core in candidates:
            pairs.append((paper, core))
    
    # 策略3: 同领域普通论文之间（可选）
    # 基于聚类或领域分组，只在组内配对
    
    return pairs
```

**效果**：
- 1500篇论文：
  - 核心论文150个：150×149/2 = 11,175对
  - 普通论文1350个：1350×5 = 6,750对
  - **总计：≈18,000对（相比30,000减少40%）**
  - 如果加强过滤：可降到10,000对以内

### 方案2: 基于聚类的分区构建

**思路**：先聚类，只在簇内和簇间代表节点建立关系

```
1. 论文聚类（基于embedding/属性）
   ↓
2. 簇内：完全图或星型图
   ↓
3. 簇间：只连接代表论文
   ↓
4. LLM验证筛选后的对
```

**优势**：
- 减少跨领域无效配对
- 保持图的模块化结构
- 自然形成主题聚合

### 方案3: 基于引用网络的智能扩展

**思路**：利用引用关系指导候选对生成

```python
def build_pairs_with_citations(papers):
    """基于引用网络的候选对"""
    pairs = []
    
    for paper_a in papers:
        # 1. 直接引用关系（如果OpenAlex提供）
        cited_ids = paper_a.get('references', [])
        for paper_b in papers:
            if paper_b['paper_id'] in cited_ids:
                pairs.append((paper_a, paper_b))
        
        # 2. 共引分析
        # 如果A和B引用了相同的经典论文，可能有关系
        
        # 3. 耦合分析
        # 如果A和B被相同的论文引用，可能有关系
    
    return pairs
```

### 方案4: 混合策略（最佳实践）⭐⭐⭐

**组合多种方法**：

```python
def build_smart_candidate_pairs(papers):
    """智能候选对生成（混合策略）"""
    all_pairs = set()  # 使用set去重
    
    # 层1: 核心论文完全图（必须）
    core_papers = identify_core_papers(papers, top_k=min(50, len(papers)//10))
    for i, pa in enumerate(core_papers):
        for pb in core_papers[i+1:]:
            all_pairs.add((pa['paper_id'], pb['paper_id']))
    
    # 层2: 引用关系（如果有数据）
    citation_pairs = extract_citation_pairs(papers)
    all_pairs.update(citation_pairs)
    
    # 层3: 时间邻近 + 高引用
    # 新论文只和近3年的高引论文配对
    for paper in papers:
        if paper.get('year', 0) >= 2022:
            recent_influential = [
                p for p in papers 
                if p.get('year', 0) >= 2019 
                and p.get('citations', 0) > 100
            ]
            for target in recent_influential[:10]:
                all_pairs.add((paper['paper_id'], target['paper_id']))
    
    # 层4: 领域内配对（基于属性或聚类）
    domain_pairs = build_domain_based_pairs(papers)
    all_pairs.update(domain_pairs)
    
    # 转换回论文对象
    id_to_paper = {p['paper_id']: p for p in papers}
    return [(id_to_paper[a], id_to_paper[b]) for a, b in all_pairs]
```

**预期效果**（1500篇论文）：
- 核心论文50个：50×49/2 = 1,225对
- 引用关系：≈2,000对
- 时间邻近：≈3,000对  
- 领域内：≈4,000对
- 去重后：**≈6,000-8,000对（减少70-80%）**

## 📊 效果对比

| 方案 | 候选对数（1500篇） | LLM调用 | 成本估算 | 预期命中率 |
|------|-------------------|---------|----------|-----------|
| 当前方案 | 30,000 | 30,000 | $30 | 5-10% |
| 方案1（两阶段） | 18,000 | 18,000 | $18 | 10-15% |
| 方案4（混合）⭐ | 8,000 | 8,000 | $8 | 20-30% |

**关键指标改善**：
- 成本：↓73%
- 命中率：↑2-3倍
- 图谱质量：保持或提升（更聚焦核心关系）

## 🚀 实施建议

### 短期（立即实施）
1. 实现核心论文识别
2. 采用分层配对策略
3. 限制每篇论文的最大候选数（从20降到5-10）

### 中期（优化迭代）
1. 加入引用网络分析
2. 实现领域聚类
3. 动态调整配对策略

### 长期（智能化）
1. 使用轻量级embedding预筛选
2. 训练关系预测模型
3. 自适应候选对生成

## 💻 代码示例

```python
class SmartRelationBuilder:
    """智能关系构建器"""
    
    def build_mekg_efficiently(self, papers):
        """高效构建MEKG"""
        # 1. 识别核心论文
        core_papers = self.identify_core_papers(papers)
        
        # 2. 构建分层候选对
        candidate_pairs = []
        
        # 核心层：核心论文之间
        core_pairs = self.build_core_layer(core_papers)
        candidate_pairs.extend(core_pairs)
        
        # 连接层：普通论文→核心论文
        connection_pairs = self.build_connection_layer(
            papers, core_papers
        )
        candidate_pairs.extend(connection_pairs)
        
        # 3. LLM验证（只验证候选对）
        edges = await self.verify_pairs_with_llm(candidate_pairs)
        
        return edges
    
    def identify_core_papers(self, papers, ratio=0.1):
        """识别核心论文（top 10%）"""
        scored_papers = []
        for paper in papers:
            score = self.calculate_influence_score(paper)
            scored_papers.append((score, paper))
        
        scored_papers.sort(reverse=True)
        k = max(int(len(papers) * ratio), 10)
        return [p for _, p in scored_papers[:k]]
    
    def calculate_influence_score(self, paper):
        """计算论文影响力分数"""
        citations = paper.get('citations', 0)
        year = paper.get('year', 2024)
        
        # 归一化引用数（log scale）
        citation_score = np.log1p(citations)
        
        # 年份分数（越早越高）
        age = 2024 - year
        time_score = min(age / 10.0, 1.0)
        
        # 综合得分
        return 0.6 * citation_score + 0.4 * time_score
```

## 🎯 总结

**核心思想**：
- 不是所有论文对都需要检查
- 聚焦高价值、高可能性的对
- 构建有层次的图谱而非密集图

**关键优化**：
1. 识别核心节点（10%）
2. 分层配对策略
3. 智能过滤机制
4. 保持图的连通性和代表性

**预期收益**：
- 成本降低70-80%
- 命中率提升2-3倍
- 图谱质量不降反升