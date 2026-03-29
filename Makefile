.PHONY: test lint build dev clean

# ─── 后端 ───

test:
	pytest tests/ -q --tb=short

lint:
	python -m py_compile main.py
	python -m py_compile config.py
	python -m py_compile database.py

dev:
	uvicorn main:app --host 0.0.0.0 --port 9900 --reload --workers 1

# ─── 前端 ───

build:
	cd frontend && npm ci && npx tsc --noEmit && npm run build

frontend-dev:
	cd frontend && npm run dev

# ─── 组合 ───

ci: lint test build

clean:
	rm -rf frontend/dist __pycache__ .pytest_cache
	find . -name '*.pyc' -delete
