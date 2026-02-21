.PHONY: help init install shell tests e2e-test unit-test integration-test dummy-component-integration-test docker-build docker-up docker-down docker-logs docker-ps docker-clean

DOCKER_COMPOSE = docker compose -f docker/docker-compose.yml --env-file docker/.env
LOAD_ENV = set -a && . docker/.env && set +a
PIPENV_PIPFILE = config/Pipfile
PYTEST_CONFIG = config/pyproject.toml

help:
	@echo "make init            - Установить pipenv и зависимости"
	@echo "make tests           - Docker up + pytest + docker-down"
	@echo "make e2e-test        - E2E тесты"
	@echo "make unit-test       - Unit тесты"
	@echo "make integration-test - Интеграционные тесты"
	@echo "make dummy-component-integration-test - Интеграционные тесты DummyComponent + брокер"
	@echo "make docker-build    - Собрать образы"
	@echo "make docker-up       - Запустить контейнеры"
	@echo "make docker-down     - Остановить"
	@echo "make docker-logs     - Логи"
	@echo "make docker-ps       - Статус"
	@echo "make docker-clean    - Очистка"

init:
	@command -v pipenv >/dev/null 2>&1 || pip install pipenv
	PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv install --dev

tests:
	@test -f docker/.env || cp docker/example.env docker/.env
	@$(LOAD_ENV) && export BROKER_TYPE MQTT_PORT KAFKA_PORT && $(MAKE) docker-up
	@sleep 20
	@$(LOAD_ENV) && PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv run pytest -c $(PYTEST_CONFIG) tests/ -v
	-$(MAKE) docker-down

e2e-test:
	@test -f docker/.env || cp docker/example.env docker/.env
	@$(LOAD_ENV) && export BROKER_TYPE MQTT_PORT KAFKA_PORT && $(MAKE) docker-up
	@sleep 20
	@$(LOAD_ENV) && PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv run pytest -c $(PYTEST_CONFIG) tests/e2e/ -v
	-$(MAKE) docker-down

unit-test:
	@test -f docker/.env || cp docker/example.env docker/.env
	@$(LOAD_ENV) && export BROKER_TYPE MQTT_PORT KAFKA_PORT && $(MAKE) docker-up
	@sleep 20
	@$(LOAD_ENV) && PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv run pytest -c $(PYTEST_CONFIG) tests/unit/ -v
	-$(MAKE) docker-down

integration-test:
	@test -f docker/.env || cp docker/example.env docker/.env
	@$(LOAD_ENV) && export BROKER_TYPE MQTT_PORT KAFKA_PORT && $(MAKE) docker-up
	@sleep 20
	@$(LOAD_ENV) && PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv run pytest -c $(PYTEST_CONFIG) tests/integration/ -v
	-$(MAKE) docker-down

dummy-component-integration-test:
	@test -f docker/.env || cp docker/example.env docker/.env
	@$(LOAD_ENV) && export BROKER_TYPE MQTT_PORT KAFKA_PORT && $(MAKE) docker-up
	@sleep 20
	@$(LOAD_ENV) && PIPENV_PIPFILE=$(PIPENV_PIPFILE) pipenv run pytest -c $(PYTEST_CONFIG) components/dummy_component/tests/integration/ -v
	-$(MAKE) docker-down

docker-build:
	@test -f docker/.env || cp docker/example.env docker/.env
	$(DOCKER_COMPOSE) --profile kafka build
	$(DOCKER_COMPOSE) --profile mqtt build

docker-up:
	@test -f docker/.env || cp docker/example.env docker/.env
	@profile=$${BROKER_TYPE:-$$(grep '^BROKER_TYPE=' docker/.env 2>/dev/null | cut -d= -f2)}; \
	profile=$${profile:-kafka}; \
	$(DOCKER_COMPOSE) --profile $$profile up -d --build

docker-down:
	-$(DOCKER_COMPOSE) --profile kafka down 2>/dev/null
	-$(DOCKER_COMPOSE) --profile mqtt down 2>/dev/null
	-docker ps -aq --filter "label=type=drone" | xargs -r docker rm -f

docker-logs:
	$(DOCKER_COMPOSE) --profile $$(grep BROKER_TYPE docker/.env | cut -d= -f2) logs -f

docker-ps:
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

docker-clean:
	-$(DOCKER_COMPOSE) --profile kafka down -v --rmi local 2>/dev/null
	-$(DOCKER_COMPOSE) --profile mqtt down -v --rmi local 2>/dev/null
	-docker ps -aq --filter "label=type=drone" | xargs -r docker rm -f
	-docker images -q "drones_v2*" | xargs -r docker rmi -f
