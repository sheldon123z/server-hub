.PHONY: test lint format check build dev clean setup backup

# ─── 后端 ───

test:
	pytest tests/ -q --tb=short

test-cov:
	pytest tests/ --cov --cov-report=term-missing --cov-report=html

lint:
	ruff check .

lint-fix:
	ruff check . --fix

format:
	ruff format .

format-check:
	ruff format . --check

# lint + format 一步到位
check: lint format-check

dev:
	uvicorn main:app --host 0.0.0.0 --port 9900 --reload --workers 1

# ─── 前端 ───

build:
	cd frontend && npm ci && npx tsc --noEmit && npm run build

frontend-dev:
	cd frontend && npm run dev

# ─── 组合 ───

ci: check test build

# ─── 工具 ───

setup:
	pip install ruff pytest pytest-cov pre-commit
	pre-commit install
	@echo "✓ 开发环境就绪"

backup:
	bash scripts/backup-db.sh

clean:
	rm -rf frontend/dist __pycache__ .pytest_cache htmlcov .ruff_cache
	find . -name '*.pyc' -delete
