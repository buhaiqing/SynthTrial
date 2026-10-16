PYTHON ?= /usr/local/bin/python3
.PHONY: test lint run
test:
	PYTHONPATH=src $(PYTHON) -m pytest -v tests/
lint:
	ruff check src tests
run:
	PYTHONPATH=src $(PYTHON) -m st_platform.cli.stctl demo
