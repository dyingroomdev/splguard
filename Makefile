PYTHON ?= python3.11
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYTHON_BIN := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
PYTEST := $(VENV)/bin/pytest

.PHONY: dev test fmt clean

$(VENV)/bin/activate: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev]

dev: $(VENV)/bin/activate

test: dev
	$(PYTEST)

fmt: dev
	$(RUFF) check --fix .
	$(RUFF) format .

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache
