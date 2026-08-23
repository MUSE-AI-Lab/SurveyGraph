# MEKG Survey Evaluation System

基于MEKG知识图谱的综述质量评估系统。

## 📋 概述

本系统是针对 **SurveyGraph** 项目的综述质量评估模块，结合 **MEKG (Methods-Entity Knowledge Graph)** 知识图谱的特点，设计了一套全面的评测方法。

### 评测维度

| 维度 | 权重 | 说明 |
|------|------|------|
| 📚 Reference Quality | 25% | 引用质量（WCR、CC、文献完整性、引用忠实度） |
| 📋 Structural Soundness | 20% | 结构完整性（SC、结构完整性、内容-结构一致性） |
| ✍️ Content Integrity | 25% | 内容完整性（事实性、写作质量、学术深度、时间覆盖） |
| ⚖️ Ethics & Integrity | 15% | 伦理与完整性（原创性、社会影响、公平性） |
| 📊 Rich Media Quality | 15% | 富媒体质量（图表质量、视觉-内容对齐、资源可访问性） |

## 🚀 快速开始

### 安装依赖

```bash
pip install openai requests
```

### 命令行使用

```bash
# 完整评测
python -m evaluation.main \
    --mekg-data outputs/xxx/mekg/mekg_data.json \
    --survey-path outputs/xxx/latex/survey.tex \
    --output-dir outputs/xxx/evaluation

# 快速评测（不使用LLM）
python -m evaluation.main \
    --mekg-data outputs/xxx/mekg/mekg_data.json \
    --survey-path outputs/xxx/latex/survey.tex \
    --no-llm

# 使用完整评测配置
python -m evaluation.main \
    --mekg-data outputs/xxx/mekg/mekg_data.json \
    --survey-path outputs/xxx/latex/survey.tex \
    --full \
    --api-key YOUR_API_KEY
```

### Python API

```python
from evaluation import MEKGSurveyEvaluator, EvaluationConfig
from pathlib import Path
import json

# 加载MEKG数据
with open("outputs/xxx/mekg/mekg_data.json", "r") as f:
    mekg_data = json.load(f)

# 创建配置
config = EvaluationConfig(
    use_llm=True,
    llm_model="gpt-4o-mini",
    api_key="YOUR_API_KEY"
)

# 创建评测器
evaluator = MEKGSurveyEvaluator(
    mekg_data=mekg_data,
    survey_path=Path("outputs/xxx/latex/survey.tex"),
    config=config
)

# 执行评测
result = evaluator.evaluate_all()

# 打印结果
print(result)

# 生成报告
evaluator.generate_report(result, Path("evaluation_report.md"))

# 保存JSON结果
result.save("evaluation_results.json")
```

## 📊 评测指标

### Reference Quality (引用质量)

| 指标 | 说明 |
|------|------|
| **WCR** | Weighted Centrality Recall - 加权中心性召回率，衡量核心论文覆盖 |
| **CC** | Community Coverage - 社区覆盖率，衡量研究方向覆盖 |
| **Bibliographic Integrity** | 文献完整性，检测虚构引用 |
| **Citation Faithfulness** | 引用忠实度，验证声明是否被引用支持 |

### Structural Soundness (结构完整性)

| 指标 | 说明 |
|------|------|
| **SC** | Structural Coherence - 结构一致性，大纲与MEKG社区对应 |
| **Structural Completeness** | 结构完整性，是否包含必要章节 |
| **Content-Structure Fidelity** | 内容与标题的一致性 |

### Content Integrity (内容完整性)

| 指标 | 说明 |
|------|------|
| **General Factualness** | 通用事实性，无引用声明验证 |
| **Writing Quality** | 写作质量（清晰度、连贯性） |
| **Scholarly Depth** | 学术深度，综合分析能力 |
| **TC** | Temporal Coverage - 时间覆盖率 |

### Ethics & Integrity (伦理与完整性)

| 指标 | 说明 |
|------|------|
| **Originality** | 原创性，检测过度引用 |
| **Societal Impact** | 社会影响讨论 |
| **Fairness** | 公平性与偏见讨论 |

### Rich Media Quality (富媒体质量)

| 指标 | 说明 |
|------|------|
| **Figure Quality** | 图片质量与相关性 |
| **Table Quality** | 表格质量与信息量 |
| **Visual-Content Alignment** | 视觉-内容对齐度 |
| **Resource Accessibility** | 资源可访问性（链接有效性） |

## 📁 目录结构

```
evaluation/
├── __init__.py                    # 模块初始化
├── config.py                      # 配置文件
├── main.py                        # 主入口
├── DESIGN.md                      # 设计文档
├── README.md                      # 使用文档
│
├── core/                          # 核心模块
│   ├── __init__.py
│   ├── base_evaluator.py          # 评测器基类
│   └── result.py                  # 评测结果数据结构
│
├── evaluators/                    # 评测器实现
│   ├── __init__.py
│   ├── reference_evaluator.py     # 引用质量评测
│   ├── structure_evaluator.py     # 结构完整性评测
│   ├── content_evaluator.py       # 内容完整性评测
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

## ⚙️ 配置说明

### EvaluationConfig

```python
from evaluation.config import EvaluationConfig

config = EvaluationConfig(
    # LLM配置
    use_llm=True,                    # 是否使用LLM
    llm_model="gpt-4o-mini",         # 模型名称
    api_url="https://api.openai.com/v1",  # API地址
    api_key="",                      # API密钥
    temperature=0.0,                 # 温度参数
    
    # 评测配置
    dimension_weights={              # 维度权重
        "reference_quality": 0.25,
        "structural_soundness": 0.20,
        "content_integrity": 0.25,
        "ethics_integrity": 0.15,
        "rich_media_quality": 0.15
    },
    
    # 采样配置
    factual_sample_size=30,          # 事实验证采样数
    content_sample_size=5,           # 内容评估采样数
    
    # 并发配置
    max_workers=10,                  # 最大并发数
    
    # 输出配置
    verbose=False                    # 详细输出
)
```

### 预设配置

```python
from evaluation.config import FAST_CONFIG, FULL_CONFIG, DEV_CONFIG

# 快速评测（不使用LLM）
config = FAST_CONFIG

# 完整评测
config = FULL_CONFIG

# 开发测试
config = DEV_CONFIG
```

## 📝 输出格式

### JSON结果

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
    "all_metrics": {
        "wcr": 0.85,
        "cc": 0.90,
        "sc": 0.80,
        ...
    },
    "recommendations": [...]
}
```

### Markdown报告

生成的报告包含：
- 📈 Overview - 总体评分和各维度得分
- 📋 Detailed Analysis - 各维度详细分析
- 📊 All Metrics - 所有指标汇总
- 💡 Recommendations - 改进建议

## 🔧 扩展开发

### 添加新的评测器

1. 继承 `BaseEvaluator` 基类
2. 实现 `name`、`weight` 属性和 `evaluate` 方法
3. 在 `evaluators/__init__.py` 中注册
4. 在 `main.py` 中添加到评测流程

```python
from evaluation.core.base_evaluator import BaseEvaluator

class MyEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "My Evaluator"
    
    @property
    def weight(self) -> float:
        return 0.1
    
    def evaluate(self, survey_content, survey_outline=None, **kwargs):
        # 实现评测逻辑
        return {
            "score": 0.8,
            "metrics": {"my_metric": 0.8},
            "details": {}
        }
```

## 📚 参考资料

- [DESIGN.md](DESIGN.md) - 详细设计文档
- [NewSurveyEvaluator](D:\PythonProjects\Survey_Benchmark\NewSurveyEvaluator) - 参考实现
- [MEKG技术文档](../mekg/docs/technical/MEKG_技术文档_CCF-A论文参考.md)

## 📄 许可证

MIT License