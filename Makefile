# speedmap.gr development entry points

PY := .venv/bin/python
PSQL := psql "$${SPEEDMAP_DSN:-postgresql:///speedmap}"

.DEFAULT_GOAL := help

.PHONY: help
help:
	@grep -hE '^[a-z-]+:.*#' $(MAKEFILE_LIST) | sed 's/:[^#]*# */\t/' | expand -t22

.PHONY: setup
setup: # create .venv and install all dependencies
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e '.[dev,pipeline]'
	@test -f .env || cp .env.example .env

.PHONY: fmt
fmt: # apply the autofixable lint rules
	.venv/bin/ruff check --fix .

.PHONY: lint
lint: # ruff, the numeric fallback ban, and the two generated contracts
	.venv/bin/ruff check .
	$(PY) tools/lint_numeric_fallback.py .
	$(PY) tools/codegen_tiles.py --check
	$(PY) -m tools.openapi_schema --check

.PHONY: typecheck
typecheck: # mypy --strict
	.venv/bin/mypy .

.PHONY: test
test: # pytest
	$(PY) -m pytest -q

.PHONY: web-check
web-check: # typecheck and test the frontend, when it has been installed
	@test -d web/node_modules \
		&& (cd web && npm run --silent typecheck && npm run --silent test) \
		|| echo "  web: no node_modules, skipped"

.PHONY: check
check: lint typecheck test web-check # everything a commit should pass

.PHONY: bootstrap
bootstrap: # from a bare clone to a loaded database, in the one order that works
	$(PY) -m tools.bootstrap

.PHONY: migrate
migrate: # apply pending migrations
	$(PY) -m normalise.migrate

.PHONY: migrate-status
migrate-status: # list pending migrations
	$(PY) -m normalise.migrate --status

.PHONY: build
build: # rebuild the derived tables from raw_*
	$(PY) -m normalise.build

.PHONY: tiles
tiles: # cut the map tiles; needs tippecanoe, so a desktop rather than the Pi
	$(PY) -m publish.run

.PHONY: codegen
codegen: # regenerate the tile contract and the OpenAPI document
	$(PY) tools/codegen_tiles.py
	$(PY) -m tools.openapi_schema
	@test -d web/node_modules && (cd web && npm run --silent api:types) || true

.PHONY: api
api: # run the read-only API on :8000
	.venv/bin/uvicorn api.main:app --reload

.PHONY: progress
progress: # how far the register load has got
	@$(PSQL) -c "select * from register_progress order by dataset"

.PHONY: db-check
db-check: # confirm Postgres is reachable with the extensions the schema needs
	@$(PSQL) -tAc "select version()" || { echo "no database at $${SPEEDMAP_DSN:-postgresql:///speedmap}"; exit 1; }
	@$(PSQL) -tAc "select extname from pg_extension order by 1"
