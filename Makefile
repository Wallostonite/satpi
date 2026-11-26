.PHONY: install lint typecheck test cycle serve docker clean

install:
	pip install -e ".[dev]"

lint:
	ruff check src tests

format:
	ruff check --fix src tests && ruff format src tests

typecheck:
	mypy src/satpi

test:
	pytest -m "not ml and not network" --cov=satpi

test-all:
	pytest

cycle:
	satpi run-cycle

serve:
	satpi serve

docker:
	docker compose -f docker/docker-compose.yml up --build

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build *.egg-info
