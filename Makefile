.PHONY: help install reinstall app test lint format check docs uninstall clean

UNAME := $(shell uname -s)
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff
PYTEST := $(VENV)/bin/pytest

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

reinstall: ## Rebuild Whispy V2, replace the installed copy, relaunch it and wait for its control socket
ifeq ($(UNAME),Darwin)
	./packaging/macos-v2/reinstall.sh
else
	./packaging/linux/reinstall.sh
endif

v2-reinstall: reinstall

app: ## macOS: build & sign the Whispy V2 bundle (dist/Whispy V2.app)
	./packaging/macos-v2/build_bundle.sh

v2-app: app

uninstall: ## Remove the installed Whispy V2 (settings and models are kept)
ifeq ($(UNAME),Darwin)
	rm -rf "/Applications/Whispy V2.app"
else
	./packaging/linux/reinstall.sh --uninstall
endif

# The repository tooling (release versioning, the docs generator, the guards
# of the website, docs and install scripts) is plain Python with pytest.
install: ## Create the tooling venv (pytest, ruff)
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

test: ## Run the Rust tests and the tooling tests
	cd v2 && cargo test --release
	$(PYTEST) -q

lint: ## Lint: clippy, rustfmt, ruff
	cd v2 && cargo fmt --check
	cd v2 && cargo clippy --release --all-targets -- -D warnings
	$(RUFF) check .
	$(RUFF) format --check .

format: ## Auto-format Rust and Python
	cd v2 && cargo fmt
	$(RUFF) format .

check: lint test ## CI-equivalent checks

docs: ## Regenerate the documentation site (website/docs) from docs/src
	$(PY) scripts/build_docs.py

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
