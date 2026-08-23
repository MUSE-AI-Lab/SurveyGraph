# MEKG Survey Evaluation System - 设计文档

## 📋 概述

本评测系统是针对 **SurveyGraph** 项目的综述质量评估模块，结合 **MEKG (Methods-Entity Knowledge Graph)** 知识图谱的特点，设计了一套全面的评测方法。

### 设计目标

1. **基于MEKG图谱的评测**：充分利用MEKG知识图谱的结构化信息进行评估
2. **多维度评测**：覆盖引用质量、内容质量、事实准确性、结构一致性、伦理完整性、富媒体质量等多个维度
3. **可扩展性**：模块化设计，便于添加新的评测指标
4. **易用性**：提供简洁的命令行接口和Python API

---

## 🏗️ 系统架构

```
evaluation/
├── __init__.py                    # 模块初始化
├── config.py                      # 配置文件
├── main.py                        # 主入口
├── DESIGN.md                      # 设计文档
│
├── core/                          # 核心模块
│   ├── __init__.py
│   ├── base_evaluator.py          # 评测器基类
│   └── result.py                  # 评测结果数据结构
│
├── evaluators/                    # 评测器实现
│   ├── __init__.py
│   ├── reference_evaluator.py     # 引用质量评测
│   ├── content_evaluator.py       # 内容质量评测
│   ├── factual_evaluator.py       # 事实准确性评测
│   ├── structure_evaluator.py     # 结构一致性评测
│   ├── mekg_evaluator.py          # MEKG图谱评测
│   ├── ethics_evaluator.py        # 伦理与完整性评测
│   └── media_evaluator.py         # 富媒体质量评测
│
├── utils/                         # 工具函数
│   ├── __init__.py
│   ├── latex_parser.py            # LaTeX解析
│   ├── llm_client.py              # LLM调用
│   └── metrics.py                 # 指标计算
│
└── report/                        # 报告生成
    ├── __init__.py
    └── generator.py               # 报告生成器
```

---

## 📊 评测维度

### 维度1: 引用质量 (Reference Quality) - 权重 25%

| 指标 | 说明 | 数据来源 |
|------|------|----------|
| **WCR** (Weighted Centrality Recall) | 加权中心性召回率，衡量核心论文覆盖 | MEKG PageRank |
| **CC** (Community Coverage) | 社区覆盖率，衡量研究方向覆盖 | MEKG 社区发现 |
| **Bibliographic Integrity** | 文献完整性，检测虚构引用 | 外部API验证 |
| **Citation Faithfulness** | 引用忠实度，声明是否被引用支持 | LLM验证 |

### 维度2: 结构完整性 (Structural Soundness) - 权重 20%

| 指标 | 说明 | 评测方法 |
|------|------|----------|
| **SC** (Structural Coherence) | 结构一致性，大纲与MEKG社区对应 | MEKG分析 |
| **Structural Completeness** | 结构完整性，是否包含必要章节 | 规则+LLM |
| **Content-Structure Fidelity** | 内容与标题的一致性 | LLM评估 |

### 维度3: 内容完整性 (Content Integrity) - 权重 25%

| 指标 | 说明 | 评测方法 |
|------|------|----------|
| **General Factualness** | 通用事实性，无引用声明验证 | Web搜索+LLM |
| **Writing Quality** | 写作质量（清晰度、连贯性） | LLM评估 |
| **Scholarly Depth** | 学术深度，综合分析能力 | LLM评估 |
| **TC** (Temporal Coverage) | 时间覆盖率 | 年份分析 |

### 维度4: 伦理与完整性 (Ethics & Integrity) - 权重 15%

| 指标 | 说明 | 评测方法 |
|------|------|----------|
| **Originality** | 原创性，检测抄袭/过度引用 | 文本分析 |
| **Societal Impact** | 社会影响，潜在危害讨论 | LLM评估 |
| **Fairness & Bias** | 公平性与偏见检测 | LLM评估 |

### 维度5: 富媒体质量 (Rich Media Quality) - 权重 15%

| 指标 | 说明 | 评测方法 |
|------|------|----------|
| **Figure Quality** | 图片质量与相关性 | LLM评估 |
| **Table Quality** | 表格质量与信息量 | LLM评估 |
| **Visual-Content Alignment** | 视觉-内容对齐度 | LLM评估 |
| **Resource Accessibility** | 资源可访问性（链接有效性） | HTTP检查 |

---

## 🔧 核心组件设计

### 1. EvaluationResult (评测结果)

```python
@dataclass
class EvaluationResult:
    """评测结果数据结构"""
    # 各维度分数 (0.0-1.0)
    reference_quality: float
    structural_soundness: float
    content_integrity: float
    ethics_integrity: float
    rich_media_quality: float
    
    # 综合得分 (0-100)
    overall_score: float
    
    # 详细指标
    metrics: Dict[str, float]
    
    # 详细信息
    details: Dict[str, Any]
    
    # 建议
    recommendations: List[str]
```

### 2. BaseEvaluator (评测器基类)

```python
class BaseEvaluator(ABC):
    """评测器基类"""
    
    @abstractmethod
    def evaluate(self, **kwargs) -> Dict[str, Any]:
        """执行评测"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """评测器名称"""
        pass
    
    @property
    @abstractmethod
    def weight(self) -> float:
        """评测器权重"""
        pass
```

### 3. MEKGSurveyEvaluator (主评测器)

```python
class MEKGSurveyEvaluator:
    """MEKG综述评测主类"""
    
    def __init__(
        self,
        mekg_data: Dict,
        survey_path: Path,
        config: EvaluationConfig
    ):
        self.mekg_data = mekg_data
        self.survey_path = survey_path
        self.config = config
        
        # 初始化子评测器
        self.evaluators = [
            ReferenceEvaluator(mekg_data),
            StructureEvaluator(mekg_data),
            ContentEvaluator(),
            EthicsEvaluator(),
            MediaEvaluator()
        ]
    
    def evaluate_all(self) -> EvaluationResult:
        """执行完整评测"""
        pass
```

---

## 📈 评测指标详解

### WCR (Weighted Centrality Recall)

**定义**: 衡量综述是否覆盖了MEKG中的核心论文

**计算公式**:
```
WCR = Σ(pagerank(p) for p in cited ∩ core) / Σ(pagerank(p) for p in core)
```

**核心论文定义**: PageRank Top 20% 的论文

### CC (Community Coverage)

**定义**: 衡量综述是否覆盖了所有研究社区

**计算公式**:
```
CC = |covered_communities| / |total_communities|
```

### SC (Structural Coherence)

**定义**: 衡量综述结构与MEKG社区结构的一致性

**计算方法**:
1. 提取综述大纲章节
2. 匹配章节与MEKG社区
3. 计算匹配覆盖率

### Citation Faithfulness (引用忠实度)

**定义**: 衡量综述中的声明是否被引用论文支持

**计算方法**:
1. 提取带引用的句子
2. 分解为原子事实
3. 验证每个原子事实是否被原文支持
4. 计算支持率

### Visual-Content Alignment (视觉-内容对齐)

**定义**: 衡量图表是否与综述内容相关

**计算方法**:
1. 提取图表及其标题
2. 提取相关章节内容
3. 使用LLM评估相关性

---

## 🚀 使用方式

### 命令行接口

```bash
# 完整评测
python -m evaluation.main \
    --mekg-data outputs/xxx/mekg/mekg_data.json \
    --survey-path outputs/xxx/latex/survey.tex \
    --outline-path outputs/xxx/outline.json \
    --output-dir outputs/xxx/evaluation

# 仅评测引用质量
python -m evaluation.main \
    --mekg-data outputs/xxx/mekg/mekg_data.json \
    --survey-path outputs/xxx/latex/survey.tex \
    --evaluators reference

# 快速评测（不使用LLM）
python -m evaluation.main \
    --mekg-data outputs/xxx/mekg/mekg_data.json \
    --survey-path outputs/xxx/latex/survey.tex \
    --no-llm
```

### Python API

```python
from evaluation import MEKGSurveyEvaluator, EvaluationConfig

# 创建配置
config = EvaluationConfig(
    use_llm=True,
    llm_model="gpt-4o-mini",
    weights={
        "reference_quality": 0.25,
        "structural_soundness": 0.20,
        "content_integrity": 0.25,
        "ethics_integrity": 0.15,
        "rich_media_quality": 0.15
    }
)

# 创建评测器
evaluator = MEKGSurveyEvaluator(
    mekg_data=mekg_data,
    survey_path=Path("outputs/xxx/latex/survey.tex"),
    config=config
)

# 执行评测
result = evaluator.evaluate_all()

# 生成报告
evaluator.generate_report(result, Path("evaluation_report.md"))
```

---

## 📝 输出格式

### JSON 结果

```json
{
    "overall_score": 78.5,
    "dimension_scores": {
        "reference_quality": 82.3,
        "structural_soundness": 80.0,
        "content_integrity": 75.0,
        "ethics_integrity": 78.0,
        "rich_media_quality": 76.5
    },
    "metrics": {
        "wcr": 0.85,
        "cc": 0.90,
        "sc": 0.80,
        "bibliographic_integrity": 0.95,
        "citation_faithfulness": 0.78,
        "general_factualness": 0.82,
        "writing_quality": 0.75,
        "scholarly_depth": 0.70,
        "tc": 0.85,
        "originality": 0.90,
        "societal_impact": 0.65,
        "fairness": 0.80,
        "figure_quality": 0.75,
        "table_quality": 0.80,
        "visual_content_alignment": 0.70,
        "resource_accessibility": 0.85
    },
    "details": {...},
    "recommendations": [...]
}
```

### Markdown 报告

```markdown
# Survey Evaluation Report

## Overview
| Dimension | Score | Weight |
|-----------|-------|--------|
| Reference Quality | 82.3 | 25% |
| Structural Soundness | 80.0 | 20% |
| Content Integrity | 75.0 | 25% |
| Ethics & Integrity | 78.0 | 15% |
| Rich Media Quality | 76.5 | 15% |
| **Overall** | **78.5** | 100% |

## Detailed Analysis
...

## Recommendations
...
```

---

## 🔄 与现有系统的关系

### 与 NewSurveyEvaluator 的区别

| 维度 | NewSurveyEvaluator | MEKG Evaluation |
|------|-------------------|-----------------|
| 数据来源 | 金标准JSON | MEKG知识图谱 |
| 核心论文识别 | 人工标注 | PageRank自动计算 |
| 社区覆盖 | 预定义分类 | 社区发现算法 |
| 关系验证 | 无 | MEKG关系图谱 |
| 伦理评测 | 无 | 有 |
| 富媒体评测 | 有限 | 全面 |
| 适用场景 | 有金标准的评测 | 无金标准的自动评测 |

### 与 mekg/src/survey/evaluator.py 的关系

本系统是对 `mekg/src/survey/evaluator.py` 的**扩展和增强**：

1. **保留原有指标**: WCR, CC, SC, RA, TC
2. **新增评测维度**: 伦理完整性、富媒体质量
3. **增强报告生成**: 更详细的分析和建议
4. **模块化设计**: 便于扩展和维护

---

## 📚 参考资料

1. NewSurveyEvaluator 评测系统
2. MEKG 知识图谱技术文档
3. Survey Benchmark 评测标准