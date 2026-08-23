<div align="center">

<img src="docs/assets/surveygraph-icon.png" alt="SurveyGraph" width="112" />

# SurveyGraph

### Methods–Entity Knowledge Graphs for Academic Survey Generation and Evaluation

Evidence-oriented survey generation with graph-aware retrieval, hybrid planning, reflective writing, and multi-dimensional evaluation.

[English](README.md) · [简体中文](README_zh.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10--3.12-3776AB.svg?logo=python&logoColor=white)](requirements.txt)
[![EMNLP 2026 Findings](https://img.shields.io/badge/venue-EMNLP%202026%20Findings-6f42c1.svg)](CITATION.cff)

</div>

SurveyGraph is the research code accompanying our **EMNLP 2026 Findings** paper. It treats an academic survey as an evidence-and-structure problem rather than a single prompt: papers are collected and parsed, methods and entities are connected in a **multi-layer evolutionary knowledge graph (MEKG)**, and the graph guides outline planning, retrieval, generation, reflection, formatting, and evaluation.

The repository is organized for inspection and reproducibility. Source code, release checks, documentation, and small visual fixtures are public; downloaded corpora, databases, provider credentials, submission material, and generated private state are intentionally excluded.

## Contents

- [What SurveyGraph does](#what-surveygraph-does)
- [System overview](#system-overview)
- [Architecture](#architecture)
- [Evaluation and output examples](#evaluation-and-output-examples)
- [Repository map](#repository-map)
- [Quick start](#quick-start)
- [Run the pipeline](#run-the-pipeline)
- [Evaluation and experiments](#evaluation-and-experiments)
- [Optional frontend](#optional-frontend)
- [Public-release boundary](#public-release-boundary)
- [Citation](#citation)
- [License](#license)

## What SurveyGraph does

### Evidence-first literature modeling

- Collects and normalizes paper metadata and source material from configured providers.
- Extracts method-centered entities such as methods, models, tasks, datasets, metrics, and innovations.
- Combines structural, semantic, conceptual, temporal, and authorship relations in MEKG.
- Uses graph centrality and relation evidence to identify influential and representative papers.

### Graph-guided survey generation

- Builds a domain-aware top-down skeleton from the requested topic and keywords.
- Discovers bottom-up themes from graph communities and core papers.
- Fuses both views into a coherent outline instead of relying on a flat list of retrieved documents.
- Performs graph-aware retrieval and evidence gating for each draft section.
- Revises sections through a reflection loop that checks structure, factual support, and citation grounding.

### Inspectable evaluation

- Evaluates structure, content, references, ethics and integrity, and visual/media quality.
- Supports parallel model-based evaluators and deterministic aggregation of rubric dimensions.
- Produces machine-readable results and an HTML report for human inspection.
- Exposes release and public-hygiene checks so the research tree can be audited before publication.

## System overview

The end-to-end flow has three stages: **MEKG construction**, **graph-driven planning and generation**, and **integrated evaluation with multimodal output**.

<p align="center">
  <img src="docs/assets/surveygraph-pipeline.png" alt="SurveyGraph end-to-end pipeline: MEKG construction, graph-driven survey generation, and integrated evaluation" width="100%" />
</p>

The pipeline is deliberately modular. Provider calls, graph storage, the optional frontend, and rendering dependencies can be enabled independently; offline checks do not require an LLM key or network access.

## Architecture

The compact architecture view below highlights the four operational stages: knowledge-graph construction, hybrid outline planning, reflective generation, and post-processing.

<p align="center">
  <img src="docs/assets/surveygraph-architecture.png" alt="SurveyGraph four-stage architecture" width="820" />
</p>

| Stage | Main responsibility | Public implementation area |
| --- | --- | --- |
| MEKG construction | Parse papers, extract entities, discover relations, and score graph nodes | `mekg/`, `src/` |
| Hybrid planning | Combine a topic skeleton with graph-emergent communities | `mekg/`, `src/` |
| Reflective generation | Retrieve evidence, draft sections, and refine against rubric feedback | `src/`, `evaluation/` |
| Post-processing | Render figures/tables, apply templates, and assemble deliverables | `src/`, `evaluation/` |

## Evaluation and output examples

The repository includes small, static visual fixtures so that the public README communicates the actual product surface without publishing private corpora or databases.

### Generated survey preview

<p align="center">
  <img src="docs/assets/generated-survey-preview.png" alt="A generated academic survey page produced by SurveyGraph" width="760" />
</p>

This is a rendered first page from a generated survey fixture. It illustrates the expected output format: a structured title and abstract, section hierarchy, citations, and a publication-style layout. The image is a display fixture, not a benchmark claim.

### Evaluation report

<p align="center">
  <img src="docs/assets/evaluation-report.png" alt="SurveyGraph evaluation report showing a multidimensional quality score" width="820" />
</p>

The included report snapshot shows the HTML evaluation surface and a **85.6/100** aggregate score for that fixture. Scores depend on the input corpus, provider configuration, evaluator models, and rubric version; they should not be interpreted as a universal system score.

## Repository map

```text
SurveyGraph/
├── src/                 Retrieval, generation, refinement, schemas, and shared config
├── mekg/                Multi-layer evolutionary knowledge-graph pipeline
├── evaluation/          Quality evaluators and HTML report generation
├── experiments/         Ablations, matched baselines, probes, and evidence audits
├── frontend/            Optional FastAPI task-management and result-browsing service
├── tests/               Unit tests and public-release checks
├── docs/                Technical notes, design records, and README assets
├── resources/           Public prompts, templates, and lightweight static resources
└── scripts/             Release staging, packaging, and validation helpers
```

Further design notes are indexed in [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md) and [`docs/mekg/README_MEKG.md`](docs/mekg/README_MEKG.md).

## Quick start

### 1. Create an environment

Python **3.10–3.12** is supported. Python 3.13 may work, but it is not part of the CI matrix.

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Configure providers only when needed

Copy `.env.example` to an ignored local `.env` file and fill only the providers required by your run:

```bash
cp .env.example .env
```

Online generation typically needs `REMOTE_URL` and `TOKEN`, or a provider-specific key such as `OPENAI_API_KEY` or `DASHSCOPE_API_KEY`. Public tests and static inspection do not require credentials. Never commit a real key to source, JSON, notebooks, shell history, or an issue.

### 3. Run public checks

```bash
python -m compileall -q src mekg evaluation experiments tests frontend scripts
python -m pytest -q tests/test_public_release.py
python scripts/check_public_release.py
```

The full test suite includes optional integrations and may require additional services or dependencies. Run it with `python -m pytest -q` after installing what the modules under change require.

## Run the pipeline

The end-to-end entry point creates an ignored task directory under `outputs/` and can resume from checkpoints:

```bash
python run_sg_endtoend.py \
  --topic "retrieval augmented generation" \
  --max_papers 20 \
  --no-memgraph \
  --no-evaluation
```

For a fully configured run, remove `--no-evaluation`, configure the LLM variables, and install optional LaTeX/MinerU dependencies described by the relevant module documentation. Depending on configuration, the pipeline may call OpenAlex, arXiv, an embedding service, and an LLM provider; network access and provider costs are outside this repository.

## Evaluation and experiments

To inspect available commands:

```bash
python evaluation/main.py --help
python experiments/run_suite.py --help
```

Experiment scripts keep model names, topic lists, and output paths explicit. Put provider-specific configuration under `experiments/configs/` with a `.local.json` suffix so it remains ignored. Record the command, model identifier, input revision, and rubric version alongside any result you publish.

## Optional frontend

The FastAPI frontend is a separate service for task management and result browsing. It requires a local MySQL-compatible database:

```bash
python -m pip install -r frontend/requirements.txt
python frontend/run.py --reload
```

The service binds to `127.0.0.1` by default. Before any shared deployment, set a strong `JWT_SECRET`, restrict CORS, and use a dedicated database account.

## Public-release boundary

The public tree is a curated source release, not a copy of the private research workspace. The release process intentionally excludes:

- downloaded papers, private corpora, generated databases, and archives;
- anonymous submission, review, rebuttal, and upload-session material;
- provider credentials, local `.env` files, and machine-specific state;
- private experiment outputs that cannot be redistributed with a clear license.

To build and audit the exact release locally:

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

Read [`docs/PUBLIC_RELEASE_BOUNDARY.md`](docs/PUBLIC_RELEASE_BOUNDARY.md) before adding a new artifact. Check the license and add attribution for every third-party asset.

## Citation

Please cite the accompanying EMNLP 2026 Findings paper when you use SurveyGraph. The machine-readable record is maintained in [`CITATION.cff`](CITATION.cff); bibliographic fields will be updated when the camera-ready record is available.

```bibtex
@software{surveygraph2026,
  title  = {SurveyGraph: Methods-Entity Knowledge Graphs for Academic Survey Generation and Evaluation},
  year   = {2026},
  note   = {Research software accompanying an EMNLP 2026 Findings paper},
  url    = {https://github.com/xzzvsxd/SurveyGraph-open-source}
}
```

## License

SurveyGraph is released under the [MIT License](LICENSE). Third-party dependencies, provider services, and user-supplied data remain subject to their own licenses and terms.
