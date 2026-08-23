# 综述生成深度优化方案

## 背景

基于Claude、Gemini、GPT三个AI模型对生成综述的评价反馈，我们识别出以下主要问题：

| 问题类型 | Claude评价 | Gemini评价 | GPT评价 |
|---------|-----------|-----------|---------|
| 技术深度 | 3/5 - 不够深入 | 需要更多机制解释 | 缺乏数学形式化 |
| 定量比较 | 缺少统一评估框架 | 需要性能对比表 | 缺少定量比较 |
| 批判性分析 | 3/5 - 缺乏深入批判 | 需要更多权衡分析 | 论断偏"宣言式" |
| 概念边界 | 部分内容重叠 | 需要更清晰的定义 | 概念混用风险 |
| 失败案例 | 未系统总结 | 需要故障树分析 | 缺少负面结果 |

## 已实施的优化

### 1. 内容生成Prompt增强 ✅

**文件**: 
- `mekg/src/survey/content_generator.py` - CONTENT_GENERATION_PROMPT
- `resources/LLM/prompts/content_generator/fulfill_content_iteratively.md`
- `resources/LLM/prompts/content_generator/fulfill_content.md`

**新增内容**:
```markdown
### 3. 定量证据 (Quantitative Evidence)
- 错误示例: "方法A显著优于方法B。"
- 正确示例: "方法A在BFCL v3上达到85.3%的准确率，比方法B（82.1%）高出3.2个百分点"

### 6. 失败模式分析 (Failure Mode Analysis)
- 识别常见失败模式
- 讨论边缘情况
- 建议缓解措施

### 7. 权衡分析 (Trade-off Analysis)
- 明确讨论方法间的权衡
- 指出各方法的最佳适用场景

### 8. 对比表格 (Comparison Tables)
- 当讨论3个或更多方法时生成对比表格
```

### 2. 属性提取Prompt增强 ✅

**文件**: `resources/LLM/prompts/preprocessor/attri_tree_for_method.md`

**新增提取字段**:
```json
{
  "experiments": {
    "quantitative results": {
      "main metrics": [...],
      "baseline comparisons": [...],
      "statistical significance": "..."
    },
    "ablation studies": "..."
  },
  "failure analysis": {
    "failure modes": [...],
    "error examples": "...",
    "failure rate": "..."
  },
  "comparative analysis": {
    "compared methods": [...],
    "trade-offs": "...",
    "best use cases": "...",
    "unsuitable scenarios": "..."
  },
  "resource requirements": {
    "computational cost": "...",
    "data requirements": "...",
    "model size": "..."
  }
}
```

### 3. 大纲生成Prompt增强 ✅

**文件**: `mekg/src/survey/outline_generator.py` - OUTLINE_GENERATION_PROMPT

**新增内容**:
```markdown
## CRITICAL: Concept Boundary Definition

A high-quality survey must have clear concept boundaries:
1. Define precisely what IS included
2. Define precisely what IS NOT included
3. Distinguish from related/adjacent concepts

### Example:
"Function Calling" in this survey refers to:
- INCLUDED: Structured schema-based tool invocation
- EXCLUDED: Free-form code generation
- DISTINCTION from "Tool Use": Function calling is a subset
```

### 4. 批判性分析后处理模块 ✅

**文件**: `src/modules/post_refine/critical_analysis_refiner.py`

**功能**:
1. **问题检测**: 自动识别缺乏定量证据、批判性分析薄弱、无失败模式分析、无权衡分析的段落
2. **内容增强**: 使用LLM自动增强问题段落
3. **对比表格生成**: 自动生成方法对比表格
4. **质量报告**: 生成详细的质量分析报告

**检测的问题类型**:
- `missing_quantitative`: 缺少定量数据的段落
- `weak_critical`: 批判性分析不足的段落
- `no_failure_analysis`: 缺少失败模式分析的段落
- `no_tradeoff`: 缺少权衡分析的段落

**使用方法**:
```python
from src.modules.post_refine.critical_analysis_refiner import CriticalAnalysisRefiner

refiner = CriticalAnalysisRefiner(chat_agent=chat_agent, auto_enhance=True)
analysis_result = refiner.analyze(mainbody_content)
report = refiner.generate_report(analysis_result)
enhanced_content, count = refiner.enhance(mainbody_content, analysis_result)
```

### 5. Pipeline集成 ✅

**文件**: `mekg/src/survey/pipeline.py`

**新增步骤**: Step 7.5 - 批判性分析增强

批判性分析模块已完全集成到主流程中，作为 Step 7.5 在质量评估之后、LaTeX生成之前执行。

**配置选项**:
```python
@dataclass
class PipelineConfig:
    # ... 其他配置 ...
    
    # 批判性分析配置 (深度优化功能 - 默认开启)
    enable_critical_analysis: bool = True  # 启用批判性分析增强
    critical_analysis_auto_enhance: bool = True  # 自动增强问题段落
```

**执行流程**:
```
Step 1: MEKG数据构建
Step 2: 大纲生成
Step 3: Survey主体内容生成
Step 4: PostRefiner文本优化
Step 5: 表格生成
Step 6: 动态视觉元素生成
Step 7: 质量评估与全局反思
Step 7.5: 批判性分析增强 ← 新增
Step 8: LaTeX生成
Step 9: 可视化数据导出
```

**输出文件**:
- `tmp/mainbody_critical_enhanced.tex`: 增强后的主体内容
- `critical_analysis_report.md`: 详细的分析报告

**默认行为**: 所有优化功能**默认开启**，无需额外配置。

## 优化效果预期

| 维度 | 优化前 | 优化后预期 |
|-----|-------|----------|
| 技术深度 | 3/5 | 4/5 |
| 定量比较 | 缺失 | 包含具体数字 |
| 批判性分析 | 3/5 | 4/5 |
| 概念边界 | 模糊 | 清晰定义 |
| 失败案例 | 无 | 系统总结 |

## 后续优化建议

### P1 优先级（建议实施）

1. **增强PaperInfo数据结构**
   - 在`mekg/src/survey/content_generator.py`的`PaperInfo`类中添加新字段
   - 支持存储定量结果、失败模式等信息

2. ~~**集成批判性分析模块到主流程**~~ ✅ 已完成
   - ~~在`mekg_run.py`中添加后处理步骤~~
   - ~~自动运行质量检查和增强~~
   - **实现**: 已集成到 `pipeline.py` 的 Step 7.5

3. **添加引用验证模块**
   - 验证所有引用的论文确实存在
   - 检查引用格式的一致性

### P2 优先级（可选实施）

1. **多模态工具调用讨论**
   - 添加GUI Agent相关内容
   - 讨论Vision-Language-Action模型

2. **标准化协议讨论**
   - 深入讨论MCP协议
   - 分析不同模型的Schema差异

3. **经济模型分析**
   - 添加成本分析章节
   - 讨论Token消耗和API成本

## 文件变更清单

| 文件路径 | 变更类型 | 说明 |
|---------|---------|-----|
| `mekg/src/survey/content_generator.py` | 修改 | 增强CONTENT_GENERATION_PROMPT |
| `mekg/src/survey/outline_generator.py` | 修改 | 添加概念边界定义要求 |
| `mekg/src/survey/pipeline.py` | 修改 | 集成批判性分析模块，添加Step 7.5 |
| `resources/LLM/prompts/preprocessor/attri_tree_for_method.md` | 修改 | 添加定量数据和失败模式提取 |
| `resources/LLM/prompts/content_generator/fulfill_content_iteratively.md` | 修改 | 增强写作原则 |
| `resources/LLM/prompts/content_generator/fulfill_content.md` | 修改 | 增强写作原则 |
| `src/modules/post_refine/critical_analysis_refiner.py` | 新增 | 批判性分析后处理模块 |

## 测试建议

1. **单元测试**: 测试`CriticalAnalysisRefiner`的各个检测方法
2. **集成测试**: 使用现有论文数据运行完整流程
3. **质量评估**: 使用AI模型重新评估生成的综述

## 参考资料

- Claude评价报告: 总体评分 B/B+
- Gemini评价报告: 评分 8.5/10，Strong Accept倾向
- GPT评价报告: 结构完整但需加强证据支撑