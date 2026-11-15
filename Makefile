.PHONY: setup seed run-api run-ui test eval check

setup:
	python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"

seed:
	python -m app.data.seed --split dev

run-api:
	uvicorn app.main:app --reload --port 8000

run-ui:
	streamlit run frontend/streamlit_app.py

test:
	pytest -m "not live" -q

eval:
	python evaluation/classification/run.py
	python evaluation/policy/run.py
	python evaluation/generation/run.py
	python evaluation/guardrails/run.py
	python evaluation/review/summarize.py

check:
	ruff check . && ruff format --check . && $(MAKE) test
