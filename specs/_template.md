# Spec NN — [Feature name]

- **Feature:** [one line]
- **Status:** Draft | Approved | In progress | Implemented | Superseded (→ spec NN)
- **Owner:** [@github-user] · **Priority:** P0 | P1 | P2 · **Size:** S | M | L
- **Challenge dimension:** Technical Judgment | AI Engineering | Data Engineering | Machine Learning | Data Analytics
- **Depends on:** [specs] · **Enables:** [specs] · **ADRs:** [NNNN]
- **Issue:** #N

> **Profile.** Minimal (default): sections 1, 3, 6 (only if there is an API), 9 and 10 — delete the rest.
> Full (delicate logic): all ten sections.
> **Anti spec-drift.** If this feature's code changes later, update this spec in the same PR or mark it Superseded.

---

## 1. Introduction
[What the feature is and the value it delivers. Two or three lines.]

## 2. User stories
- As a [role], I want [capability], so that [benefit].

## 3. Acceptance criteria (EARS)
Copy the issue's criteria with the same numbers; add more if needed, never drop or weaken one without the lead.
Each criterion needs at least one test or check that cites it by ID. Evidence: [T] test · [C] command · [U] screenshot
or video on the public URL · [D] file.

- AC-01 — When [trigger], the system shall [response]. · [T]
- AC-02 — While [state], the system shall [response]. · [T]
- AC-03 — If [unwanted trigger], then the system shall [response]. · [T]
- AC-04 — The system shall [ubiquitous requirement]. · [C]

## 4. Functional requirements
- FR-01 — [what it must do]

## 5. Non-functional requirements
- Performance: [budget, e.g. p95]
- Security: [auth, validation, secrets]
- Observability: [events, logs, traces]

## 6. API contract (I/O)
The OpenAPI document is generated from the code (FastAPI/Pydantic); this table is the agreed contract.

| Method | Path | Request | Response | Status codes |
|---|---|---|---|---|
| POST | /api/… | {fields} | {fields} | 201 / 400 / 409 |

## 7. Data model touched
[Tables or fields this feature reads or creates.]

## 8. Assumptions and open questions
- Assumption: [what is assumed; label it `[assumption]`].
- Open question: [what is still undefined]. The agent must not invent it; close it before approval (gate 1).

## 9. Out of scope
- [What this feature does not do.]

## 10. Plan, tasks and verification
- [ ] Task 1 — goal · covers FR-01, AC-01 · done when: [test or check]
- [ ] Task 2 — goal · covers AC-02 · done when: [test or check]

**Closing checklist** (last PR): every AC has a passing test or check that cites it · status → Implemented · ADR for
any decision taken · lessons added to `CLAUDE.md`.
