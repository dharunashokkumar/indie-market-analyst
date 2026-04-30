# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Instead, email **dharuna457@gmail.com** with:

- A description of the issue and its impact.
- Steps to reproduce (minimal repro preferred).
- Your name or handle for acknowledgement (optional).

You should receive an acknowledgement within 72 hours. Once a fix is prepared, the issue will be disclosed publicly alongside the patched release.

## Scope

This project is local-first market-analysis tooling. It ships with no authentication and is intended for trusted single-user use unless the operator adds deployment controls. Public or shared deployments are the operator's responsibility.

Credentials and private runtime settings, including `OPENROUTER_API_KEY` and NSE cookies, must be kept out of the repository. `.env` is gitignored; only `.env.example` is tracked.



