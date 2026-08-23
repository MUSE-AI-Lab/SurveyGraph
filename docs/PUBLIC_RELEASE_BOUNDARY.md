# Public Release Boundary

This document defines the difference between the complete local research workspace and the GitHub release. The boundary is deliberate: no research source file is deleted merely because it is not suitable for a public repository.

## Public release

The staging script includes source code, tests, evaluation logic, experiment drivers, technical documentation, configuration templates, governance files, and small public assets from:

- `src/`
- `mekg/`
- `evaluation/`
- `experiments/`
- `tasks/`
- `frontend/`
- `tests/`
- `docs/` (excluding private upload/session material and generated binaries)
- `resources/`
- the explicitly approved root files listed in `scripts/stage_public_release.py`

## Preserved locally, excluded from GitHub

The following files remain available in the local workspace and are recorded in `release_artifacts/RESEARCH_ASSET_MANIFEST.tsv`, but are excluded from the public staging tree:

- downloaded papers, figures, PDFs, ZIP archives, and generated LaTeX output;
- `refer/` third-party/reference repositories and corpora;
- graph databases under `data/graph_db/`;
- `paper/openreview_*` supplementary bundles and generated result archives;
- `output/`, `outputs/`, `tmp/`, caches, logs, and IDE/virtual-environment state;
- local experiment configuration such as `experiments/configs/*.local.*`;
- internal submission checklists, CFP snapshots, and transient experiment TODO sheets.

These are exclusions from publication, not deletion. The manifest records existence, byte size, and SHA-256 for every present asset that is excluded.

## Removed from the working tree

OpenReview/S3 presigned fields, upload-session responses, and submission helper files that contained credentials or session material were removed from the working tree. Their filenames and baseline commit are recorded in `release_artifacts/PRIVATE_FILE_REMOVAL_MANIFEST.md`; their contents remain recoverable only from the pre-release Git history after credential rotation.

## Reproduce the release tree

From the repository root:

```bash
python scripts/audit_release_assets.py --output release_artifacts/RESEARCH_ASSET_MANIFEST.tsv
python scripts/stage_public_release.py --output release_artifacts/public_release
python scripts/check_public_release.py --root release_artifacts/public_release
python scripts/package_public_release.py --source release_artifacts/public_release --output release_artifacts/SurveyGraph-public-release.zip
```

The staging tree is the object to review, archive, and publish. The package command re-scans it and creates a deterministic ZIP plus a SHA-256 sidecar. It is generated from Git's current candidate set plus the explicit allowlist, so ignored/generated/private assets remain out. The audit manifest walks the filesystem separately, including ignored research assets, and is the record that local material was preserved rather than discarded.
