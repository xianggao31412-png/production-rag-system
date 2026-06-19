# Enterprise Knowledge Assistant — common tasks
.DEFAULT_GOAL := help
PY ?= python

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install core dependencies
	$(PY) -m pip install -r requirements.txt

install-optional: ## Install optional production backends (chroma, cross-encoder)
	$(PY) -m pip install -r requirements-optional.txt

run: ## Run the API + dashboard (http://localhost:8000)
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test: ## Run the test suite
	$(PY) -m pytest

smoke: ## End-to-end smoke test (boots app in-process, ingests, queries)
	$(PY) scripts/smoke_test.py

seed: ## Ingest the bundled example documents into a running instance
	$(PY) scripts/seed_examples.py

docker-build: ## Build the Docker image
	docker build -t enterprise-knowledge-assistant:latest .

docker-up: ## Start with docker compose
	docker compose up --build

clean: ## Remove caches and runtime data
	rm -rf .pytest_cache __pycache__ */__pycache__ */*/__pycache__ data

.PHONY: help install install-optional run test smoke seed docker-build docker-up clean
