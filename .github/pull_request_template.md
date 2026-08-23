## What changed?

<!-- Describe the user-visible or research-visible change. -->

## Validation

- [ ] `python -m compileall -q src mekg evaluation experiments tests frontend scripts`
- [ ] `python -m pytest -q tests/test_public_release.py`
- [ ] `python scripts/check_public_release.py`
- [ ] `python scripts/stage_public_release.py --output release_artifacts/public_release`
- [ ] `python scripts/check_public_release.py --root release_artifacts/public_release`
- [ ] `python scripts/package_public_release.py --source release_artifacts/public_release --output release_artifacts/SurveyGraph-public-release.zip`
- [ ] Additional checks (list them below)

## Release hygiene

- [ ] No `.env`, `*.local.*`, database, downloaded paper, generated output, upload trace, or provider credential is included.
- [ ] New third-party assets have a compatible license and attribution.
- [ ] Documentation explains any new environment variable or external service.
