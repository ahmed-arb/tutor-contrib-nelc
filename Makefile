.DEFAULT_GOAL := help
.PHONY: docs
SRC_DIRS = ./tutornelc

# The vendored Django app under templates/ is excluded from these checks: it is
# not part of the Tutor plugin's own Python package, it imports edx-platform
# modules that are not installed here, and mypy --strict on it would only ever
# report missing imports. tests/run_checks.py is what exercises that code.

# Warning: These checks are not necessarily run on every PR.
test: test-lint test-types test-format  # Run some static checks.

test-format: ## Run code formatting tests
	ruff format --check --diff ${SRC_DIRS}

test-lint: ## Run code linting tests
	ruff check ${SRC_DIRS}

test-types: ## Run type checks.
	mypy --exclude=templates --ignore-missing-imports --implicit-reexport --strict ${SRC_DIRS}

format: ## Format code
	ruff format ${SRC_DIRS}

fix-lint: ## Fix lint errors automatically
	ruff check --fix ${SRC_DIRS}

version: ## Print the current tutor-contrib-nelc version
	@python -c 'import io, os; about = {}; exec(io.open(os.path.join("tutornelc", "__about__.py"), "rt", encoding="utf-8").read(), about); print(about["__version__"])'

######## Demo instance

PYTHON ?= python3
TUTOR_VERSION ?= 22.0.1
TUTOR_MFE_VERSION ?= 22.0.0

# This target installs into whatever virtualenv is active and configures whatever
# TUTOR_ROOT is exported, and refuses to run if either is missing. Both are your
# shell's state, which a Makefile cannot set: every recipe line runs in its own
# subshell. Rather than create a venv you then have to activate anyway, or default
# TUTOR_ROOT to something your later `tutor` commands would not agree with, it
# asks you to set both first and then uses exactly what you set.
#
# TUTOR_ROOT matters most if you are reviewing several submissions: give each one
# its own root or they share a config, a database and a set of Docker volumes.

setup: ## Install Tutor, tutor-mfe and this plugin into the active venv, then enable and configure
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "No virtualenv is active. First:"; \
		echo ""; \
		echo "    $(PYTHON) -m venv .venv"; \
		echo "    source .venv/bin/activate"; \
		echo ""; \
		exit 1; \
	fi
	@if [ -z "$$TUTOR_ROOT" ]; then \
		echo "TUTOR_ROOT is not set. Give this submission its own root, so it cannot"; \
		echo "share config, database or volumes with anything else you are running:"; \
		echo ""; \
		echo "    export TUTOR_ROOT=\"$$PWD/tutor-root\""; \
		echo ""; \
		exit 1; \
	fi
	pip install --upgrade --quiet pip
	pip install --quiet "tutor==$(TUTOR_VERSION)" "tutor-mfe==$(TUTOR_MFE_VERSION)"
	pip install --quiet -e .
	tutor plugins enable nelc mfe
	tutor config save
	@echo
	@echo "Configured. TUTOR_ROOT=$$TUTOR_ROOT"
	@echo
	@echo "    tutor images build openedx mfe    # 15-30 min"
	@echo "    tutor local launch"
	@echo
	@echo "Then http://local.openedx.io and sign in as admin / admin"

checks: ## Run the standalone checks in their own venv. No Docker needed
	$(PYTHON) -m venv .venv-tests
	.venv-tests/bin/pip install --quiet "django>=4.2" djangorestframework django-model-utils
	.venv-tests/bin/python tests/run_checks.py

.PHONY: setup checks

ESCAPE = 
help: ## Print this help
	@grep -E '^([a-zA-Z_-]+:.*?## .*|######* .+)$$' Makefile \
		| sed 's/######* \(.*\)/@               $(ESCAPE)[1;31m\1$(ESCAPE)[0m/g' | tr '@' '\n' \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[33m%-30s\033[0m %s\n", $$1, $$2}'
