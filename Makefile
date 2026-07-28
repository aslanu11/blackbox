# F1 — golden-path targets. Each is a thin wrapper; read the command, not the make.
# Windows without `make`: just run the commands directly.

PY  ?= .venv/bin/python
BB  ?= .venv/bin/bb
ifeq ($(OS),Windows_NT)
	PY = .venv/Scripts/python.exe
	BB = .venv/Scripts/bb.exe
endif

.PHONY: setup fixture demo-fixture run test export clean

## Create the venv and install the package.
setup:
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	$(BB) doctor || true

## Regenerate the deterministic synthetic fight.
fixture:
	$(BB) fixture

## The whole machine, end to end, on synthetic data. No network, no footage.
demo-fixture: fixture
	$(BB) telemetry --fight-id fixture-001
	$(BB) events    --fight-id fixture-001
	$(BB) momentum  --fight-id fixture-001
	$(BB) scorecard --fight-id fixture-001
	$(BB) fuse      --fight-id fixture-001
	$(BB) overlay   --fight-id fixture-001
	$(BB) export
	@echo ""
	@echo "  Fixture pipeline complete. Now:  cd web && npm run dev"
	@echo ""

## Full pipeline for one real fight:  make run FIGHT=pl-e04-f2
run:
	@test -n "$(FIGHT)" || (echo "usage: make run FIGHT=<fight_id>" && exit 1)
	$(BB) run --fight-id $(FIGHT)

test:
	$(PY) -m pytest

export:
	$(BB) export

## Remove derived artifacts. Leaves data/raw and the manifest alone.
clean:
	rm -rf data/processed data/frames web/public/data .pytest_cache
