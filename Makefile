PYTHON ?= python3

.PHONY: install install-dev run test lint check build clean

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev,build]"

run:
	$(PYTHON) -m shuttle_s3

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

check: test lint
	$(PYTHON) -m compileall -q src tests scripts

build:
	$(PYTHON) scripts/package_release.py

clean:
	$(PYTHON) -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('build', 'dist', 'artifacts')]"

