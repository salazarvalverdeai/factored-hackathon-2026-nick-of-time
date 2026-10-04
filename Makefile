# Reproduces the bronze → silver → gold pipeline, the late-arrivals fixture and data/quality_report.md.
#   make setup              everything from scratch (needs .env and the dataset AWS profile; see .env.example)
#   make setup SOURCE=local the same over the local mirror data/<table>/ (no network)
#   make hooks              installs the gitleaks pre-commit hook (.pre-commit-config.yaml)
PYTHON ?= python3
PY := .venv/bin/python
SOURCE ?= s3

.PHONY: setup deps pipeline fixture report test hooks check-bedrock check-telegram check-resend check-jev check-all env-pull

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

test:
	$(PY) -m pytest -q

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

# Fill the local .env from SSM (/nickoftime/prod/*) without printing values. ARGS=--force overwrites existing values.
env-pull:
	$(PY) scripts/env_pull.py $(ARGS)
