# Pipeline notes and verification of the pitch numbers

> Decisions and list of what was not verified, copied as-is from the wrap-up report of Sep 28, 2026 (index in
> `docs/eda/README.md`, verification in `queries/pitch/`, pipeline in `data/pipeline/`, fixture in
> `data/fixtures/late_arrival/`, tests in `tests/`).

## Decisions

All five tasks are done in this repo; I did not find the new repo on disk.

It covers the 4 tables of the W3 idea, in full: customers, products, transactions and complaints.

**Decisions I made that you can revert:**
- The EDA queries stay in `docs/eda/queries/`, because the documents cite them by that path. `queries/` only holds the verification queries.
- `.gitignore` now lets in `data/pipeline/`, `data/fixtures/`, the report and the manifest. That relaxes rule 4 of `CLAUDE.md` ("data/ stays out of git"), which I did not touch; you decide whether to update it.
- I did not create `eval/`: none of the tasks asked for it.
- I installed `pandera[polars]` and `pytest` in the `.venv` and added them to `requirements.txt`.

## What I could not verify

- **Installation from a clean clone.** I ran on an existing `.venv` (Python 3.14) with the S3 mirror already complete, so neither the download nor the venv creation was ever exercised.
- **Integrity of `customers.csv` and `products.csv`.** Their ETag is multipart and not an md5, so I only compare the size.
- **Time zone of the load date.** I used Lima time, like `data_quality.md`. If it were UTC, the future dates would drop by 49 customers and 113 products (this came from a query I ran separately and did not save).
- **Contract domains.** They come from the values observed in the EDA, so they pass by construction on this data. They detect new changes, but they do not validate the business rule.
- **How late data would arrive in practice.** The fixture assumes that a re-delivery overwrites the object in S3 and that renames are declared as aliases. Factored has not said (Slack questions 6 and 7).
- **Assumptions behind the numbers.** That `Queja` equals disputes is a low-confidence rule, and I do not know whether `fraud_score` is available in real time. The queries reproduce the numbers, but they do not validate those assumptions.
- **"No network" in the tests.** The block covers Python sockets, not DuckDB's C++ layer. The tests do not use httpfs and ICU is statically linked, but it is not enforced.
- **Row diff.** It uses DuckDB's 64-bit `hash()`, which is not cryptographic. The manifest's sha256 is exact.
- **Numbers outside the list.** I did not review the benchmark, the costs, the 32.8% automatable or the savings: they are assumptions or projections.

## Migration to this repo (Sep 28, 2026)

Everything above was copied as-is from the EDA repo. This section records what was done when bringing the pipeline here.

**Decisions**
- The repo did not exist (neither on disk nor on GitHub): it was created locally as `factored-hackathon-2026-nick-of-time`, with no remote
  and no push.
- `contracts/gold_contract.md` did not exist: it was drafted from the team's 4 requirements (12 months of transactions,
  `customer_id` resolved by join, `is_fraud` only in `gold_eval/`, `customer_profile` and `transactions_enriched`). Anything
  that does not follow from those 4 points is marked **[proposal]** in the contract.
- 12-month window: the last complete months, 2025-06-01 → 2026-05-31 (chosen by Freddy).
- Copied, not moved: the EDA repo keeps `docs/eda`, `data/pipeline`, `data/fixtures`, `tests` and the Makefile.
- `contracts.py` stayed in `data/pipeline/`, where the pipeline imports it; `contracts/` holds the gold contract.
- `queries/pitch/` (SQL + CSV, without the runner) was also copied so the `docs/eda/` index does not end up with broken
  links. It cannot be regenerated here: gold only has 4 tables and 12 months. The links to `docs/pitch/pitch_brief.md`
  were left as plain text (a file in the EDA repo).
- Bronze downloads only the transactions partitions from 2025-05-31 (one day before the window, because of the shifted
  operating day) onward: 714 files are not downloaded.
- The fixture was moved to May 2026 so that it falls inside the window, and an event from 2025-05-31 (WIN-01) was added.
- `.gitattributes` keeps the fixture CSVs byte for byte (BOM + CRLF); with `core.autocrlf=input` git was converting them.
- The report does not compare against the EDA: `outputs/tables/` is not here and transactions covers a different period. `make pitch` was
  removed from the Makefile.

**Run from a clean clone**

| Item | Value |
|---|---|
| Date | 2026-09-28, 20:02:10 → 20:03:10 UTC |
| Procedure | `git clone` of commit `4ba3547` into a temporary directory, `.env` copied by hand (it is not in git), `PIP_NO_CACHE_DIR=1 make setup` |
| Python in the new venv | 3.13.11 (duckdb 1.5.6, polars 1.44.2, pandera 0.33.1, pyarrow 25.0.1) |
| **Total `make setup` time** | **60.27 s** wall clock (`/usr/bin/time -p`) |
| Of the total, pipeline run | 49.7 s (the rest: venv, uncached dependencies, fixture and report) |
| Download from S3 | 1,482 objects, 416.5 MB; 714 skipped as outside the window |
| Result | exit 0; gold v1 with the same sha256 as the commit's `data/gold/manifest.json` in all 7 tables; rules G1–G5 pass; `make test`: 6 passed |

Cross-check: gold has 1,477,723 transactions in the window and `gold_eval` 1,372 frauds, the same counts that
the full dataset gives in the EDA repo for that window.

**Still unverified**
- The team's actual contract: if another `gold_contract.md` exists, it may differ from this draft, especially in what is
  marked [proposal].
- Another machine or another network: the clean clone ran on the same Mac and with the same connection to S3. Tested with Python 3.13
  (here) and 3.14 (EDA repo); not with other versions.
- sha256 stability across library versions: `requirements.txt` does not pin versions. The same `customers` content
  gave a different sha256 with DuckDB 1.5.5 (EDA repo) than with 1.5.6 (here), because the Parquet writer changes. A
  future install with another version would bump the gold version with no data change.
