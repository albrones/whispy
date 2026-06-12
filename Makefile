.PHONY: help install test lint format check run uninstall clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff
PYTEST := $(VENV)/bin/pytest

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install the package with dev dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

test: ## Run the test suite
	$(PYTEST) -q

cov: ## Run tests with coverage report
	$(PYTEST) --cov=src/whispy --cov-report=term-missing

lint: ## Lint with ruff
	$(RUFF) check .

format: ## Auto-format with ruff
	$(RUFF) format .

check: ## CI-equivalent checks (lint + format check + tests)
	$(RUFF) check .
	$(RUFF) format --check .
	$(PYTEST) -q

run: ## Run the daemon in the foreground (for development)
	$(PY) whispy_daemon.py

doctor: ## Diagnose the environment (sox, model, permissions, daemon)
	$(PY) whispy_daemon.py --doctor

uninstall: ## Remove the LaunchAgent and venv
	./install.sh --uninstall

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
