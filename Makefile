# One entry point for the checks CI runs. Every target is a thin wrapper over a
# command you can also run by hand: on Windows without make, copy the lines
# under the target you want.
#
#   make install   install backend + frontend dependencies
#   make check     everything CI gates on, except the browser suite
#   make e2e       Playwright smoke tests (downloads Chromium on first run)
#
# Uses whichever `python` is first on PATH, so activate your venv first.

PYTHON ?= python
BACKEND := backend
FRONTEND := frontend
export DJANGO_SETTINGS_MODULE := config.settings_test

.PHONY: install check lint test test-backend test-frontend build e2e coverage-html

install:
	cd $(BACKEND) && $(PYTHON) -m pip install -r requirements-dev.txt
	cd $(FRONTEND) && npm ci

check: lint test build

lint:
	cd $(BACKEND) && ruff check .
	cd $(FRONTEND) && npm run lint

test: test-backend test-frontend

test-backend:
	cd $(BACKEND) && $(PYTHON) manage.py check
	cd $(BACKEND) && $(PYTHON) manage.py makemigrations --check --dry-run
	cd $(BACKEND) && coverage run manage.py test --noinput
	cd $(BACKEND) && coverage report

test-frontend:
	cd $(FRONTEND) && npm test

build:
	cd $(FRONTEND) && VITE_API_URL=https://api.example.invalid/api npm run build

e2e:
	cd $(FRONTEND) && npx playwright install chromium
	cd $(FRONTEND) && npm run test:e2e

coverage-html:
	cd $(BACKEND) && coverage html && echo "open backend/htmlcov/index.html"
	cd $(FRONTEND) && npm run test:coverage && echo "open frontend/coverage/index.html"
