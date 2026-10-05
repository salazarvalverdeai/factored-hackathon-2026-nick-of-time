# Changelog draft (for the lead's review)

Draft of the `[Unreleased]` section of `CHANGELOG.md`, which has not been updated since the deploy path entry
(`CHANGELOG.md`, 2026-10-03). It lists the 118 pull requests merged into `main` with `mergedAt` on 2026-10-05 (UTC), up
to `origin/main` at `5636caa`, taken from `gh pr list --state merged --limit 300` on 2026-10-05 and grouped by area from
each Conventional Commit scope. Every entry links its PR and the merge commit on `main`. Milestones: `v0.2.0` is tagged
(`dcca724`); `v0.3.0` is reported reached by the lead but no tag exists in `origin` yet (`git ls-remote --tags origin`,
2026-10-05).

## [Unreleased] - 2026-10-05

### Agent graph
- feat: add the echo graph dispute_intake and a minimal langgraph.json ([#62](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/62), `9523e31`)
- feat: add the dispute_intake skeleton with greet, understand, route ([#88](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/88), `e334ec8`)
- feat: add retrieve, decide, plan and clarify nodes (spec 04 T3) ([#96](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/96), `036d707`)
- feat: add status re-reads and call requests on the active case ([#104](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/104), `7396c1b`)
- feat: add act and verify with retries and the unconfirmed path ([#105](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/105), `650cd16`)
- feat: add respond with receipt, handoff, grounding and chips ([#109](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/109), `c61d121`)
- fix: pin fastapi and opentelemetry-api so the Platform agent server starts ([#110](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/110), `65ee820`)
- fix: receipt chip, D-051 verify times and no_cards read_at (task 04d2) ([#131](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/131), `c815d05`)
- feat: S1/S2 understand with usage, budget and S0 fallback (spec 04 T7) ([#133](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/133), `e1147b7`)
- feat: serve the real graph as dispute_intake (D-048) ([#134](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/134), `91e82d0`)
- test: bound only block_card in the retry-timeout test ([#135](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/135), `e345b39`)
- test: run dispute_intake end to end against the real MCP server locally (INT1) ([#138](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/138), `4ca799a`)
- fix: confirm a charge the customer did not name before acting (spec 04, D-067) ([#142](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/142), `e9ce62c`)
- feat: stream one progress label per step to the customer (spec 04 AC-17) ([#156](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/156), `458829b`)

### Auditor and judge
- feat: add the advisory judge with grounded reasons and fallback (spec 18 T4) ([#73](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/73), `be26d1d`)
- fix: close the 18a follow-ups on A3, A4 and the fixtures ([#79](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/79), `caae577`)
- feat: add checks A1 decision and A2 deadline ([#85](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/85), `c4a6574`)

### Backend API
- feat: api stub with every spec 01 route, compose.dev and config names ([#56](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/56), `500ecfe`)
- fix: close the 01d round-2 stub follow-ups ([#76](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/76), `7fe993b`)
- feat: spec 05 backend on the case store (Cognito, analyst actions, channels, agent proxy) ([#111](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/111), `e1e8b21`)
- feat: demo sessions understand with S1 and the deploy passes the public link config ([#140](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/140), `451a387`)
- feat: serve the spec 09 demo customers and their cards from gold (spec 05 T7) ([#141](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/141), `71f8a40`)
- feat: per-IP rate limits and a daily LLM spend cap for the public demo (spec 05 AC-18) ([#148](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/148), `44cda23`)
- fix: answer a Platform outage with a calm retry turn in ES/PT ([#150](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/150), `552508e`)
- feat: demo sessions open by scenario with a typed name and their own run (spec 05 AC-14 to AC-17, D-068) ([#152](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/152), `bcbdeb5`)

### CI
- fix: give the entry-point gold fixture the transaction_country column (main is red) ([#137](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/137), `74cb531`)

### Contracts
- fix: close the 01a final-review follow-ups ([#65](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/65), `c6c9f2d`)
- feat: add refuse, clarify and cancel ES/PT messages ([#77](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/77), `dcca724`)
- feat: contract 1.4.0 (D-052, idempotency key, cards read_at) ([#107](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/107), `7a07fd4`)
- fix: tool outputs ignore unknown fields, inputs stay strict ([#153](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/153), `dbd3fb2`)

### Data
- feat: ops lakehouse bronze and silver on the in-memory store (spec 14 T1-T2) ([#145](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/145), `226981d`)
- feat: ops gold tables, manifest and ops_kpis.json export (spec 14 T3-T4) ([#146](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/146), `b6cbbd9`)

### Deploy and infrastructure
- feat: add compose stack, deploy through OIDC and SSM, and Postgres backup ([#41](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/41), `1993964`)
- fix: read the deploy role and instance id from Actions variables ([#115](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/115), `a89e856`)
- fix: sync gold to the host and pass the spec 05 config names to the containers ([#119](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/119), `7163a57`)
- fix: deploy only after CI passes on main ([#136](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/136), `96c5ceb`)

### Docs and specs
- docs: add spec 06 deploy and CI ([#40](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/40), `4d7c16e`)
- docs: add ADR 0023 correcting the MX provisional-credit window ([#69](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/69), `9560f3a`)
- docs: add the problem in numbers with four charts and conclusions ([#70](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/70), `9e0af0b`)
- docs: set the freeze at v0.4.0 on the public URL (D-004) ([#75](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/75), `d455743`)
- docs: record D-029 in CLAUDE.md and the current merge rule in CONTRIBUTING ([#83](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/83), `4a0f2be`)
- docs: add spec 09 demo and evaluation data ([#89](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/89), `e8423d3`)
- docs: add spec 10 evaluation harness ([#90](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/90), `22da4b4`)
- docs: add spec 12 insight pages ([#91](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/91), `90f0d11`)
- docs: add spec 14 operational lakehouse ([#92](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/92), `644a2fd`)
- docs: fix the data shape of the three /evaluation result files (spec 12 Q1) ([#116](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/116), `d57c5ab`)
- docs: mark specs 09, 10, 12 in progress; approve and defer 14 ([#128](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/128), `1fe7a83`)

### Evaluation and eval data
- feat: add auditor checks A3-A7 as pure functions ([#54](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/54), `6371676`)
- docs: sync the unsealed protocol with decisions D-011, D-012, D-016, D-017 and D-022 ([#60](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/60), `e8d468d`)
- fix: send temperature 0 only where the model accepts it (D-016) ([#71](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/71), `8032497`)
- feat: add the demo index query and its candidate list ([#93](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/93), `426078d`)
- feat: add the demo customers, live profiles and sample cases ([#94](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/94), `4be21e0`)
- feat: add the 20 dev agent cases derived by the policy engine ([#95](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/95), `f75411b`)
- feat: add the 80 held-out agent cases and their hash ([#97](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/97), `452a7c7`)
- feat: add the harness run loop, comparison and metrics ([#98](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/98), `8de768a`)
- feat: add the harness reports, held-out guard and label cross ([#100](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/100), `6bffb11`)
- test: fail when pitch_numbers.json drifts from the pitch CSVs ([#101](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/101), `1ac4e09`)
- fix: spec 10 harness follow-ups (held-out guard in run_set) ([#113](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/113), `2148291`)
- fix: spec 09 case follow-ups ([#114](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/114), `84741bd`)
- feat: classifier set drafts from three model families (ADR 0025) ([#118](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/118), `345ec07`)
- fix: cover the D-029 call request on a high-zone charge ([#121](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/121), `efcc1f8`)
- feat: add make eval and make eval-stub ([#127](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/127), `7d2e58e`)
- feat: second-labeling kit for the 20 dev cases (spec 09 T6) ([#143](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/143), `621e8c1`)
- feat: deterministic review hints for the classifier drafts ([#144](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/144), `2ed9252`)
- feat: robustness suite with simulated customer characters and a constitution checker ([#157](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/157), `77751c6`)
- feat: live LLM simulated customer for the robustness suite ([#158](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/158), `cec4342`)
- feat: make eval-local runs the dev set against the real graph, MCP server and store-backed api (spec 10 T6) ([#164](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/164), `21a8809`)
- feat: review the classifier train and validation splits ([#165](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/165), `5636caa`)

### Fraud model (ML)
- feat: sklearn fraud screen with calibration and cost harness (spec 17 T3) ([#46](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/46), `5088ce2`)
- feat: search for transaction-time fraud signal before the test window (spec 17 FEAT) ([#66](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/66), `3aa9e44`)

### Intent and injection (NLU)
- feat: add B0 rules arm, ES/PT date parser and injection rules ([#55](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/55), `0b7f15b`)
- fix: widen B0 rules coverage (task 11c) ([#74](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/74), `a3cf8cf`)
- fix: flag PT/ES policy-override and staff role-play injections in B0 ([#139](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/139), `5853749`)
- fix: answer a clear non-ES/PT sentence by rule in the session language plus English ([#154](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/154), `d437030`)
- fix: B0 reads 13 abril as a date and English person requests (spec 11e) ([#159](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/159), `ad750ad`)

### LLM client
- feat: add shared LLM client (fake, bedrock, anthropic) and config.resolve ([#53](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/53), `b9fef96`)
- fix: configurable read timeout, used by the judge ([#84](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/84), `291007b`)

### MCP server
- feat: add tools.py v1.1 with the 16 customer tools and a fake MCP server ([#59](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/59), `ac0a144`)
- feat: add the MCP app with key, session, fault and rate gates ([#81](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/81), `6f91daa`)
- feat: add gold loader and search, profile, score, convert tools ([#106](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/106), `642a494`)
- feat: add compute_deadline and search live sessions on the real clock ([#120](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/120), `f421468`)
- feat: run the real gated MCP server from python -m mcp_server ([#122](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/122), `3d2bf94`)
- feat: add open_case and block_card with idempotency and the call hold ([#123](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/123), `0ac142c`)
- feat: add the follow-up tools add_case_info, request_call and request_reevaluation ([#124](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/124), `9d07137`)
- feat: add the case and card read tools and the latency benchmark ([#125](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/125), `212bce8`)
- feat: add the notification tools send_case_summary and list_my_notifications ([#126](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/126), `6804d41`)
- feat: move the queue status after the agent's writes ([#132](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/132), `1738511`)
- fix: name the legal deadline source in the customer's language (contract 1.5.0) ([#149](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/149), `b2909e3`)
- test: make the AC-12 card-number leak check deterministic ([#162](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/162), `70bd65d`)

### Shared package and cross-cutting
- feat: add TurnResult, FinalState, view models and customer projections ([#45](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/45), `68fb41a`)
- fix: request_call returns expected_contact_by from a policy window ([#50](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/50), `728f981`)
- feat: add the shared package skeleton, ids and the receipt contract ([#52](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/52), `f4559d6`)
- ci: add ruff and acceptance-criteria coverage gates ([#57](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/57), `5f66be9`)
- ci: run the PostgresStore suite on a postgres:16 service ([#108](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/108), `777045d`)
- ci: add a 15-minute uptime monitor with Telegram alerts ([#147](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/147), `b5495a5`)
- feat: demo sessions carry a display name and a demo run the console can read (spec 05, D-068) ([#151](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/151), `218ecac`)
- feat: demo type C, a live demo visitor registers a simulated charge for its own run (spec 05 AC-19, spec 03 AC-14) ([#160](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/160), `5817e92`)

### Policy engine and clock
- feat: add the policies.yaml v2 model, loader and rule ids ([#63](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/63), `ac60c62`)
- feat: decide a turn and re-check an action with rule ids ([#64](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/64), `cbf20ab`)
- feat: add the regulatory clock with MX and AR deadlines ([#67](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/67), `3588fed`)
- feat: add the CO and BR rows of the regulatory clock ([#68](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/68), `88eaa3d`)
- feat: defer the high-zone block on a call request (D-029) ([#80](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/80), `5c49733`)
- feat: add queue transition() and sla() with the decision table ([#86](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/86), `1c193a8`)

### Store and Postgres
- feat: add the Store interface and in-memory backend with case-id retry ([#58](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/58), `d788b80`)
- feat: add schema.sql with the spec 01 §6.5 tables and the append-only guard ([#61](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/61), `3ee76a3`)
- refactor: import VERIFIED_WITH from contracts ([#78](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/78), `a61b294`)
- feat: add the Postgres backend and run the store suite on it ([#82](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/82), `91740f2`)
- feat: add session, denial and channel accessors on both backends ([#87](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/87), `efd0137`)
- feat: add the idempotency accessor once on both backends ([#99](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/99), `0ecbb4c`)
- feat: add llm_calls accessors on both backends ([#117](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/117), `4415279`)
- fix: make schema.sql idempotent and apply it on every deploy ([#129](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/129), `63752c0`)

### Web
- feat: hello-world web on mock data for specs 16, 07, 08 and 13 ([#51](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/51), `076c980`)
- feat: add interactive problem charts to /analytics ([#72](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/72), `19eaa8f`)
- feat: add the /evaluation page for the harness results ([#102](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/102), `a8b4398`)
- feat: add the /data page and data_quality.json ([#103](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/103), `275205b`)
- fix: spec 12 page follow-ups ([#112](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/112), `c164a09`)
- feat: add the benchmark, classifier and fraud sections to /evaluation ([#130](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/130), `bab5311`)
- docs: add the spec 12 T7 screenshots and the script that takes them ([#163](https://github.com/salazarvalverdeai/factored-hackathon-2026-nick-of-time/pull/163), `73c9518`)
