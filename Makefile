# CS1302 Code Visualizer Makefile
# Provides unified task runners for Python and Frontend workflows

.DEFAULT_GOAL := help

.PHONY: help install install-py install-frontend install-sys-deps \
        build build-frontend build-py watch-frontend \
        test test-py test-frontend test-frontend-watch test-examples test-all \
        lint lint-py deptry format format-py typecheck check \
        clean clean-py clean-frontend update-tracer gallery all

# --- Configuration & Commands ---
PYTHON ?= uv run python
UV ?= uv
NPM ?= npm
FRONTEND_DIR := cs1302_code_visualizer/frontend
GALLERY_JDK ?=

##@ 🛠️ General & Help
help: ## Display this interactive help menu
	@echo "Usage: make [target]"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "\033[1m%-20s\033[0m %s\n", "Target", "Description"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ 📦 Installation & Setup
install: install-py install-frontend ## Install all Python and Frontend dependencies

install-py: ## Install Python dependencies via uv sync
	$(UV) sync --all-groups

install-frontend: ## Install frontend node modules via npm
	$(NPM) --prefix $(FRONTEND_DIR) install

install-sys-deps: ## Run system dependencies installer (Java, Graphviz, PlantUML)
	$(PYTHON) -m scripts.install_deps

##@ 🏗️ Building
build: build-frontend build-py ## Build frontend Webpack bundles and Python wheel/sdist

build-frontend: ## Compile frontend Webpack production bundles
	$(NPM) --prefix $(FRONTEND_DIR) run build

build-py: ## Build Python package distributables (sdist and wheel)
	$(UV) build

watch-frontend: ## Run frontend Webpack watcher in development mode
	$(NPM) --prefix $(FRONTEND_DIR) run watch

gallery: ## Generate the complete PDF gallery with JDK 25 (GALLERY_JDK=/path/to/jdk25)
	$(UV) run --extra gallery python -m scripts.build_gallery_data $(if $(GALLERY_JDK),--jdk "$(GALLERY_JDK)",)
	$(UV) run --extra gallery python -m scripts.generate_gallery_pdf

##@ 🧪 Testing
test: test-py test-frontend ## Run Python pytest and Frontend Vitest unit tests

test-py: ## Run Python pytest with coverage enforcement
	$(PYTHON) -m pytest

test-frontend: ## Run Frontend Vitest unit tests in JSDOM
	$(NPM) --prefix $(FRONTEND_DIR) test

test-frontend-watch: ## Run Frontend Vitest in interactive watch mode
	$(NPM) --prefix $(FRONTEND_DIR) run test:watch

test-examples: ## Run full end-to-end integration tests across all 22 example suites
	./examples/test_all.sh --no-rm-json --no-rm-image --no-open

test-all: test test-examples ## Run all unit tests and integration test suites

##@ 🔍 Quality & Linting
lint: lint-py ## Run all code linters

lint-py: ## Run Ruff linter on Python codebase
	$(UV) run ruff check

deptry: ## Check Python dependency declarations and imports
	$(UV) run deptry .

format: format-py ## Format Python source code

format-py: ## Run Ruff code formatter and auto-fix lint issues
	$(UV) run ruff format
	$(UV) run ruff check --fix

typecheck: ## Run Basedpyright static type checker
	$(UV) run basedpyright --level error cs1302_code_visualizer

check: lint typecheck test ## Run full verification suite (lint, typecheck, unit tests)

##@ 🔄 Maintenance & Utilities
update-tracer: ## Check and update code-tracer JAR release and SHA-256 hash in pyproject.toml
	$(PYTHON) scripts/update_tracer_hash.py

clean: clean-py clean-frontend ## Remove temporary files, caches, and build artifacts

clean-py: ## Remove Python build artifacts, bytecode, and test/linter caches
	rm -rf dist/ build/ *.egg-info .pytest_cache/ .ruff_cache/ .coverage htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[co]" -delete 2>/dev/null || true

clean-frontend: ## Remove frontend build outputs and node_modules caches
	rm -rf $(FRONTEND_DIR)/build/*

all: install build check ## Full end-to-end setup, build, and verification
