<div align="center">

<img src="docs/assets/surveygraph-icon.png" alt="SurveyGraph" width="112" />

# SurveyGraph

### 面向学术综述生成与评测的方法-实体知识图谱

以证据为中心的综述生成：图感知检索、混合式规划、反思式写作与多维度评测。

[English](README.md) · [简体中文](README_zh.md)

[![许可证：MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10--3.12-3776AB.svg?logo=python&logoColor=white)](requirements.txt)
[![EMNLP 2026 Findings](https://img.shields.io/badge/venue-EMNLP%202026%20Findings-6f42c1.svg)](CITATION.cff)

</div>

SurveyGraph 是我们 **EMNLP 2026 Findings** 论文配套的研究代码。它将学术综述视为一个“证据与结构”问题，而不是一次性提示词任务：系统先采集并解析论文，再围绕方法与实体构建**多层演化知识图谱（MEKG）**，最后由图谱共同驱动大纲规划、证据检索、综述生成、反思修订、排版和评测。

仓库按“可检查、可复现”的原则组织。公开内容包括源代码、发布检查、技术文档和少量展示素材；下载语料、数据库、服务凭据、投稿材料以及本地生成状态均被有意排除。

## 目录

- [SurveyGraph 能做什么](#surveygraph-能做什么)
- [系统概览](#系统概览)
- [系统架构](#系统架构)
- [评测与输出示例](#评测与输出示例)
- [仓库结构](#仓库结构)
- [快速开始](#快速开始)
- [运行完整流水线](#运行完整流水线)
- [评测与实验](#评测与实验)
- [可选前端](#可选前端)
- [公开发布边界](#公开发布边界)
- [引用](#引用)
- [许可证](#许可证)

## SurveyGraph 能做什么

### 以证据为中心的文献建模

- 从配置的数据源采集并规范化论文元数据与源材料。
- 抽取方法、模型、任务、数据集、指标和创新点等方法中心实体。
- 在 MEKG 中统一组织结构、语义、概念、时间和作者关系。
- 结合图中心性与关系证据识别具有影响力且具代表性的论文。

### 图谱驱动的综述生成

- 根据主题与关键词构建领域感知的自顶向下骨架。
- 从图社区和核心论文中发现自底向上的主题结构。
- 融合两种视角形成连贯大纲，而不是依赖扁平的检索文档列表。
- 为每个草稿章节执行图感知检索和证据门控。
- 通过反思循环检查结构、事实支撑与引用锚定，并据此修订章节。

### 可检查的多维评测

- 覆盖结构、内容、参考文献、伦理与完整性、视觉/媒体质量等维度。
- 支持并行的模型评测器，并对各项 rubric 指标进行确定性聚合。
- 同时生成机器可读结果和便于人工检查的 HTML 报告。
- 提供发布边界扫描和公开卫生检查，便于在开源前审计研究树。

## 系统概览

端到端流程分为三个阶段：**MEKG 构建**、**图驱动规划与生成**、**集成评测与多模态输出**。

<p align="center">
  <img src="docs/assets/surveygraph-pipeline.png" alt="SurveyGraph 端到端流水线：MEKG 构建、图驱动综述生成与集成评测" width="100%" />
</p>

流水线保持模块化设计。数据源调用、图存储、可选前端和渲染依赖可以独立启用；离线检查不需要 LLM 密钥或网络访问。

## 系统架构

下面的紧凑架构图展示四个运行阶段：知识图谱构建、混合式大纲规划、反思式生成和后处理。

<p align="center">
  <img src="docs/assets/surveygraph-architecture.png" alt="SurveyGraph 四阶段系统架构" width="820" />
</p>

| 阶段 | 主要职责 | 公开实现目录 |
| --- | --- | --- |
| MEKG 构建 | 解析论文、抽取实体、发现关系并计算图节点得分 | `mekg/`、`src/` |
| 混合式规划 | 融合主题骨架与图谱涌现的社区结构 | `mekg/`、`src/` |
| 反思式生成 | 检索证据、撰写章节，并依据 rubric 反馈迭代 | `src/`、`evaluation/` |
| 后处理 | 生成图表、应用模板并组装交付物 | `src/`、`evaluation/` |

## 评测与输出示例

仓库包含少量静态展示素材，使 README 能够呈现实际产品界面，同时不公开私有语料或数据库。

### 生成综述预览

<p align="center">
  <img src="docs/assets/generated-survey-preview.png" alt="SurveyGraph 生成的学术综述页面" width="760" />
</p>

这是一个生成综述样例的第一页渲染图，展示了系统预期的输出形式：结构化标题与摘要、章节层级、引用以及出版物风格的排版。该图片是展示用 fixture，不代表基准结果声明。

### 评测报告

<p align="center">
  <img src="docs/assets/evaluation-report.png" alt="SurveyGraph 多维质量评测报告" width="820" />
</p>

随仓库提供的报告截图展示了 HTML 评测界面，以及该 fixture 的 **85.6/100** 综合得分。分数会随输入语料、服务配置、评测模型和 rubric 版本变化，不应被解读为系统的统一固定分数。

## 仓库结构

```text
SurveyGraph/
├── src/                 检索、生成、反思、数据结构与共享配置
├── mekg/                多层演化知识图谱流水线
├── evaluation/          质量评测器与 HTML 报告生成
├── experiments/         消融、匹配基线、检索探针与证据审计
├── frontend/            可选的 FastAPI 任务管理与结果浏览服务
├── tests/               单元测试与公开发布检查
├── docs/                技术说明、设计记录与 README 素材
├── resources/           公开提示词、模板和轻量静态资源
└── scripts/             发布暂存、打包与验证脚本
```

更详细的设计索引见 [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) 与 [`docs/mekg/README_MEKG.md`](docs/mekg/README_MEKG.md)。

## 快速开始

### 1. 创建环境

支持 Python **3.10–3.12**。Python 3.13 可能可以运行，但不属于 CI 测试矩阵。

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. 仅在需要时配置服务

将 `.env.example` 复制为本地、且被 Git 忽略的 `.env` 文件，只填写本次运行需要的服务：

```bash
cp .env.example .env
```

在线生成通常需要 `REMOTE_URL` 与 `TOKEN`，或者配置 `OPENAI_API_KEY`、`DASHSCOPE_API_KEY` 等服务商密钥。公开测试和静态检查不需要凭据。请勿将真实密钥写入源代码、JSON、笔记本、Shell 历史或 Issue。

### 3. 运行公开检查

```bash
python -m compileall -q src mekg evaluation experiments tests frontend scripts
python -m pytest -q tests/test_public_release.py
python scripts/check_public_release.py
```

完整测试套件包含可选集成，可能需要额外服务或依赖。修改具体模块后，请先安装该模块所需依赖，再运行 `python -m pytest -q`。

## 运行完整流水线

端到端入口会在 `outputs/` 下创建被忽略的任务目录，并支持从检查点恢复：

```bash
python run_sg_endtoend.py \
  --topic "retrieval augmented generation" \
  --max_papers 20 \
  --no-memgraph \
  --no-evaluation
```

如需完整运行，请移除 `--no-evaluation`、配置 LLM 变量，并按相关模块文档安装可选的 LaTeX/MinerU 依赖。根据配置，流水线可能调用 OpenAlex、arXiv、嵌入服务和 LLM 服务；网络访问与服务商费用不属于本仓库的一部分。

## 评测与实验

查看可用命令：

```bash
python evaluation/main.py --help
python experiments/run_suite.py --help
```

实验脚本明确记录模型名称、主题列表和输出路径。服务商专用配置请放在 `experiments/configs/` 下，并使用 `.local.json` 后缀以保持忽略。发布实验结果时，请同时记录命令、模型标识、输入版本和 rubric 版本。

## 可选前端

FastAPI 前端是独立服务，用于任务管理和结果浏览，需要本地兼容 MySQL 的数据库：

```bash
python -m pip install -r frontend/requirements.txt
python frontend/run.py --reload
```

服务默认绑定 `127.0.0.1`。在共享部署前，请设置高强度 `JWT_SECRET`、限制 CORS，并使用专用数据库账号。

## 公开发布边界

公开仓库是经过筛选的源码发布版，不是私有研究工作区的完整复制。发布流程明确排除：

- 下载论文、私有语料、生成数据库和归档文件；
- 匿名投稿、审稿、rebuttal 与上传会话材料；
- 服务凭据、本地 `.env` 文件和机器相关状态；
- 没有明确再分发许可的私有实验输出。

如需在本地构建并审计完全一致的发布树：

```bash
python scripts/audit_release_assets.py \
  --output release_artifacts/RESEARCH_ASSET_MANIFEST.tsv
python scripts/stage_public_release.py \
  --output release_artifacts/public_release
python scripts/check_public_release.py \
  --root release_artifacts/public_release
python scripts/package_public_release.py \
  --source release_artifacts/public_release \
  --output release_artifacts/SurveyGraph-public-release.zip
```

新增素材前请阅读 [`docs/PUBLIC_RELEASE_BOUNDARY.md`](docs/PUBLIC_RELEASE_BOUNDARY.md)，并核对第三方素材的许可证与署名要求。

## 引用

如果 SurveyGraph 对你的研究有帮助，请引用配套的 EMNLP 2026 Findings 论文。机器可读记录维护在 [`CITATION.cff`](CITATION.cff)；论文 camera-ready 书目信息确定后会同步更新。

```bibtex
@software{surveygraph2026,
  title  = {SurveyGraph: Methods-Entity Knowledge Graphs for Academic Survey Generation and Evaluation},
  year   = {2026},
  note   = {Research software accompanying an EMNLP 2026 Findings paper},
  url    = {https://github.com/xzzvsxd/SurveyGraph-open-source}
}
```

## 许可证

SurveyGraph 采用 [MIT License](LICENSE) 发布。第三方依赖、服务商服务和用户提供的数据仍受其各自许可证与服务条款约束。
