.PHONY: help \
	up up-all up-broker up-gcs up-drone-port \
	down down-all down-broker down-gcs down-drone-port \
	stop stop-all stop-broker stop-gcs stop-drone-port \
	ps ps-all ps-broker ps-gcs ps-drone-port \
	log log-all log-broker log-gcs log-drone-port \
	logs logs-all logs-broker logs-gcs logs-drone-port \
	tests \
	unit-test unit-test-broker unit-test-gcs unit-test-drone-port \
	integration-test integration-test-no-up \
	integration-test-broker integration-test-broker-no-up \
	integration-test-gcs integration-test-gcs-no-up \
	integration-test-drone-port integration-test-drone-port-no-up

PROJECT_ROOT := $(CURDIR)
PIPENV_PIPFILE := config/Pipfile
PYTEST_CONFIG := config/pyproject.toml

SYSTEMS := drone_port gcs
MULTI_OUTPUT := .generated/all

BROKER_COMPOSE := docker compose -f docker/docker-compose.yml --env-file docker/.env
MULTI_COMPOSE := docker compose -f $(MULTI_OUTPUT)/docker-compose.yml --env-file $(MULTI_OUTPUT)/.env
GCS_COMPOSE := docker compose -f systems/gcs/.generated/docker-compose.yml --env-file systems/gcs/.generated/.env
DRONE_PORT_COMPOSE := docker compose -f systems/drone_port/.generated/docker-compose.yml --env-file systems/drone_port/.generated/.env

help:
	@echo "Запуск:"
	@echo "  make up                 - Запустить broker + drone_port + gcs"
	@echo "  make up-broker          - Запустить только broker"
	@echo "  make up-drone-port      - Запустить только DronePort + broker"
	@echo "  make up-gcs             - Запустить только GCS + broker"
	@echo ""
	@echo "Docker:"
	@echo "  make down              - docker compose down для broker + drone_port + gcs"
	@echo "  make stop              - docker compose stop для broker + drone_port + gcs"
	@echo "  make ps                - docker compose ps для broker + drone_port + gcs"
	@echo "  make log               - docker compose logs -f для broker + drone_port + gcs"
	@echo "  make down-broker|stop-broker|ps-broker|log-broker"
	@echo "  make down-drone-port|stop-drone-port|ps-drone-port|log-drone-port"
	@echo "  make down-gcs|stop-gcs|ps-gcs|log-gcs"
	@echo ""
	@echo "Unit-тесты:"
	@echo "  make unit-test          - Все unit-тесты: broker + drone_port + gcs"
	@echo "  make unit-test-broker   - Unit-тесты broker/SDK"
	@echo "  make unit-test-drone-port - Unit-тесты DronePort"
	@echo "  make unit-test-gcs      - Unit-тесты GCS"
	@echo ""
	@echo "Интеграционные тесты:"
	@echo "  make integration-test   - Все integration-тесты: broker + drone_port + gcs"
	@echo "  make integration-test-broker - Integration-тесты broker"
	@echo "  make integration-test-drone-port - Integration-тесты DronePort"
	@echo "  make integration-test-gcs - Integration-тесты GCS"
	@echo "  make integration-test-no-up - Integration-тесты без управления Docker"
	@echo "  make tests              - Все тесты: unit-test + integration-test"

up: up-all

up-all:
	@test -f docker/.env || cp docker/example.env docker/.env
	@PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv run python scripts/prepare_multi.py \
		--systems $(SYSTEMS) --output $(MULTI_OUTPUT)
	@set -a && . $(MULTI_OUTPUT)/.env && set +a && \
		$(MULTI_COMPOSE) --profile $${BROKER_TYPE:-mqtt} up -d --build --remove-orphans

up-broker:
	@test -f docker/.env || cp docker/example.env docker/.env
	@set -a && . docker/.env && set +a && \
		profiles="--profile $${BROKER_TYPE:-mqtt}"; \
		[ "$${ENABLE_FABRIC:-false}" = "true" ] && profiles="$$profiles --profile fabric"; \
		$(BROKER_COMPOSE) $$profiles up -d --build

up-gcs:
	@$(MAKE) -C systems/gcs docker-up PROJECT_ROOT=$(PROJECT_ROOT)

up-drone-port:
	@$(MAKE) -C systems/drone_port docker-up PROJECT_ROOT=$(PROJECT_ROOT)

down: down-all

down-all:
	@if [ -f "$(MULTI_OUTPUT)/docker-compose.yml" ]; then \
		$(MULTI_COMPOSE) --profile mqtt --profile fabric down; \
	else \
		echo "$(MULTI_OUTPUT)/docker-compose.yml not found. Run: make up"; \
	fi

down-broker:
	-$(BROKER_COMPOSE) --profile mqtt --profile fabric down 2>/dev/null

down-gcs:
	@$(MAKE) -C systems/gcs docker-down PROJECT_ROOT=$(PROJECT_ROOT)

down-drone-port:
	@$(MAKE) -C systems/drone_port docker-down PROJECT_ROOT=$(PROJECT_ROOT)

stop: stop-all

stop-all:
	@if [ -f "$(MULTI_OUTPUT)/docker-compose.yml" ]; then \
		$(MULTI_COMPOSE) --profile mqtt --profile fabric stop; \
	else \
		echo "$(MULTI_OUTPUT)/docker-compose.yml not found. Run: make up"; \
	fi

stop-broker:
	-$(BROKER_COMPOSE) --profile mqtt --profile fabric stop 2>/dev/null

stop-gcs:
	@if [ -f "systems/gcs/.generated/docker-compose.yml" ]; then \
		$(GCS_COMPOSE) --profile mqtt stop; \
	else \
		echo "systems/gcs/.generated/docker-compose.yml not found. Run: make up-gcs"; \
	fi

stop-drone-port:
	@if [ -f "systems/drone_port/.generated/docker-compose.yml" ]; then \
		$(DRONE_PORT_COMPOSE) --profile mqtt stop; \
	else \
		echo "systems/drone_port/.generated/docker-compose.yml not found. Run: make up-drone-port"; \
	fi

ps: ps-all

ps-all:
	@if [ -f "$(MULTI_OUTPUT)/docker-compose.yml" ]; then \
		$(MULTI_COMPOSE) --profile mqtt --profile fabric ps; \
	else \
		echo "$(MULTI_OUTPUT)/docker-compose.yml not found. Run: make up"; \
	fi

ps-broker:
	@$(BROKER_COMPOSE) --profile mqtt --profile fabric ps

ps-gcs:
	@if [ -f "systems/gcs/.generated/docker-compose.yml" ]; then \
		$(GCS_COMPOSE) --profile mqtt ps; \
	else \
		echo "systems/gcs/.generated/docker-compose.yml not found. Run: make up-gcs"; \
	fi

ps-drone-port:
	@if [ -f "systems/drone_port/.generated/docker-compose.yml" ]; then \
		$(DRONE_PORT_COMPOSE) --profile mqtt ps; \
	else \
		echo "systems/drone_port/.generated/docker-compose.yml not found. Run: make up-drone-port"; \
	fi

log: log-all
logs: log
log-all:
	@if [ -f "$(MULTI_OUTPUT)/docker-compose.yml" ]; then \
		$(MULTI_COMPOSE) --profile mqtt --profile fabric logs -f; \
	else \
		echo "$(MULTI_OUTPUT)/docker-compose.yml not found. Run: make up"; \
	fi
logs-all: log-all

log-broker:
	@$(BROKER_COMPOSE) --profile mqtt --profile fabric logs -f
logs-broker: log-broker

log-gcs:
	@$(MAKE) -C systems/gcs docker-logs PROJECT_ROOT=$(PROJECT_ROOT)
logs-gcs: log-gcs

log-drone-port:
	@$(MAKE) -C systems/drone_port docker-logs PROJECT_ROOT=$(PROJECT_ROOT)
logs-drone-port: log-drone-port

unit-test: unit-test-broker unit-test-drone-port unit-test-gcs

unit-test-broker:
	@PYTHONPATH=. PIPENV_PIPFILE=$(PIPENV_PIPFILE) \
		pipenv run pytest -c $(PYTEST_CONFIG) tests/unit

unit-test-gcs:
	@$(MAKE) -C systems/gcs unit-test PROJECT_ROOT=$(PROJECT_ROOT)

unit-test-drone-port:
	@$(MAKE) -C systems/drone_port unit-test PROJECT_ROOT=$(PROJECT_ROOT)

tests: unit-test integration-test

integration-test: integration-test-broker integration-test-drone-port integration-test-gcs

integration-test-no-up: integration-test-broker-no-up integration-test-drone-port-no-up integration-test-gcs-no-up

integration-test-broker: up-broker
	@status=0; \
	$(MAKE) integration-test-broker-no-up || status=$$?; \
	$(BROKER_COMPOSE) --profile mqtt --profile fabric down >/dev/null 2>&1 || true; \
	exit $$status

integration-test-broker-no-up:
	@set -a && . docker/.env && set +a && \
		PYTHONPATH=. PIPENV_PIPFILE=$(PIPENV_PIPFILE) \
		pipenv run pytest -c $(PYTEST_CONFIG) tests/integration

integration-test-gcs:
	@status=0; \
	$(MAKE) -C systems/gcs integration-test PROJECT_ROOT=$(PROJECT_ROOT) || status=$$?; \
	$(MAKE) -C systems/gcs docker-down >/dev/null 2>&1 || true; \
	exit $$status

integration-test-gcs-no-up:
	@$(MAKE) -C systems/gcs integration-test-no-up PROJECT_ROOT=$(PROJECT_ROOT)

integration-test-drone-port:
	@status=0; \
	$(MAKE) -C systems/drone_port integration-test PROJECT_ROOT=$(PROJECT_ROOT) || status=$$?; \
	$(MAKE) -C systems/drone_port docker-down >/dev/null 2>&1 || true; \
	exit $$status

integration-test-drone-port-no-up:
	@$(MAKE) -C systems/drone_port integration-test-no-up PROJECT_ROOT=$(PROJECT_ROOT)
