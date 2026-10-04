# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Spec-driven process: `CLAUDE.md`, `CONTRIBUTING.md`, `specs/` with template and index, `docs/adr/` with template and
  18 ADRs back-filling the decisions of 2026-09-28, 2026-09-29 and 2026-10-03.
- GitHub workflow: pull request and commit templates, issue templates, `CODEOWNERS`, CI (pytest, web lint + build,
  secret scan).
- `docs/infrastructure.md`, `STATUS.md` and the option A architecture diagram.
- Deploy path (spec 06): `infra/compose.yml`, Caddy config, `infra/deploy.sh` with pull-first and rollback,
  `infra/backup.sh` (daily Postgres dump to S3), `.github/workflows/deploy.yml` (GHCR → OIDC → SSM), web production
  image, placeholder `api` (`/api/health`) and `mcp` images, and `tests/test_spec06_deploy.py`.

### Removed
- Per-person Spanish guides in `docs/team/`, superseded by specs and issues.

## [0.1.0] - 2026-10-01
### Added
- Bronze → silver → gold pipeline on DuckDB with pandera contracts, gold rules G1–G5, manifest and late-arrival fixture.
- Contracts: `policies.yaml`, `tools.py`, `handoff.schema.json`, `eval_case.schema.json`, `gold_contract.md`.
- EDA records, pitch queries with their outputs, and architecture diagrams.
- Next.js 16 + shadcn/ui web scaffold with page shells.

[Unreleased]: https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/releases/tag/v0.1.0
