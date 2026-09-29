# Reproduces the bronze → silver → gold pipeline, the late-arrivals fixture and data/quality_report.md.
#   make setup              everything from scratch (needs .env and the dataset AWS profile; see .env.example)
#   make setup SOURCE=local the same over the local mirror data/<table>/ (no network)
#   make hooks              installs the gitleaks pre-commit hook (.pre-commit-config.yaml)
PYTHON ?= python3
PY := .venv/bin/python
SOURCE ?= s3

.PHONY: setup deps pipeline fixture report test hooks

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
