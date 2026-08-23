# MEKG 完整运行指南

## 快速开始

### 步骤1: 构建MEKG和大纲

```bash
python tasks/mekg_workflow/build_mekg_and_outline.py \
    --topic "Large Language Model Tool Calling" \
    --target_papers 1000 \
    --year_start 2022 \
    --year_end 2026 \
    --core_ratio 0.05 \
    --llm_concurrent 20
```

**参数说明**：
- `--topic`: 研究主题（必需）
- `--target_papers`: 目标论文数量（默认1500）
- `--year_start`: 起始年份（默认2018）
- `--year_end`: 结束年份（默认2024）
- `--core_ratio`: 核心论文比例（默认0.1=10%，你设置的0.05=5%也可以）
- `--llm_concurrent`: LLM并发数（默认5，你设置20可能更快但注意API限流）

**✅ 综述优先策略已自动启用！**

这个命令会自动：
- 搜索10篇相关综述论文
- 从每篇综述展开100个references
- 使用关键词搜索补充剩余论文
- 显示详细的关系提取进度

**预期输出目录**：
```
data/mekg_Large_Language_Model_Tool_Call_20251117_235157/
├── papers/
│   └── paper_pool.json              # 1000篇论文（含来源标记）
├── mekg/
│   ├── mekg.json                    # MEKG图谱
│   ├── mekg.graphml                 # 可视化格式
│   ├── outline.json                 # 大纲JSON
│   ├── outline.md                   # 大纲Markdown
│   ├── analysis_report.json         # 图谱分析
│   ├── core_discovery_report.json   # 核心论文发现
│   └── citation_network_stats.json  # 引文网络统计
└── dual_loop_builder.log            # 构建日志
```

**预期耗时**（以1000篇论文为例）：
- 综述搜索: ~2分钟
- References展开: ~5-8分钟
- 关键词补充: ~3-5分钟
- 引文网络构建: ~1分钟
- 核心论文发现: ~30秒
- 关系提取: ~15-30分钟（取决于并发数和候选对数量）
- **总计**: 约30-50分钟

---

### 步骤2: 集成到SurveyY格式

```bash
python tasks/mekg_workflow/integrate_mekg_to_survey.py \
    --mekg_dir data/mekg_Large_Language_Model_Tool_Call_20251117_235157/mekg \
    --papers_dir data/mekg_Large_Language_Model_Tool_Call_20251117_235157/papers \
    --task_id mekg_Large_Language_Model_Tool_Call_20251117_235157
```

**注意**：将上面的目录名替换为实际生成的目录名。

这一步会：
- 将MEKG转换为SurveyY的格式
- 创建`outputs/mekg_XXX/`目录
- 生成`outlines.json`、`references.bib`等文件

**预期耗时**: ~1分钟

---

### 步骤3: 生成Survey内容

```bash
python tasks/workflow/04_gen_content.py --task_id mekg_Large_Language_Model_Tool_Call_20251117_235157
```

这一步会：
- 基于大纲生成每个章节的内容
- 使用LLM生成学术文本
- 引用相关论文

**预期耗时**: ~20-40分钟（取决于章节数和LLM速度）

---

### 步骤4: 后处理优化

```bash
python tasks/workflow/05_post_refine.py --task_id mekg_Large_Language_Model_Tool_Call_20251117_235157
```

这一步会：
- 优化文本质量
- 修正引用格式
- 添加图表

**预期耗时**: ~10-20分钟

---

### 步骤5: 生成LaTeX

```bash
python tasks/workflow/06_gen_latex.py --task_id mekg_Large_Language_Model_Tool_Call_20251117_235157
```

这一步会：
- 生成最终的LaTeX文件
- 创建PDF（如果安装了LaTeX）

**预期耗时**: ~5分钟

---

## 运行中你会看到的新功能

### 1. 综述搜索日志
```
[策略1] 综述优先 - 搜索并展开综述references
搜索综述论文: [...], 最多10篇
找到 8 篇综述论文 (平均引用: 245, 年份范围: 2022-2024)
  找到 8 篇综述论文
从 8 篇综述中展开references
  收集到 623 个唯一的reference IDs
  批量获取论文详情: 623 个ID...
    处理批次 1/13 (50 IDs)
    批次 1 完成: 成功 48/50
```

### 2. 关系提取进度
```
[backbone] 开始关系提取: 1225 对 (并发数=20)
[backbone] 进度: 123/1225 (10.0%) | 成功: 37 | 命中率: 30.1% | 预计剩余: 12分45秒
[backbone] 进度: 245/1225 (20.0%) | 成功: 73 | 命中率: 29.8% | 预计剩余: 10分18秒
[backbone] 进度: 368/1225 (30.0%) | 成功: 112 | 命中率: 30.4% | 预计剩余: 8分02秒
...
[backbone] 提取完成: 364/1225 对有关系 (命中率=29.7%, 失败=861, 耗时=185.3秒, 平均=0.15秒/对)
```

### 3. 最终统计
```
论文池收集完成:
  总论文数: 1000
  - 综述论文: 8
  - 综述references: 587
  - 关键词搜索: 405
  平均引用数: 156.3
  平均参考文献数: 52.1
```

---

## 常见问题

### Q1: 如何调整综述策略？

如果你想调整综述策略的参数，可以修改 `src/modules/mekg/dual_loop_builder.py` 的 `_collect_paper_pool` 方法：

```python
self.papers_pool = await self.paper_collector.collect_comprehensive_pool(
    keywords=keywords,
    target_count=self.target_paper_count,
    year_start=year_start,
    year_end=year_end,
    enrich_cited_by=False,
    use_survey_strategy=True,      # 设为False可禁用
    survey_count=15,               # 增加综述数量
    max_refs_per_survey=150        # 增加每篇综述的references数
)
```

### Q2: 遇到API 429错误怎么办？

降低并发数：
```bash
--llm_concurrent 5  # 或更低
```

### Q3: 如何查看详细日志？

查看构建日志：
```bash
cat data/mekg_XXX/dual_loop_builder.log
```

### Q4: 命中率太低怎么办？

综述策略应该已经显著提升了命中率（从2%到15-25%）。如果还是太低：
1. 检查是否找到了高质量综述
2. 增加综述数量和references展开数
3. 检查topic是否太宽泛或太窄

### Q5: 想要更快的构建速度？

```bash
# 减少论文数量
--target_papers 500

# 增加并发数（注意API限制）
--llm_concurrent 30

# 禁用PDF下载（默认已禁用）
# 不使用 --enable_pdf 标志
```

### Q6: 输出目录名太长怎么办？

使用自定义输出目录：
```bash
--output_dir data/my_mekg
```

---

## 高级用法

### 完整参数列表

```bash
python tasks/mekg_workflow/build_mekg_and_outline.py --help
```

### 禁用综述策略（不推荐）

如果你的领域缺少综述论文，可以手动禁用：

修改 `src/modules/mekg/dual_loop_builder.py` 第267行：
```python
use_survey_strategy=False,  # 禁用综述策略
```

### 调整核心论文比例

```bash
--core_ratio 0.1   # 10%的核心论文（默认）
--core_ratio 0.05  # 5%的核心论文（更精英）
--core_ratio 0.15  # 15%的核心论文（更宽松）
```

---

## 一键运行全流程（示例脚本）

创建 `run_full_mekg_pipeline.sh`:

```bash
#!/bin/bash

TOPIC="Large Language Model Tool Calling"
YEAR_START=2022
YEAR_END=2026
TARGET_PAPERS=1000

echo "Step 1: Building MEKG..."
python tasks/mekg_workflow/build_mekg_and_outline.py \
    --topic "$TOPIC" \
    --target_papers $TARGET_PAPERS \
    --year_start $YEAR_START \
    --year_end $YEAR_END \
    --core_ratio 0.05 \
    --llm_concurrent 20

# 获取最新的输出目录
LATEST_DIR=$(ls -td data/mekg_* | head -1)
TASK_ID=$(basename $LATEST_DIR)

echo "Step 2: Integrating to SurveyY format..."
python tasks/mekg_workflow/integrate_mekg_to_survey.py \
    --mekg_dir $LATEST_DIR/mekg \
    --papers_dir $LATEST_DIR/papers \
    --task_id $TASK_ID

echo "Step 3: Generating content..."
python tasks/workflow/04_gen_content.py --task_id $TASK_ID

echo "Step 4: Post-refining..."
python tasks/workflow/05_post_refine.py --task_id $TASK_ID

echo "Step 5: Generating LaTeX..."
python tasks/workflow/06_gen_latex.py --task_id $TASK_ID

echo "Done! Check outputs/$TASK_ID/"
```

运行：
```bash
chmod +x run_full_mekg_pipeline.sh
./run_full_mekg_pipeline.sh
```

---

## 预期改进效果对比

### 之前（纯关键词搜索）
- 论文来源：100% 关键词搜索
- 引文网络密度：0.0018
- 关系提取命中率：2.2%
- 提取时间：很长（大量无效候选对）

### 现在（综述优先策略）
- 论文来源：
  - 综述论文：1%
  - 综述references：60%
  - 关键词搜索：39%
- 引文网络密度：0.005-0.008 (提升3-4倍)
- 关系提取命中率：15-25% (提升7-11倍)
- 提取时间：更快（更少无效候选对）
- 进度可见：实时显示进度和ETA

---

## 总结

你的命令完全正确！只需：

1. **运行第一个命令** - 等待30-50分钟
2. **查看输出目录** - 记录实际的目录名
3. **替换后续命令中的目录名** - 运行步骤2-5

现在就可以开始了！🚀