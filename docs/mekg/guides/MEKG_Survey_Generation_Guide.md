# MEKG 高级综述生成指南：打造 SOTA 级学术综述

> **目标**: 超越简单的自动化生成，利用 MEKG 图谱和 Agentic Workflow 生成具有深度、严谨性和创新性的 SOTA (State-of-the-Art) 综述。

---

## 🌟 核心理念：Agentic Workflow + Graph Reasoning

传统的自动化综述往往流于表面，缺乏深度。SurveyGraph 通过以下机制解决这一问题：

1.  **Critic-Refine Loop (批判-优化循环)**: 模拟人类专家的"撰写-审稿-修改"过程。
2.  **Evidence-Based Writing (基于证据的写作)**: 利用图谱中的实体和关系构建严谨的论证逻辑。
3.  **Dynamic Graph Querying (动态图谱查询)**: 在写作过程中动态查询图谱，补充缺失的细节。

---

## 🚀 流程详解

### Phase 1: 深度大纲构建 (The Architect)

不仅仅是列出标题，而是构建逻辑严密的知识框架。

**Agent 角色**:
- **Architect**: 负责构建大纲架构。
- **Reviewer**: 负责批判大纲的逻辑漏洞和覆盖盲点。

**Prompt 策略**:
- **Gap Analysis**: "分析图谱中的稀疏区域，识别当前研究的空白和未来方向。"
- **Evolutionary Path**: "基于图谱中的 `precedes`/`succeeds` 关系，构建技术演进的时间线。"

**执行步骤**:
1. Architect 基于图谱社区生成初版大纲。
2. Reviewer 检查大纲是否覆盖了所有核心论文 (PageRank Top-K)。
3. Reviewer 检查章节间的逻辑连贯性。
4. Architect 根据反馈修正大纲。

### Phase 2: 原子事实提取与推理 (The Researcher)

在写作之前，先准备好"弹药"。

**核心机制**:
- **Triple-to-Text**: 将图谱中的三元组 `(Paper A, improves, Paper B)` 转化为自然语言描述。
- **Entity Injection**: 提取论文中的关键实体（Method, Metric, Dataset），确保写作时术语准确。

**Prompt 示例**:
> "基于关系 `Paper A improves Paper B on Dataset D`，请详细描述 A 是如何改进 B 的，重点关注 Method 实体中的差异。"

### Phase 3: 深度内容撰写 (The Writer)

拒绝泛泛而谈，要求基于证据的深度分析。

**特色功能**:
1.  **自动对比分析**:
    - 利用 `compares` 和 `outperforms` 关系。
    - 自动生成 "Comparison of Methods" 表格。
    
2.  **技术演进叙事**:
    - 利用时间线和继承关系。
    - 叙述 "从 A 到 B 的演进逻辑"（解决了什么问题？引入了什么新机制？）。

3.  **引用完整性检查**:
    - 确保所有核心结论都有引用支持。
    - 检查引用格式是否符合 LaTeX 标准。

### Phase 4: 评估与自我修正 (The Editor)

**闭环机制**:
1. 计算 **WCR (Weighted Centrality Recall)**。
2. 如果某章节 WCR < 0.8（漏掉了核心论文）：
   - **Action**: 触发 `GraphRetriever`，专门检索该子领域的缺失核心论文。
   - **Action**: 触发 `Writer` 重写该章节，强制包含缺失论文。

---

## 🛠️ 高级配置参数

在 `run_mekg_survey.py` 中启用高级模式：

```python
config = PipelineConfig(
    # ...
    enable_critic_loop=True,      # 启用批判循环
    critic_rounds=2,              # 批判轮数
    enable_evidence_check=True,   # 启用证据检查
    min_wcr_threshold=0.8,        # 最低核心论文覆盖率
    auto_refine=True              # 自动重写低分章节
)
```

## 📊 提示词工程 (Prompt Engineering) 最佳实践

### 1. 角色扮演 (Role Playing)
> "你是一位在 [Topic] 领域有20年经验的资深研究员，以严谨、客观、深入的风格撰写综述..."

### 2. 思维链 (Chain of Thought)
> "在撰写本节之前，请先：
> 1. 列出本节涉及的所有核心论文。
> 2. 分析这些论文之间的演进关系。
> 3. 归纳出3个关键的技术挑战。
> 4. 基于以上分析撰写正文。"

### 3. 约束控制 (Constraints)
> "禁止使用模糊的形容词（如'good performance'），必须引用具体的 Metric 实体和数值（如'achieved 85% accuracy on ImageNet'）。"

---

通过实施这些高级策略，SurveyGraph 将生成的不仅仅是一份"合格"的综述，而是一份具有**深度洞察力**和**学术价值**的 SOTA 综述。