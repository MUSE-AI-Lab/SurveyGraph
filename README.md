# SurveyGraph

Evidence-oriented academic survey generation with a multi-layer evolutionary knowledge graph (MEKG).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

SurveyGraph is the research code accompanying our EMNLP 2026 Findings work. It combines literature collection, graph construction, evidence-aware retrieval, outline planning, survey generation, reflection, and evaluation into an inspectable Python pipeline. The repository is intentionally organized for offline inspection first; online providers and the optional web frontend are separate layers.

## What is included

- **MEKG pipeline** (`mekg/`): paper collection, graph construction, evolving relations, survey planning, and generation.
- **Core modules** (`src/`): retrieval, multimodal processing, refinement, schemas, and shared configuration.
- **Evaluation** (`evaluation/`): structure, references, content, ethics, media, and HTML report generation.
- **Experiments** (`experiments/`): ablations, matched baselines, retrieval probes, and evidence audits.
- **Optional frontend** (`frontend/`): FastAPI service for task management and result browsing.
- **Tests** (`tests/`): unit tests and public-release checks that do not require an LLM or network access.

Generated databases, downloaded papers, private corpora, anonymous submission bundles, upload-session traces, and provider credentials are excluded from the public release. See [data/README.md](data/README.md).

## Quick start

### 1. Create an environment

Python 3.10-3.12 is supported. Python 3.13+ may work, but is not part of the CI matrix.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Configure providers

Copy `.env.example` to `.env` for local use and fill only the providers you need. `.env` is ignored by Git. At minimum, online generation needs `REMOTE_URL` and `TOKEN` (or `OPENAI_API_KEY`/`DASHSCOPE_API_KEY`). Offline tests do not need a provider key.

```bash
cp .env.example .env
```

The configuration loader reads environment variables and, optionally, the ignored path in `SURVEYGRAPH_EXPERIMENT_CONFIG`. Never put a real key in Python, JSON, notebooks, shell history, or an issue.

### 3. Run the public checks

```bash
python -m compileall -q src mekg evaluation experiments tests frontend scripts
python -m pytest -q tests/test_public_release.py
python scripts/check_public_release.py
```

The full test suite includes optional integrations and may require additional dependencies. Run it with `python -m pytest -q` after installing the packages needed by the modules you are changing.

## Build the exact public release

The working directory may contain private experiment inputs, downloaded papers, graph databases, paper drafts, and generated results. Those assets are preserved locally and are not silently deleted. Before publishing, generate the reviewable release tree and its two manifests:

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

`RESEARCH_ASSET_MANIFEST.tsv` inventories present and historical local assets with size and SHA-256. `public_release/RELEASE_MANIFEST.json` records the strict allowlist output. The public tree excludes the anonymous `paper/` workspace, `refer/`, databases, PDFs, archives, upload sessions, rebuttal/submission material, local configuration, and generated state. Review [docs/PUBLIC_RELEASE_BOUNDARY.md](docs/PUBLIC_RELEASE_BOUNDARY.md) before copying the staged tree to a new GitHub repository.

The package command re-scans the staged tree, writes a deterministic ZIP with the root directory `SurveyGraph-public-release/`, and emits `SurveyGraph-public-release.zip.sha256` beside it.

## Running the pipeline

The end-to-end entry point is `run_sg_endtoend.py`. It creates an ignored task directory under `outputs/` and can resume from checkpoints.

```bash
python run_sg_endtoend.py \
  --topic "retrieval augmented generation" \
  --max_papers 20 \
  --no-memgraph \
  --no-evaluation
```

For a fully configured run, remove `--no-evaluation`, set the LLM variables, and install the optional LaTeX/MinerU dependencies described in the relevant module documentation. The pipeline may call OpenAlex, arXiv, an embedding service, and an LLM provider; network and provider costs are outside this repository.

## Evaluation and experiments

The evaluation package can generate reports from an existing MEKG task output. Start with:

```bash
python evaluation/main.py --help
python experiments/run_suite.py --help
```

Experiment scripts are intentionally explicit about model names, topic lists, and output paths. Put provider-specific JSON under `experiments/configs/` with a `.local.json` suffix so it remains ignored. Record the command, model identifier, and input revision alongside any result you publish.

## Optional frontend

The FastAPI frontend is a separate service and requires a local MySQL-compatible database. Install its dependencies, set `DB_*` and `JWT_SECRET`, then run:

```bash
python -m pip install -r frontend/requirements.txt
python frontend/run.py --reload
```

The service binds to `127.0.0.1` by default. Do not expose it to the public internet without setting a strong JWT secret, restricting CORS, and configuring a dedicated database account.

## Repository map

```text
SurveyGraph/
├── src/                 Core retrieval, generation, refinement, and schemas
├── mekg/                Multi-layer evolutionary knowledge graph pipeline
├── evaluation/         Quality evaluators and report generators
├── experiments/         Reproduction and ablation scripts
├── frontend/            Optional FastAPI application
├── tests/               Unit and release-hygiene tests
├── docs/                Technical notes and design records
├── data/                Runtime/data boundary documentation
└── scripts/             Local validation helpers
```

## Artifact and licensing policy

Only source and documentation with a clear license belong in the Git repository. Downloaded papers, generated surveys, graph databases, private logs, user uploads, and third-party reference trees stay outside Git. Before adding an asset, check its license and add attribution where required.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Report credentials or security issues privately according to [SECURITY.md](SECURITY.md). The local scanner is intentionally part of the normal contributor workflow.

## Citation

Use [CITATION.cff](CITATION.cff) or cite the accompanying EMNLP 2026 Findings paper. Update the citation metadata when the camera-ready bibliographic record is available.

## License

SurveyGraph is released under the [MIT License](LICENSE). Third-party dependencies and any user-provided data remain subject to their own licenses.
