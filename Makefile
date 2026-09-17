# Run from WSL (or any Linux shell with Docker). `make help` lists targets.
SHELL := /bin/bash
COMPOSE ?= docker compose
.DEFAULT_GOAL := help

.PHONY: help env up up-extras down restart build logs ps smoke test test-api test-sim \
        rigs chaos-fault chaos-reset reset-db clean nuke pipeline

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || { cp .env.example .env; echo "created .env – edit passwords if you like"; }

build: env ## Build all images (runs unit tests inside the rig-sim build)
	$(COMPOSE) build

up: env ## Start the core stack (Jenkins, agent, broker, 3 rigs, Prometheus, Grafana)
	$(COMPOSE) up -d --build
	@echo; echo "Jenkins http://localhost:$${JENKINS_PORT:-8080}  Grafana http://localhost:$${GRAFANA_PORT:-3000}  Broker http://localhost:$${RIG_API_PORT:-8000}/docs"
	@echo "Jenkins takes ~1-2 min on first boot. Then: make smoke"

up-extras: env ## Start core + sqlite-web (:8081), alertmanager (:9093), cadvisor (:8082)
	$(COMPOSE) --profile extras up -d --build

down: ## Stop everything (keeps volumes)
	$(COMPOSE) --profile extras down

restart: ## Restart the whole stack
	$(COMPOSE) --profile extras restart

logs: ## Tail logs (LOGS=service to filter, e.g. make logs LOGS=rig-api)
	$(COMPOSE) --profile extras logs -f --tail=100 $(LOGS)

ps: ## Container status
	$(COMPOSE) --profile extras ps

smoke: ## End-to-end smoke test from the host (needs curl + jq)
	bash scripts/smoke.sh

test: test-api test-sim ## Run all unit tests inside containers

test-api: ## rig-api: ruff + pytest (Docker build target "test")
	docker build --target test -t rig-api:test ./rig-api

test-sim: ## rig-sim: mvn test inside the maven image
	docker run --rm -v "$(CURDIR)/rig-sim:/src" -v maven_repo:/root/.m2 -w /src maven:3.9.8-eclipse-temurin-17 mvn -q -B test

rigs: ## Print the broker's view of the fleet
	RIG_API_URL=http://localhost:$${RIG_API_PORT:-8000} bash scripts/rig-cli.sh list

chaos-fault: ## Inject a fault into rig-munich-01 (watch Grafana / Prometheus alerts / quarantine)
	curl -fsS -X POST http://localhost:8103/fault -H 'Content-Type: application/json' -d '{"reason":"chaos: make chaos-fault"}'; echo

chaos-reset: ## Reset rig-munich-01 and lift its quarantine
	curl -fsS -X POST http://localhost:8103/reset; echo
	RIG_API_URL=http://localhost:$${RIG_API_PORT:-8000} bash scripts/rig-cli.sh unquarantine rig-munich-01

pipeline: env ## Trigger the Jenkins HIL pipeline for Vienna from the CLI
	@set -a; . ./.env; set +a; \
	crumb=$$(curl -fsS -u "$$JENKINS_ADMIN_ID:$$JENKINS_ADMIN_PASSWORD" "http://localhost:$${JENKINS_PORT:-8080}/crumbIssuer/api/json" | jq -r .crumb); \
	curl -fsS -u "$$JENKINS_ADMIN_ID:$$JENKINS_ADMIN_PASSWORD" -H "Jenkins-Crumb: $$crumb" -X POST \
	  "http://localhost:$${JENKINS_PORT:-8080}/job/rig-hil-pipeline/buildWithParameters?LAB=vienna" \
	  && echo "queued – http://localhost:$${JENKINS_PORT:-8080}/job/rig-hil-pipeline/"

reset-db: ## Drop the broker's SQLite volume (rigs re-seed from rigs.yaml)
	$(COMPOSE) stop rig-api
	$(COMPOSE) rm -f rig-api
	docker volume rm -f $$($(COMPOSE) config --format json | jq -r '.name')_rig_api_data
	$(COMPOSE) up -d rig-api

clean: ## Stop and remove containers + volumes (full reset, keeps images)
	$(COMPOSE) --profile extras down -v

nuke: clean ## clean + remove built images
	$(COMPOSE) --profile extras down -v --rmi local
