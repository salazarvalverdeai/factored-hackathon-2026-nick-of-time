# 0001. Record decisions as ADRs and build features from specs

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Freddy, GianMarco, Diego · **Owner:** @salazarvalverdeai
- **Related:** [`CONTRIBUTING.md`](../../CONTRIBUTING.md)

## Context
Three senior engineers build in parallel with AI assistants under a fixed deadline (2026-10-05). The challenge
rewards deliberate, defensible technical choices and good engineering practice (feature branches, small merges, clear
commits, tagged versions). Until now, decisions lived in slide decks and chat threads that neither the judges nor the
AI agents can read.

## Decision
Adopt spec-driven development for every new feature (one spec per feature in `specs/`, EARS acceptance criteria, a
test per criterion) and record every load-bearing decision as an ADR in `docs/adr/`, one file per decision. Decisions
taken on 2026-09-28 and 2026-09-29 are back-filled with their original dates. The existing data pipeline is not
re-specified. Git flow, approvals and versioning follow `CONTRIBUTING.md`.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Specs + ADRs in the repo (chosen) | Readable by judges and AI agents; reviewed through PRs; history in git | ~10 minutes per spec or decision |
| Decisions in slides and chat | No overhead | Invisible to the judges and to agents; not reviewable |
| Full Spec Kit / OpenSpec tooling | Rich workflow | Tooling overhead for a 2-day sprint |

## Consequences
Every PR can cite the spec criteria and ADRs it implements; the README and slides reuse the trade-off tables. Writing
specs costs time up front and saves rework from agents guessing.

## Confidence
High. Revisit only if the process slows the critical path; then reduce specs to the minimal profile.
