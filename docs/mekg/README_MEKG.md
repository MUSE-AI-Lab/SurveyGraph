# MEKG综述生成系统使用指南

## 🚀 快速开始

### 1. 安装依赖

```bash
# 激活虚拟环境
.venv\Scripts\activate  # Windows
# 或 source .venv/bin/activate  # Linux/Mac

# 安装必要的库
pip install networkx python-louvain httpx loguru

# 可选：安装Leiden算法（更好的社区发现）
pip install leidenalg igraph
```

### 2. 快速测试（20篇论文）

```bash
python quick_test.py
```

这会：
- 爬取20篇论文
- 构建MEKG知识图谱
- 生成综述大纲
- 生成分析报告

**预计时间**: 5-10分钟

### 3. 完整运行（100篇论文）

```bash
python run_mekg_pipeline.py --query "large language model agents" --max-papers 100
```

**预计时间**: 30-60分钟

### 4. 大规模运行（500篇论文）

```bash
python run_mekg_pipeline.py \
    --query "reinforcement learning" \
    --max-papers 500 \
    --seed-count 20 \
    --download-pdf
```

**预计时间**: 2-3小时（含PDF下载）

---

## 📁 输出文件结构

运行后会在`output/`目录下生成：

```
output/20241115_123456_large_language_model_agents/
├── 01_crawled_data/
│   ├── collected_papers.json      # 论文元数据
│   ├── citation_edges.json        # 引用关系
│   └── crawl_statistics.json      # 爬取统计
│
├── 03_mekg/
│   ├── mekg.json                  # 知识图谱（JSON格式）
│   ├── mekg.graphml               # 知识图谱（GraphML格式，可用Gephi可视化）
│   ├── mekg_analysis_report.json  # 完整分析报告
│   ├── papers.json                # 处理后的论文数据
│   └── edges.json                 # 处理后的边数据
│
├── 04_outline/
│   ├── outline.json               # 大纲（JSON格式）
│   └── outline.md                 # 大纲（Markdown格式）
│
├── 05_reports/
│   ├── mekg_analysis_report.json  # 完整分析报告
│   └── summary.md                 # 摘要报告
│
├── completion_status.json         # 完成状态
└── pipeline.log                   # 运行日志
```

---

## 🔧 命令行参数

### 必需参数

- `--query`: 搜索查询关键词
  ```bash
  --query "large language model agents"
  ```

### 可选参数

- `--max-papers`: 最大论文数量（默认100）
  ```bash
  --max-papers 500
  ```

- `--seed-count`: 种子论文数量（默认10）
  ```bash
  --seed-count 20
  ```

- `--output-dir`: 输出根目录（默认output）
  ```bash
  --output-dir my_surveys
  ```

- `--download-pdf`: 是否下载PDF文件
  ```bash
  --download-pdf
  ```

- `--use-mineru`: 是否使用MinerU解析PDF（需要MinerU环境）
  ```bash
  --use-mineru
  ```

### 示例命令

```bash
# 1. 快速测试（20篇）
python run_mekg_pipeline.py --query "graph neural networks" --max-papers 20

# 2. 标准运行（100篇）
python run_mekg_pipeline.py --query "transformer models" --max-papers 100 --seed-count 10

# 3. 完整运行（500篇 + PDF）
python run_mekg_pipeline.py \
    --query "reinforcement learning" \
    --max-papers 500 \
    --seed-count 20 \
    --download-pdf

# 4. 自定义输出目录
python run_mekg_pipeline.py \
    --query "computer vision" \
    --max-papers 200 \
    --output-dir surveys/cv_2024
```

---

## 📊 查看结果

### 1. 查看大纲

```bash
# Markdown格式（人类可读）
cat output/*/04_outline/outline.md

# JSON格式（程序处理）
cat output/*/04_outline/outline.json
```

### 2. 查看分析报告

```bash
# 摘要报告
cat output/*/05_reports/summary.md

# 完整报告
cat output/*/05_reports/mekg_analysis_report.json
```

### 3. 可视化知识图谱

使用[Gephi](https://gephi.org/)打开：

```
output/*/03_mekg/mekg.graphml
```

推荐布局算法：
- Force Atlas 2（力导向）
- Fruchterman Reingold

节点大小按PageRank，颜色按社区ID。

---

## 🎯 核心功能说明

### 1. 雪球采样爬虫

从少量种子论文出发，通过引用网络扩展到500+篇：

```python
from src.modules.paper_acquisition import SnowballPaperCrawler

crawler = SnowballPaperCrawler(
    output_dir=Path("data/crawled"),
    max_papers=500,
    max_depth=3,
    min_citations=5
)

results = await crawler.crawl_from_query(
    query="LLM agents",
    seed_count=20
)
```

### 2. MEKG知识图谱构建

```python
from src.modules.mekg import MEKGBuilder

builder = MEKGBuilder(output_dir=Path("data/mekg"))

mekg = await builder.build_from_crawled_data(
    papers_file=Path("data/crawled/collected_papers.json"),
    edges_file=Path("data/crawled/citation_edges.json")
)
```

### 3. 大纲生成（不依赖RAG）

```python
from src.modules.mekg import MEKGOutlineGenerator

generator = MEKGOutlineGenerator(mekg)

outline = generator.generate_outline(
    title="A Survey on LLM Agents",
    max_sections=6
)
```

### 4. 图谱分析

```python
from src.modules.mekg import MEKGAnalyzer

analyzer = MEKGAnalyzer(mekg)

# 计算中心性
analyzer.calculate_centrality_metrics()

# 社区发现
communities = analyzer.detect_communities()

# 评测指标
wcr = analyzer.calculate_wcr()  # Weighted Centrality Recall
cc = analyzer.calculate_cc()    # Community Coverage
sc = analyzer.calculate_sc()    # Structural Coherence
```

---

## ⚙️ 配置说明

### LLM API配置

默认使用pisces.ink API（已内置配置）：

如需修改，编辑`src/modules/mekg/relation_extractor.py`和`src/agents/base_agent.py`。

### OpenAlex配置

默认邮箱：`2803505580@qq.com`

如需修改，编辑`OpenAlex/scholar.py`：

```python
DEFAULT_EMAIL = "your_email@example.com"
```

---

## 🐛 故障排查

### 问题1: ImportError

```
ImportError: cannot import name 'MEKGOutlineGenerator'
```

**解决**: 确保`src/modules/mekg/__init__.py`已更新（已修复）

### 问题2: API速率限制

```
速率限制(429)
```

**解决**: 
- OpenAlex有速率限制（10req/s）
- 代码已包含自动重试和指数退避
- 如持续出现，等待1分钟后重试

### 问题3: MinerU解析失败

```
MinerU解析出错
```

**解决**:
- 当前MinerU为占位代码
- 首次运行建议不使用`--use-mineru`
- 如需MinerU，请先配置环境后修改`pdf_processor.py`

### 问题4: 网络超时

```
Network error downloading PDF
```

**解决**:
- 部分PDF链接可能失效
- 代码会自动跳过并继续
- 查看日志了解成功率

---

## 📈 性能优化

### 1. 并发控制

```python
# paper_crawler.py
max_concurrent = 5  # 控制并发请求数

# pdf_processor.py
max_concurrent_downloads = 5  # 控制并发下载数
```

### 2. 减少论文数量（快速测试）

```bash
python run_mekg_pipeline.py --query "test" --max-papers 20 --seed-count 5
```

### 3. 跳过PDF下载

```bash
# 不加 --download-pdf 参数
python run_mekg_pipeline.py --query "test" --max-papers 100
```

---

## 🎓 适用场景

### 1. 快速原型（20-50篇）

适合快速验证想法或探索新领域：

```bash
python run_mekg_pipeline.py --query "your_topic" --max-papers 20
```

### 2. 标准综述（100-200篇）

适合一般规模的综述论文：

```bash
python run_mekg_pipeline.py --query "your_topic" --max-papers 150
```

### 3. 深度综述（500+篇）

适合CCF-A论文级别的深度综述：

```bash
python run_mekg_pipeline.py \
    --query "your_topic" \
    --max-papers 500 \
    --seed-count 30 \
    --download-pdf
```

---

## 📝 下一步工作

### 立即可用
✅ 论文爬取
✅ MEKG构建
✅ 大纲生成
✅ 图谱分析

### 待完成（需要你实现）
⏳ 具体智能体（Planner, Constructor, Writer, Refiner）
⏳ 编排器（Orchestrator）
⏳ 内容生成（基于MEKG）
⏳ 五维度评测

### 集成现有框架
需要修改：
- `src/models/generator/outlines_generator.py`
- `src/models/generator/content_generator.py`
- `src/modules/preprocessor/preprocessor.py`

---

## 💡 提示

1. **首次运行**: 建议用`quick_test.py`验证环境
2. **API费用**: LLM调用会产生费用，注意控制论文数量
3. **存储空间**: 500篇论文的PDF约需5-10GB空间
4. **时间规划**: 500篇论文全流程约2-3小时

---

## 📧 问题反馈

遇到问题请：
1. 查看`output/*/pipeline.log`日志
2. 检查各步骤的输出文件
3. 参考本文档的故障排查部分

---

**祝你的CCF-A论文顺利发表！🎉**