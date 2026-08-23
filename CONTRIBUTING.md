# Contributing to SurveyGraph

Thanks for helping improve SurveyGraph. Contributions should make the research pipeline easier to inspect, reproduce, or extend.

## Before opening a pull request

1. Create a focused branch from `master`.
2. Install the base dependencies with `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` only for local work; never commit `.env` or provider credentials.
4. Run the lightweight checks:

   ```bash
   python -m compileall -q src mekg evaluation experiments tests frontend scripts
   python -m pytest -q tests/test_public_release.py
   python scripts/check_public_release.py
   python scripts/stage_public_release.py --output release_artifacts/public_release
   python scripts/check_public_release.py --root release_artifacts/public_release
   python scripts/package_public_release.py --source release_artifacts/public_release --output release_artifacts/SurveyGraph-public-release.zip
   ```

5. For changes that touch optional providers, add or update a test that runs without network access and mark live tests with `@pytest.mark.integration` or `@pytest.mark.requires_llm`.

## Pull request expectations

- Explain the motivation and affected pipeline stage.
- Include the exact validation commands and their results.
- Keep generated outputs, databases, downloaded papers, and local configuration out of commits.
- Use `scripts/audit_release_assets.py` to inventory the complete local workspace and `scripts/stage_public_release.py` to build the exact public tree.
- Do not include API keys, access tokens, private URLs, user data, or upload-session traces.
- Preserve citation and licensing information for any new third-party asset.

## Code style

Follow the existing Python layout, prefer small functions with explicit inputs, and keep configuration in environment variables or local ignored files. Add a short comment only when the behavior is not obvious from the code.
