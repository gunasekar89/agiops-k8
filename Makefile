.PHONY: install test lint format check help

install:
	python3 -m pip install -e .

test:
	python3 -m pytest

lint:
	python3 -m ruff check .

format:
	python3 -m ruff format .

check: lint test

help:
	python3 -m holmes_console.cli --help

