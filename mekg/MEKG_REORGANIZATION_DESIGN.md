# MEKG 知识图谱模块重组设计文档

## 1. 概述

### 1.1 目标
将分散在项目各处的MEKG知识图谱相关文件整合到统一的 `mekg/` 文件夹下，形成一个独立、完整的模块。

### 1.2 范围
- ✅ **包含**: MEKG知识图谱构建、存储、分析、可视化相关的所有代码
- ❌ **排除**: 综述生成相关的代码（如outline生成、content生成等）

---

## 2. 新的文件夹结构

```
mekg/
├── README.md                    # MEKG模块说明文档
├── MEKG_REORGANIZATION_DESIGN.md  # 本设计文档
│
├── src/                         # 核心源代码
│   ├── __init__.py
│   ├── core/                    # 核心数据结构和基础类
│   │   ├── __init__.py
│   │   ├── data_structures.py   # MEKGGraph, MEKGNode, MEKGEdge等
│   │   └── analyzer.py          # MEKGAnalyzer
│   │
│   ├── extraction/              # 实体和关系抽取
│   │   ├── __init__.py
│   │   ├── semantic_entity_extractor.py
│   │   ├── citation_context_analyzer.py
│   │   ├── attribute_based_relation_extractor.py
│   │   ├── enhanced_relation_discoverer.py
│   │   ├── incremental_relation_discoverer.py
│   │   ├── relation_reasoner.py
│   │   └── intelligent_candidate_generator.py
│   │
│   ├── processing/              # 数据处理
│   │   ├── __init__.py
│   │   ├── entity_cleaner.py
│   │   ├── entity_disambiguator.py
│   │   ├── pdf_processor.py
│   │   └── paper_pool_collector.py
│   │
│   ├── storage/                 # 存储层
│   │   ├── __init__.py
│   │   ├── semantic_entity_db.py
│   │   ├── kuzu_graph_db.py
│   │   └── memgraph_graph_db.py
│   │
│   ├── analysis/                # 图谱分析
│   │   ├── __init__.py
│   │   ├── community_labeler.py
│   │   ├── core_paper_discoverer.py
│   │   ├── citation_network_builder.py
│   │   ├── igraph_adapter.py
│   │   └── evaluation_metrics.py
│   │
│   ├── automation/              # 自动化构建
│   │   ├── __init__.py
│   │   ├── incremental_builder.py
│   │   ├── crawler_manager.py
│   │   ├── pipeline_orchestrator.py
│   │   ├── maintenance_manager.py
│   │   └── topic_builder.py
│   │
│   └── visualization/           # 可视化
│       ├── __init__.py
│       ├── graph_visualizer.py
│       └── web/                 # Web可视化前端
│           ├── index.html
│           ├── css/
│           │   └── style.css
│           └── js/
│               ├── app.js
│               └── data.js
│
├── scripts/                     # 运行脚本
│   ├── build/                   # 构建脚本
│   │   ├── build_mekg_v3.py
│   │   ├── build_large_graph.py
│   │   └── run_mekg_builder.py
│   │
│   ├── test/                    # 测试脚本
│   │   ├── test_mekg_v3.py
│   │   ├── test_mekg_v2_integration.py
│   │   ├── test_igraph_performance.py
│   │   ├── test_relation_discovery.py
│   │   ├── test_citation_analyzer.py
│   │   ├── test_entity_disambiguator.py
│   │   ├── test_pdf_sections.py
│   │   ├── test_auto_build.py
│   │   └── test_automation_service.py
│   │
│   ├── tools/                   # 工具脚本
│   │   ├── view_graph_stats.py
│   │   ├── export_mekg.py
│   │   ├── extract_survey_subgraph.py
│   │   ├── reprocess_data.py
│   │   ├── sync_mekg_attrs_to_papers.py
│   │   └── auto_surfer.py
│   │
│   └── web/                     # Web服务启动脚本
│       ├── start_mekg_web.py
│       ├── start_mekg_panel.py
│       ├── start_mekg_pro.py
│       ├── start_dashboard.py
│       ├── start_enterprise.py
│       ├── live_dashboard.py
│       └── enterprise_dashboard.py
│
├── docs/                        # 文档
│   ├── guides/                  # 使用指南
│   │   ├── MEKG_快速开始指南.md
│   │   ├── MEKG_完整运行指南.md
│   │   ├── MEKG_V2_使用指南.md
│   │   ├── MEKG_V3_使用指南.md
│   │   └── MEKG_高性能图算法使用指南.md
│   │
│   ├── design/                  # 设计文档
│   │   ├── MEKG_V2_设计方案.md
│   │   ├── MEKG_V3_完整架构设计.md
│   │   ├── MEKG_V3_改进方案_借鉴NLP-AKG.md
│   │   ├── MEKG_Automation_and_Visualization_Design.md
│   │   ├── MEKG_V2_关系类型体系.md
│   │   └── MEKG_图数据库优化方案.md
│   │
│   ├── technical/               # 技术文档
│   │   ├── MEKG_技术文档_CCF-A论文参考.md
│   │   ├── MEKG_SYSTEM_OVERVIEW.md
│   │   ├── MEMGRAPH_SETUP.md
│   │   ├── MEKG_关系构建优化方案.md
│   │   ├── MEKG_关系提取问题修复.md
│   │   ├── MEKG_性能优化说明.md
│   │   ├── MEKG_性能优化总结.md
│   │   └── MEKG_重试机制说明.md
│   │
│   ├── reports/                 # 报告文档
│   │   ├── MEKG知识图谱调研报告.md
│   │   ├── MEKG_汇报文档_导师反馈整理.md
│   │   ├── MEKG_实施总结.md
│   │   ├── MEKG_集成实施总结.md
│   │   ├── MEKG算法学术严谨性分析.md
│   │   └── MEKG_架构分析与改进方案.md
│   │
│   └── references/              # 参考资料
│       └── NLP-AKG.pdf
│
└── data/                        # 数据目录（可选，用于存放数据库文件）
    └── .gitkeep
```

---

## 3. 文件迁移映射

### 3.1 核心源代码迁移

| 原路径 | 新路径 |
|--------|--------|
| `src/modules/mekg/data_structures.py` | `mekg/src/core/data_structures.py` |
| `src/modules/mekg/analyzer.py` | `mekg/src/core/analyzer.py` |
| `src/modules/mekg/semantic_entity_extractor.py` | `mekg/src/extraction/semantic_entity_extractor.py` |
| `src/modules/mekg/citation_context_analyzer.py` | `mekg/src/extraction/citation_context_analyzer.py` |
| `src/modules/mekg/attribute_based_relation_extractor.py` | `mekg/src/extraction/attribute_based_relation_extractor.py` |
| `src/modules/mekg/enhanced_relation_discoverer.py` | `mekg/src/extraction/enhanced_relation_discoverer.py` |
| `src/modules/mekg/incremental_relation_discoverer.py` | `mekg/src/extraction/incremental_relation_discoverer.py` |
| `src/modules/mekg/relation_reasoner.py` | `mekg/src/extraction/relation_reasoner.py` |
| `src/modules/mekg/intelligent_candidate_generator.py` | `mekg/src/extraction/intelligent_candidate_generator.py` |
| `src/modules/mekg/entity_cleaner.py` | `mekg/src/processing/entity_cleaner.py` |
| `src/modules/mekg/entity_disambiguator.py` | `mekg/src/processing/entity_disambiguator.py` |
| `src/modules/mekg/pdf_processor.py` | `mekg/src/processing/pdf_processor.py` |
| `src/modules/mekg/paper_pool_collector.py` | `mekg/src/processing/paper_pool_collector.py` |
| `src/modules/mekg/semantic_entity_db.py` | `mekg/src/storage/semantic_entity_db.py` |
| `src/modules/mekg/storage/kuzu_graph_db.py` | `mekg/src/storage/kuzu_graph_db.py` |
| `src/modules/mekg/storage/memgraph_graph_db.py` | `mekg/src/storage/memgraph_graph_db.py` |
| `src/modules/mekg/community_labeler.py` | `mekg/src/analysis/community_labeler.py` |
| `src/modules/mekg/core_paper_discoverer.py` | `mekg/src/analysis/core_paper_discoverer.py` |
| `src/modules/mekg/citation_network_builder.py` | `mekg/src/analysis/citation_network_builder.py` |
| `src/modules/mekg/igraph_adapter.py` | `mekg/src/analysis/igraph_adapter.py` |
| `src/modules/mekg/evaluation_metrics.py` | `mekg/src/analysis/evaluation_metrics.py` |
| `src/modules/mekg/automation/incremental_builder.py` | `mekg/src/automation/incremental_builder.py` |
| `src/modules/mekg/automation/crawler_manager.py` | `mekg/src/automation/crawler_manager.py` |
| `src/modules/mekg/pipeline_orchestrator.py` | `mekg/src/automation/pipeline_orchestrator.py` |
| `src/modules/mekg/maintenance_manager.py` | `mekg/src/automation/maintenance_manager.py` |
| `src/modules/mekg/topic_builder.py` | `mekg/src/automation/topic_builder.py` |
| `src/modules/mekg/graph_visualizer.py` | `mekg/src/visualization/graph_visualizer.py` |
| `src/visualization/mekg_viewer/*` | `mekg/src/visualization/web/*` |

### 3.2 排除的文件（综述生成相关）

以下文件**不迁移**到mekg模块，因为它们属于综述生成流程：

- `src/modules/mekg/llm_enhanced_outline_generator.py` - 大纲生成
- `src/modules/mekg/graph_driven_mounter.py` - 论文挂载
- `src/modules/mekg/survey_template_library.py` - 综述模板库
- `src/modules/mekg/template_extractor.py` - 模板提取
- `src/modules/mekg/dual_search_orchestrator.py` - 双重搜索（综述相关）
- `src/modules/mekg/graph_merger.py` - 图融合（综述相关）
- `src/modules/mekg/graph_rag_searcher.py` - RAG搜索（综述相关）
- `scripts/generate_survey_from_mekg.py` - 综述生成
- `scripts/generate_survey_v2.py` - 综述生成V2
- `scripts/extract_survey_templates.py` - 模板提取

### 3.3 脚本迁移

| 原路径 | 新路径 |
|--------|--------|
| `scripts/build_mekg_v3.py` | `mekg/scripts/build/build_mekg_v3.py` |
| `scripts/build_large_graph.py` | `mekg/scripts/build/build_large_graph.py` |
| `scripts/run_mekg_builder.py` | `mekg/scripts/build/run_mekg_builder.py` |
| `scripts/test_mekg_v3.py` | `mekg/scripts/test/test_mekg_v3.py` |
| `scripts/test_mekg_v2_integration.py` | `mekg/scripts/test/test_mekg_v2_integration.py` |
| `scripts/test_igraph_performance.py` | `mekg/scripts/test/test_igraph_performance.py` |
| `scripts/test_relation_discovery.py` | `mekg/scripts/test/test_relation_discovery.py` |
| `scripts/test_citation_analyzer.py` | `mekg/scripts/test/test_citation_analyzer.py` |
| `scripts/test_entity_disambiguator.py` | `mekg/scripts/test/test_entity_disambiguator.py` |
| `scripts/test_pdf_sections.py` | `mekg/scripts/test/test_pdf_sections.py` |
| `scripts/test_auto_build.py` | `mekg/scripts/test/test_auto_build.py` |
| `scripts/test_automation_service.py` | `mekg/scripts/test/test_automation_service.py` |
| `scripts/view_graph_stats.py` | `mekg/scripts/tools/view_graph_stats.py` |
| `scripts/export_mekg.py` | `mekg/scripts/tools/export_mekg.py` |
| `scripts/extract_survey_subgraph.py` | `mekg/scripts/tools/extract_survey_subgraph.py` |
| `scripts/reprocess_data.py` | `mekg/scripts/tools/reprocess_data.py` |
| `scripts/sync_mekg_attrs_to_papers.py` | `mekg/scripts/tools/sync_mekg_attrs_to_papers.py` |
| `scripts/auto_surfer.py` | `mekg/scripts/tools/auto_surfer.py` |
| `scripts/start_mekg_web.py` | `mekg/scripts/web/start_mekg_web.py` |
| `scripts/start_mekg_panel.py` | `mekg/scripts/web/start_mekg_panel.py` |
| `scripts/start_mekg_pro.py` | `mekg/scripts/web/start_mekg_pro.py` |
| `scripts/start_dashboard.py` | `mekg/scripts/web/start_dashboard.py` |
| `scripts/start_enterprise.py` | `mekg/scripts/web/start_enterprise.py` |
| `scripts/live_dashboard.py` | `mekg/scripts/web/live_dashboard.py` |
| `scripts/enterprise_dashboard.py` | `mekg/scripts/web/enterprise_dashboard.py` |

### 3.4 文档迁移

| 原路径 | 新路径 |
|--------|--------|
| `README/MEKG_快速开始指南.md` | `mekg/docs/guides/MEKG_快速开始指南.md` |
| `README/MEKG_完整运行指南.md` | `mekg/docs/guides/MEKG_完整运行指南.md` |
| `README/MEKG_V2_使用指南.md` | `mekg/docs/guides/MEKG_V2_使用指南.md` |
| `README/MEKG_V3_使用指南.md` | `mekg/docs/guides/MEKG_V3_使用指南.md` |
| `README/MEKG_高性能图算法使用指南.md` | `mekg/docs/guides/MEKG_高性能图算法使用指南.md` |
| `README/MEKG_V2_设计方案.md` | `mekg/docs/design/MEKG_V2_设计方案.md` |
| `README/MEKG_V3_完整架构设计.md` | `mekg/docs/design/MEKG_V3_完整架构设计.md` |
| `README/MEKG_V3_改进方案_借鉴NLP-AKG.md` | `mekg/docs/design/MEKG_V3_改进方案_借鉴NLP-AKG.md` |
| `README/MEKG_Automation_and_Visualization_Design.md` | `mekg/docs/design/MEKG_Automation_and_Visualization_Design.md` |
| `README/MEKG_V2_关系类型体系.md` | `mekg/docs/design/MEKG_V2_关系类型体系.md` |
| `README/MEKG_图数据库优化方案.md` | `mekg/docs/design/MEKG_图数据库优化方案.md` |
| `README/MEKG_技术文档_CCF-A论文参考.md` | `mekg/docs/technical/MEKG_技术文档_CCF-A论文参考.md` |
| `docs/MEKG_SYSTEM_OVERVIEW.md` | `mekg/docs/technical/MEKG_SYSTEM_OVERVIEW.md` |
| `docs/MEMGRAPH_SETUP.md` | `mekg/docs/technical/MEMGRAPH_SETUP.md` |
| `README/MEKG_关系构建优化方案.md` | `mekg/docs/technical/MEKG_关系构建优化方案.md` |
| `README/MEKG_关系提取问题修复.md` | `mekg/docs/technical/MEKG_关系提取问题修复.md` |
| `README/MEKG_性能优化说明.md` | `mekg/docs/technical/MEKG_性能优化说明.md` |
| `README/MEKG_性能优化总结.md` | `mekg/docs/technical/MEKG_性能优化总结.md` |
| `README/MEKG_重试机制说明.md` | `mekg/docs/technical/MEKG_重试机制说明.md` |
| `README/MEKG知识图谱调研报告.md` | `mekg/docs/reports/MEKG知识图谱调研报告.md` |
| `README/MEKG_汇报文档_导师反馈整理.md` | `mekg/docs/reports/MEKG_汇报文档_导师反馈整理.md` |
| `README/MEKG_实施总结.md` | `mekg/docs/reports/MEKG_实施总结.md` |
| `README/MEKG_集成实施总结.md` | `mekg/docs/reports/MEKG_集成实施总结.md` |
| `README/MEKG算法学术严谨性分析.md` | `mekg/docs/reports/MEKG算法学术严谨性分析.md` |
| `README/MEKG_架构分析与改进方案.md` | `mekg/docs/reports/MEKG_架构分析与改进方案.md` |
| `README/NLP-AKG.pdf` | `mekg/docs/references/NLP-AKG.pdf` |

---

## 4. 导入路径更新策略

### 4.1 新的导入路径

迁移后，导入路径将从：
```python
from src.modules.mekg.data_structures import MEKGGraph
from src.modules.mekg.semantic_entity_extractor import SemanticEntityExtractor
```

变为：
```python
from mekg.src.core.data_structures import MEKGGraph
from mekg.src.extraction.semantic_entity_extractor import SemanticEntityExtractor
```

### 4.2 兼容性方案

为保持向后兼容，在 `src/modules/mekg/__init__.py` 中添加重导出：
```python
# 兼容性导入 - 重定向到新位置
from mekg.src.core.data_structures import *
from mekg.src.extraction.semantic_entity_extractor import *
# ... 其他重导出
```

---

## 5. 实施步骤

1. **创建目录结构** - 创建mekg/下的所有子目录
2. **复制核心源代码** - 将src/modules/mekg/下的文件复制到新位置
3. **复制脚本文件** - 将scripts/下的mekg相关脚本复制到新位置
4. **复制文档** - 将README/和docs/下的MEKG文档复制到新位置
5. **复制可视化文件** - 将src/visualization/mekg_viewer/复制到新位置
6. **创建__init__.py文件** - 为每个包创建初始化文件
7. **更新导入路径** - 更新所有文件中的导入语句
8. **创建README.md** - 为mekg模块创建说明文档
9. **验证** - 运行测试确保功能正常

---

## 6. 注意事项

1. **保留原文件**: 在确认新结构工作正常前，不删除原文件
2. **导入兼容性**: 通过重导出保持向后兼容
3. **相对路径**: 脚本中的相对路径需要更新
4. **数据库路径**: 数据库文件路径可能需要调整

---

## 7. 确认

请确认此设计方案是否符合您的预期，我将按照此方案开始实施文件整理。