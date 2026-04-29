.PHONY: install install-dev lint format test clean run plan create upload help

# ── Setup ─────────────────────────────────────────────────────────────────────

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
	pre-commit install

# ── Quality ───────────────────────────────────────────────────────────────────

lint:
	ruff check app/ main.py tests/
	black --check app/ main.py tests/

format:
	ruff check --fix app/ main.py tests/
	black app/ main.py tests/

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

# ── Run ───────────────────────────────────────────────────────────────────────

run:
	python main.py

plan:
	python main.py --plan-only

create:
	python main.py --create-only

upload:
	python main.py --upload-only

loop:
	python main.py --mode loop

# ── Maintenance ───────────────────────────────────────────────────────────────

clean:
	python main.py --cleanup
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov .ruff_cache

check-token:
	python main.py --check-token

refresh-token:
	python main.py --refresh-token

check-quota:
	python main.py --check-quota

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker-compose build

docker-run:
	docker-compose run --rm cyberbot python main.py

docker-loop:
	docker-compose up

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo "CyberShorts Bot — available make targets:"
	@echo ""
	@echo "  install        Install runtime dependencies"
	@echo "  install-dev    Install dev dependencies + pre-commit hooks"
	@echo "  lint           Check code style (ruff + black)"
	@echo "  format         Auto-fix code style"
	@echo "  test           Run pytest with coverage"
	@echo ""
	@echo "  run            Full run: plan + create + upload"
	@echo "  plan           Plan stories only (no video)"
	@echo "  create         Create videos; skip upload"
	@echo "  upload         Upload locally saved videos"
	@echo "  loop           Run every 24 hours"
	@echo ""
	@echo "  clean          Remove generated artefacts"
	@echo "  check-token    Show YouTube token status"
	@echo "  refresh-token  Force re-authentication"
	@echo "  check-quota    Show quota cooldown status"
	@echo ""
	@echo "  docker-build   Build Docker image"
	@echo "  docker-run     Run one batch inside Docker"
	@echo "  docker-loop    Run in loop mode inside Docker"
