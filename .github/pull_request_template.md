<!-- Title must be a Conventional Commit, e.g. "feat(policy): compute MX debit credit deadline" (it becomes the commit on main). -->

## Summary
<!-- 2–4 sentences: what this PR does and why it matters to the customer, the analyst or the judges. -->

**Spec:** specs/NN-slug.md · **Issue:** Closes #N · **ADRs:** NNNN
**Kind:** spec PR | implementation PR | fix | docs | chore

## Acceptance criteria covered
<!-- One line per criterion with its evidence: [T] test name · [C] command + output · [U] screenshot/video · [D] file. -->
- [ ] AC-01 — [T] `tests/test_specNN_…::test_ac_01_…`
- [ ] AC-02 — [C] `curl …` → output below

## What changed
- added …
- updated …

## API surface
<!-- New or changed endpoints, MCP tools, events or schemas. Write "none" if none. -->

## Config
<!-- New or changed environment variables or SSM parameters (names only, never values). -->

## Testing
- Unit / integration: `make test` → result
- Manual / URL: steps and result
- Docs updated: files

## Screenshots
<!-- Required for UI changes. -->

## Risks and rollback
- Risk:
- Rollback:

## AI assistance
<!-- Tool and what it was used for, e.g. "Claude Code — drafted the store module and its tests; reviewed line by line." -->

## Checklist
- [ ] Title is a Conventional Commit; branch follows `spec/` `feat/` `fix/` `docs/` `chore/` `ci/`
- [ ] Every criterion above has its evidence; CI is green
- [ ] Spec updated in this PR if the behavior changed (no spec drift)
- [ ] ADR added for any load-bearing decision
- [ ] No secrets, no `.env`, no dataset files
- [ ] **Closing PR of a spec:** status → Implemented · all ACs have passing tests · lessons added to `CLAUDE.md`
