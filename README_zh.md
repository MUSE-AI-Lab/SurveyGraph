<div align="center">

<img src="docs/assets/surveygraph-icon.png" alt="SurveyGraph" width="96">

# SurveyGraph: Generating Academic Surveys via Methods-Entity Knowledge Graphs

**Yifan Yuan** · **Yancheng Zhu** · **Zuoyu Zhang** · **Xiaogang Peng**<sup>&dagger;</sup>

深圳大学人工智能学院
<br>
<sup>&dagger;</sup>通讯作者

**EMNLP 2026 Findings**

<a href="https://arxiv.org/abs/2610.31317"><img src="https://img.shields.io/badge/arXiv-2610.31317-b31b1b" alt="arXiv"></a>
<a href="requirements.txt"><img src="https://img.shields.io/badge/Python-3.10--3.12-3776ab?logo=python&logoColor=white" alt="Python"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-lightgrey" alt="License"></a>

[English](README.md) · [简体中文](README_zh.md)

</div>

<p align="center"><img src="docs/assets/surveygraph-pipeline.png" width="100%"><br><em>SurveyGraph：MEKG 构建、图驱动的综述生成与一体化评测。</em></p>

**一句话总结：** 现有的大模型综述生成大多把论文当作一堆彼此独立的文档来检索，写出来的综述像是摘要拼贴。好的综述要讲清一个领域是怎么演化的：哪项工作延续了哪项，哪些方法相互竞争，哪些基准是转折点。**SurveyGraph** 构建**方法—实体知识图谱（MEKG）**，记录方法之间的*延续*、*竞争*和*共享资源*关系，并以它为骨架完成核心论文发现、图感知检索、混合式大纲生成，以及有证据门控、体现演化脉络的写作。图感知检索的召回率**接近平面词法检索基线的两倍**（p = 0.004）；引用核查显示，**80.6%** 的生成句子能在所引文献中找到完全或部分支撑。

## 🔍 方法

<p align="center"><img src="docs/assets/surveygraph-architecture.png" width="80%"></p>

| 阶段 | 内容 | 代码 |
|:-|:-|:-|
| **MEKG 构建** | 采集并解析论文（OpenAlex、arXiv、上传的 PDF）；抽取方法、模型、任务、数据集和评价指标；推断带类型的关系（*extends*、*improves*、*applies*、竞争、共享资源），并用语义证据门过滤；按图中心性排序核心论文 | `mekg/`、`src/` |
| **混合式大纲规划** | 把自上而下的主题骨架与自下而上的图社区主题、核心论文融合，再由大纲评审循环修订 | `mekg/`、`src/` |
| **反思式生成** | 逐节进行图感知检索和证据门控，生成体现演化脉络的叙述，并通过反思循环检查结构、事实支撑和引用依据 | `src/` |
| **后处理与评测** | 生成图表并组装 LaTeX/PDF；从结构、内容、参考文献、伦理与学术诚信、视觉质量等维度评测，输出 HTML 报告 | `src/`、`evaluation/` |

## 🛠️ 安装

```bash
git clone https://github.com/MUSE-AI-Lab/SurveyGraph.git
cd SurveyGraph
python -m venv .venv && source .venv/bin/activate      # Windows：.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

已测试 Python 3.10–3.12。可选组件按需启用：图数据库 [Memgraph](https://memgraph.com/)、生成 PDF 用的 LaTeX、解析 PDF 用的 MinerU，以及网页前端需要的 MySQL。

**模型服务配置。** 把 `.env.example` 复制为 `.env`（已被 git 忽略），只填写本次运行需要的项：`REMOTE_URL` + `TOKEN`，或 `OPENAI_API_KEY` / `DASHSCOPE_API_KEY` 等服务密钥；需要时再填嵌入服务（`EMBED_*`）和 `OPENALEX_EMAIL`。离线测试不需要任何凭据。

## 🚀 快速开始

为一个主题生成综述（论文自动采集）：

```bash
python tasks/mekg_run.py --topic "Retrieval-Augmented Generation" --max_papers 30 \
    --year_start 2022 --year_end 2024 --no-memgraph --no-evaluation
```

所有中间结果都保存在 `outputs/<task_id>/` 下（`mekg/`、`papers/`、`latex/`、`logs/`、`task_config.json`），中断后可以续跑：

```bash
python tasks/mekg_run.py --list-tasks
python tasks/mekg_run.py --resume --task_id <task_id>
```

常用开关：`--uploaded-files '["a.pdf", "b.pdf"]'` 配合 `--no-arxiv` 只用自己的论文写作；`--no-reflection` / `--no-hybrid-outline` / `--no-global-reflector` 用于消融；去掉 `--no-evaluation` 会在最后自动评测。全部参数见 `python tasks/mekg_run.py --help`。

## 📊 评测

```bash
python evaluation/main.py --help         # 质量评测与 HTML 报告
python experiments/run_suite.py --help   # 消融、匹配基线、探针与证据审计
```

**七种方法的等预算检索基准**（top-5，论文表 2）。R@5 / P@5：召回率与精确率；Str.：章节—证据对齐；Den.：带类型关系密度；CoCit：用 OpenAlex 计算的共被引连通度，与 MEKG 无关。

| 方法 | R@5 | P@5 | Str. | Den. | CoCit |
|:-|:-:|:-:|:-:|:-:|:-:|
| Flat lexical | .252 | .132 | **.558** | .134 | .089 |
| Bibliographic RRF | .309 | .194 | .530 | .132 | .142 |
| TF-IDF GraphRAG | .347 | .176 | .485 | .140 | .118 |
| MEKG typed | .153 | .089 | .392 | **.228** | .156 |
| Safe fusion | .261 | .134 | .528 | .179 | .147 |
| Biblio + TF-IDF | **.357** | **.200** | .498 | .134 | .131 |
| Biblio + MEKG | .304 | .178 | .486 | .174 | **.163** |

不用图的方法原始召回更高，但几乎没有带类型的结构；接入 MEKG 的融合方法在保持有竞争力召回的同时，关系密度和共被引连通度接近翻倍。其他结果：在图原生核心诊断上，图感知检索的召回接近平面词法基线的两倍（p = 0.004）；语义证据门 AUC = 0.75；对 160 个生成句子的引用核查中，80.6% 有锚定或部分支撑；对 108 条语义边的人工验证中，68.5% 被判为支持或部分支持（Cohen's κ = 0.64）。

<table>
<tr>
<td width="45%"><img src="docs/assets/generated-survey-preview.png"><p align="center"><em>生成综述的首页</em></p></td>
<td width="55%"><img src="docs/assets/evaluation-report.png"><p align="center"><em>HTML 评测报告</em></p></td>
</tr>
</table>

分数取决于语料、模型服务和评测模型；图片仅为展示样例，不代表基准结论。

## 🖥️ 网页前端（可选）

用于任务管理和结果浏览的 FastAPI 服务（需要兼容 MySQL 的数据库）：

```bash
pip install -r frontend/requirements.txt
python frontend/run.py --reload          # 默认只监听 127.0.0.1；对外开放前先设置 JWT_SECRET 和 CORS
```

## 📁 仓库结构

```text
tasks/mekg_run.py   # 端到端入口（采集 → MEKG → 大纲 → 写作 → LaTeX → 评测）
mekg/               # 方法—实体知识图谱流水线
src/                # 检索、生成、修订、数据结构与共享配置
evaluation/         # 质量评测与 HTML 报告
experiments/        # 消融、匹配基线、探针与证据审计
frontend/           # 可选的 FastAPI 服务
resources/          # 提示词、模板与静态资源
tests/              # 单元测试与公开发布检查
docs/               # 设计文档与配图
scripts/            # 发布打包与校验脚本
```

下载的论文、语料、生成的数据库和服务凭据都不在仓库中；`python -m pytest -q tests/test_public_release.py` 和 `python scripts/check_public_release.py` 用于审计公开内容（需要 `git` 在 `PATH` 中）。详见 [`docs/PUBLIC_RELEASE_BOUNDARY.md`](docs/PUBLIC_RELEASE_BOUNDARY.md)。

## 📝 引用

```bibtex
@inproceedings{yuan2026surveygraph,
  title     = {{SurveyGraph}: Generating Academic Surveys via Methods-Entity Knowledge Graphs},
  author    = {Yuan, Yifan and Zhu, Yancheng and Zhang, Zuoyu and Peng, Xiaogang},
  booktitle = {Findings of the Association for Computational Linguistics: EMNLP 2026},
  year      = {2026},
  eprint    = {2610.31317},
  archivePrefix = {arXiv}
}
```

## 📄 许可证

[MIT](LICENSE)。第三方依赖、模型服务和用户提供的数据仍受各自的许可与条款约束。
