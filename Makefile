.PHONY: help
help:
    @echo "Available commands:"
    @grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'


.PHONY: test-frontend test-backend test

test: test-backend test-frontend

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
test-frontend: node_modules
	npm test

# ==============================================================================
# Backend Development
#
# These targets require uv and all the required dependencies to be installed.
# ==============================================================================

test-backend:
	uv run pytest -vv -o log_cli=true -o log_cli_level=10 tests/backend/