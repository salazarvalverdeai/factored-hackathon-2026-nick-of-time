# 0012. Frozen demo date

- **Status:** Accepted
- **Date:** 2026-10-03
- **Deciders:** Freddy · **Owner:** @salazarvalverdeai
- **Related:** specs 02, 03, 09

In the context of gold transactions that end on 2026-05-31 (gold contract R1), facing deadlines and searches that
would find nothing if computed from the real date, we decided that the system's "today" is
**`DEMO_TODAY=2026-06-03`** (a Wednesday), read from the environment by the clock, the tools and the harness, and shown
in the UI, to achieve deterministic, testable deadlines (MX debit opened on 2026-06-03 → credit by 2026-06-05),
accepting one line of explanation in the README and the video, instead of shifting the dataset's dates (which would
break the reproducibility of the pitch numbers).
