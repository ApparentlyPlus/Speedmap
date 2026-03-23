# speedmap.gr development entry points

PY := .venv/bin/python
PSQL := psql "$${SPEEDMAP_DSN:-postgresql:///speedmap}"

.DEFAULT_GOAL := help

.PHONY: help
help:
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

.PHONY: setup
setup: # create .venv and install all dependencies
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e '.[dev,pipeline]'
	@test -f .env || cp .env.example .env

.PHONY: fmt
fmt: # format the tree
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

.PHONY: lint
lint: # ruff, plus the numeric fallback ban
	.venv/bin/ruff format --check .
	.venv/bin/ruff check .
	$(PY) tools/lint_numeric_fallback.py .

.PHONY: typecheck
typecheck: # mypy --strict
	.venv/bin/mypy .

.PHONY: test
test: # pytest
	$(PY) -m pytest -q

.PHONY: check
check: lint typecheck test # everything a commit should pass

.PHONY: db-check
db-check: # confirm Postgres is reachable with the extensions the schema needs
	@$(PSQL) -tAc "select version()" || { echo "no database, see README"; exit 1; }
	@$(PSQL) -tAc "select extname from pg_extension order by 1"
