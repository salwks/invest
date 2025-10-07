# Makefile for Automated Trading System

.PHONY: help install test run clean docker-build docker-run docker-stop

help:
	@echo "Automated Trading System - Available commands:"
	@echo ""
	@echo "  make install       - Install dependencies"
	@echo "  make test          - Run tests"
	@echo "  make run-once      - Run single cycle"
	@echo "  make run-continuous - Run continuously"
	@echo "  make clean         - Clean generated files"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-run    - Run in Docker"
	@echo "  make docker-stop   - Stop Docker container"
	@echo ""

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

test-quick:
	pytest tests/test_rules.py -v

run-once:
	python -m app.main --mode once

run-continuous:
	python -m app.main --mode continuous

clean:
	rm -rf __pycache__ app/__pycache__ tests/__pycache__
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -f data/*.db
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

docker-build:
	docker-compose build

docker-run:
	docker-compose up -d autotrader

docker-run-once:
	docker-compose run --rm autotrader-once

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f autotrader

docker-test:
	docker-compose --profile test run --rm autotrader-test

lint:
	ruff check app/ tests/

format:
	black app/ tests/
	isort app/ tests/
