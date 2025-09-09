.PHONY: test-frontend test-backend test

test: test-backend test-frontend ## Run all tests

# ==============================================================================
# Frontend Development
#
# These targets require Node.js and npm to be installed.
# ==============================================================================

# Install frontend dependencies using npm. The node_modules file is used as a
# marker to avoid running 'npm install' every time.
node_modules: package.json package-lock.json
	npm install
	touch node_modules

# Run frontend unit tests
test-frontend: node_modules ## Run frontend tests
	npm test

# ==============================================================================
# Backend Development
#
# These targets require uv and all the required dependencies to be installed.
# ==============================================================================

static-backend-ruff: ## Run ruff to check the code
	/usr/bin/uv run ruff check app/

static-backend-mypy:
	/usr/bin/uv run mypy app/

static-backend-mypy-strict:
	/usr/bin/uv run mypy --strict --disallow-any-generics --disallow-untyped-defs --disallow-incomplete-defs --warn-unreachable --strict-equality app/

test-backend: ## Run backend tests
	uv run pytest -vv -o log_cli=true -o log_cli_level=10 tests/backend/

