# Reproduces the bronze → silver → gold pipeline, the late-arrivals fixture and data/quality_report.md.
#   make setup              everything from scratch (needs .env and the dataset AWS profile; see .env.example)
#   make setup SOURCE=local the same over the local mirror data/<table>/ (no network)
#   make hooks              installs the gitleaks pre-commit hook (.pre-commit-config.yaml)
PYTHON ?= python3
PY := .venv/bin/python
SOURCE ?= s3

.PHONY: setup deps pipeline fixture report test lint hooks check-bedrock check-telegram check-resend check-jev check-all telegram-profile env-pull gold-pull labels-pull eval eval-stub eval-local

setup: deps pipeline fixture report

$(PY):
	$(PYTHON) -m venv .venv

deps: $(PY)
	$(PY) -m pip install -q -r requirements.txt

pipeline:
	$(PY) -m data.pipeline run --source $(SOURCE)

fixture:
	$(PY) -m data.pipeline fixture

report:
	$(PY) -m data.pipeline report

# Spec 14: operational lakehouse on a seeded in-memory store (T5 adds the Postgres source). GOLD_PATH overrides data/gold.
.PHONY: ops
ops:
	PYTHONPATH=.:packages $(PY) -m data.ops run --source sample

test:
	$(PY) -m pytest -q

# Same pinned ruff as CI (ruff.toml); installs into the venv on first use.
lint:
	$(PY) -m pip install -q ruff==0.14.0
	$(PY) -m ruff check .

hooks: $(PY)
	$(PY) -m pip install -q pre-commit
	.venv/bin/pre-commit install

# Access checks (docs/runbooks/): read the local .env, never print secrets. Extra flags through ARGS="...".
check-bedrock:
	cd scripts/checks && ../../$(PY) check_bedrock.py $(ARGS)

check-telegram:
	cd scripts/checks && ../../$(PY) check_telegram.py $(ARGS)

check-resend:
	cd scripts/checks && ../../$(PY) check_resend.py $(ARGS)

check-jev:
	cd scripts/checks && ../../$(PY) check_jev.py $(ARGS)

check-all: check-bedrock check-telegram check-jev

# Telegram bot profile: English name; description, short description and commands in EN (default), ES and PT.
telegram-profile:
	$(PY) scripts/telegram_profile.py

# Fill the local .env from SSM (/nickoftime/prod/*) without printing values. ARGS=--force overwrites existing values.
env-pull:
	$(PY) scripts/env_pull.py $(ARGS)

# Project data from the team bucket (no dataset credentials needed). Labels are readable only by Diego and the lead.
GOLD_BUCKET ?= s3://nickoftime-gold-061039767206
AWS_TEAM_PROFILE ?= nickoftime

gold-pull:
	aws s3 sync $(GOLD_BUCKET)/gold/v1/ data/gold/ --profile $(AWS_TEAM_PROFILE) --only-show-errors
	$(PY) scripts/verify_gold.py

labels-pull:
	aws s3 cp $(GOLD_BUCKET)/labels/v1/transaction_labels.parquet data/gold_eval/transaction_labels.parquet --profile $(AWS_TEAM_PROFILE) --only-show-errors
	$(PY) scripts/verify_gold.py

# Evaluation harness (spec 10 §6, T6): the dev set on S0 and S1 against a running api with EVAL_MODE=true. Results go
# to eval/.runs/ (git-ignored); the held-out runs only after the seal (AC-07). EVAL_CASES points at another case file.
EVAL_API ?= http://localhost:8000
EVAL_ARMS ?= S0,S1
EVAL_RUNS ?= 4
EVAL_CASES ?=

eval: $(PY)
	PYTHONPATH=packages $(PY) -m eval.harness run --set dev --arms $(EVAL_ARMS) --runs $(EVAL_RUNS) --api $(EVAL_API) $(if $(EVAL_CASES),--cases $(EVAL_CASES),)

# The real stack for `make eval` (spec 10 T6, eval/README.md "Local real stack"): the store-backed api with the eval
# hooks (:8000) and the real MCP server (:8001) over one in-memory store, and the real graph under `langgraph dev`
# (:2024); gold read-only from GOLD_PATH. S1 calls Bedrock with AWS_PROFILE (default nickoftime); EVAL_PROVIDER=fake
# keeps every arm off Bedrock. Ctrl-C stops all three. Then `make eval` in another shell.
GOLD_PATH ?= data/gold
EVAL_PROVIDER ?= bedrock

eval-local: $(PY)
	@$(PY) -c "import langgraph_api" 2>/dev/null || $(PY) -m pip install -q "langgraph-cli[inmem]>=0.4"
	PYTHONPATH=packages:apps/api:apps/mcp $(PY) -m eval.local --gold $(GOLD_PATH) --provider $(EVAL_PROVIDER)

# The api stub with the evaluation hooks on and the fake LLM, on EVAL_API's default port, for `make eval` offline.
eval-stub: $(PY)
	cd apps/api && PYTHONPATH=../../packages:../.. EVAL_MODE=true LLM_PROVIDER=fake ../../$(PY) -m uvicorn app.main:create_app --factory --port 8000

# Spec 15 B1 (python -m eval.bench). `make bench` is the one post-seal run on the frozen test split: it refuses while
# eval/PROTOCOL.md is not SEALED and tagged protocol-v1 on the merged sealing commit, and writes eval/results/bench_*.csv, benchmark.json and the SVG. `make bench-dev` runs
# the validation split as a development run into eval/.runs/bench/ (git-ignored); BENCH_PROVIDER=fake calls no model.
BENCH_PROVIDER ?= bedrock
BENCH_ARGS ?=

.PHONY: bench bench-dev
bench: $(PY)
	PYTHONPATH=.:packages $(PY) -m eval.bench --split test

bench-dev: $(PY)
	PYTHONPATH=.:packages $(PY) -m eval.bench --split validation --provider $(BENCH_PROVIDER) $(BENCH_ARGS)
