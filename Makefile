# Reproduces the bronze → silver → gold pipeline, the late-arrivals fixture and data/quality_report.md.
#   make setup              everything from scratch (needs .env with S3 credentials; see .env.example)
#   make setup SOURCE=local the same over the local mirror data/<table>/ (no network)
PYTHON ?= python3
PY := .venv/bin/python
SOURCE ?= s3

.PHONY: setup deps pipeline fixture report test

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
