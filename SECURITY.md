# Security Policy

## Supported versions

Security fixes are applied to the latest commit on `master`. This repository is research software and is not a hosted production service.

## Reporting a vulnerability

Please do not open a public issue for credentials, personal data, authentication bypasses, or exploitable code. Contact the maintainers privately through the security contact configured on the GitHub repository and include:

- affected file and commit;
- reproducible steps or a minimal proof of concept;
- impact and any required configuration;
- a suggested remediation, if available.

If a credential may have been committed, revoke or rotate it immediately and then report the commit hash. Removing a file in a later commit does not remove it from Git history.

## Safe handling rules

- Keep `.env`, `*.local.*`, databases, downloaded papers, generated outputs, and upload traces outside commits.
- Use least-privilege provider tokens and separate research credentials from production accounts.
- Set a strong `JWT_SECRET` before running the optional frontend outside local development.
