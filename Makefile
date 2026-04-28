.PHONY: smoke test

PY := .venv/bin/python

smoke:
	@$(PY) scripts/smoke_runtime.py

test:
	@PYTHONPATH=$(PWD) $(PY) -m pytest tests/ -q
