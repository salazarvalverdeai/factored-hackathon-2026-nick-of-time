# Reproduce el pipeline bronze → silver → gold, el fixture de llegadas tardías y data/quality_report.md.
#   make setup              todo desde cero (necesita .env con credenciales S3; ver .env.example)
#   make setup SOURCE=local lo mismo sobre el espejo local data/<tabla>/ (sin red)
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
