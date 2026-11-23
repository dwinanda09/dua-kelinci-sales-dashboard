# Shortcuts for the Docker stack. Run `make` to list them.
.PHONY: help run down stop test

COMPOSE := docker compose

help:
	@echo "make run    start the backend, wait until it is healthy, then build and start the frontend"
	@echo "            (and the Telegram bot when TELEGRAM_BOT_TOKEN is set in .env)"
	@echo "make down   stop and remove the containers (data is kept in the Docker volume)"
	@echo "make stop   stop every process of this project: containers and local dev servers"
	@echo "make test   run the backend unit tests in Docker (fails below 98% coverage)"

run:
	@./scripts/start.sh

down:
	$(COMPOSE) --profile bot --profile test down --remove-orphans

stop:
	@./scripts/stop.sh

test:
	$(COMPOSE) --profile test build test
	$(COMPOSE) --profile test run --rm test
