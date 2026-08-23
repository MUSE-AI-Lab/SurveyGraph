# SurveyGraph 项目结构说明

## 目录结构

```
SurveyGraph/
├── src/                          # 核心业务逻辑（SurveyX 原版模块）
│   ├── configs/                  # 配置文件
│   │   ├── config.py            # 主配置
│   │   ├── constants.py         # 常量定义
│   │   ├── logger.py            # 日志配置
│   │   └── LLM.yaml             # LLM 配置
│   ├── models/                   # 模型层
│   │   ├── generator/           # 内容生成器
│   │   ├── LLM/                 # LLM 接口（ChatAgent, EmbedAgent）
│   │   ├── monitor/             # 监控（时间、Token）
│   │   ├── post_refine/         # 后处理
│   │   └── rag/                 # RAG 模块
│   ├── modules/                  # 功能模块
│   │   ├── analysis/            # 分析模块（演化分析等）
│   │   ├── fig_retrieve/        # 图片检索
│   │   ├── heuristic_modules/   # 启发式模块
│   │   ├── latex_handler/       # LaTeX 处理
│   │   ├── multimodal/          # 多模态处理
│   │   ├── outline/             # 大纲生成
│   │   ├── post_refine/         # 后处理模块
│   │   └── preprocessor/        # 预处理（数据获取、清洗）
│   └── schemas/                  # 数据模型定义
│
├── mekg/                         # MEKG 图谱模块
│   ├── src/                      # MEKG 核心代码
│   │   ├── survey/              # 流水线核心
│   │   │   ├── pipeline.py      # 主流水线
│   │   │   ├── outline_generator.py
│   │   │   ├── content_generator.py
│   │   │   └── evaluator.py
│   │   ├── builders/            # 构建器（论文收集、分类、关系发现）
│   │   │   └── paper_collector.py
│   │   ├── processing/          # 论文处理
│   │   ├── extraction/          # 关系提取
│   │   ├── storage/             # 图数据库存储
│   │   ├── visualization/       # 可视化
│   │   ├── analysis/            # 分析模块
│   │   ├── automation/          # 自动化模块
│   │   └── core/                # 核心数据结构
│   ├── scripts/                  # MEKG 相关脚本（测试、工具）
│   ├── webapp/                   # Web 应用
│   └── data/                     # MEKG 数据
│
├── evaluation/                   # 评估模块
│   ├── core/                     # 核心评估器
│   ├── evaluators/              # 各类评估器
│   ├── report/                  # 报告生成
│   └── utils/                   # 工具函数
│
├── tasks/                        # 入口脚本
│   ├── mekg_run.py              # 主入口（MEKG 驱动的综述生成）
│   └── workflow/                # 工作流脚本
│
├── tools/                        # 工具脚本
│   ├── check_expense.py         # 费用检查
│   ├── test_crawler.py          # 爬虫测试
│   └── ...
│
├── tests/                        # 测试代码
│
├── docs/                         # 文档
│   ├── mekg/                    # MEKG 相关文档
│   │   ├── design/              # 设计文档
│   │   ├── guides/              # 使用指南
│   │   ├── technical/           # 技术文档
│   │   └── reports/             # 报告
│   └── PROJECT_STRUCTURE.md     # 本文件
│
├── outputs/                      # 输出目录（生成的综述）
├── resources/                    # 资源文件（LaTeX 模板等）
├── frontend/                     # 前端代码
└── OpenAlex/                     # OpenAlex 相关模块
```

## 核心模块说明

### 1. `src/` - SurveyX 核心模块
这是原版 SurveyX 的核心代码，包含：
- **LLM 接口**：`ChatAgent` 和 `EmbedAgent`
- **内容生成**：`ContentGenerator`、`ReflectiveContentGenerator`
- **后处理**：`PostRefiner`、各种 Refiner
- **LaTeX 处理**：表格、图片、文本构建器

### 2. `mekg/src/` - MEKG 图谱模块
MEKG（Method-Entity Knowledge Graph）相关代码：
- **流水线**：`MEKGSurveyPipeline` - 完整的综述生成流水线
- **构建器**：论文收集、分类、关系发现
- **存储**：支持 Memgraph、Kuzu 等图数据库
- **可视化**：图谱可视化

### 3. `evaluation/` - 评估模块
综述质量评估：
- 内容评估
- 结构评估
- 参考文献评估
- 媒体评估
- 伦理评估

### 4. `tasks/` - 入口脚本
- `mekg_run.py`：主入口，支持命令行参数和断点续传

## 使用方法

### 运行综述生成
```bash
python tasks/mekg_run.py --topic "Large Language Model Agents" --max_papers 200
```

### 从断点恢复
```bash
python tasks/mekg_run.py --resume --task_id "2025-12-15-1933_Large_Language_Model"
```

## 依赖关系

```
tasks/mekg_run.py
    ├── src/configs/logger.py
    ├── mekg/src/survey/pipeline.py
    │   ├── mekg/src/builders/paper_collector.py
    │   ├── mekg/src/survey/outline_generator.py
    │   ├── mekg/src/survey/content_generator.py
    │   ├── mekg/src/survey/evaluator.py
    │   ├── src/models/generator/content_generator.py
    │   ├── src/models/post_refine/post_refiner.py
    │   └── ...
    ├── src/models/generator/latex_generator.py
    └── evaluation/main.py