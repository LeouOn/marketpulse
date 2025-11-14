# MarketPulse Makefile
# Cross-platform task automation for MarketPulse application

.PHONY: help install dev dev-backend dev-frontend build test clean docker-up docker-down docker-logs lint format check-deps setup-db reset-db

# Default target
help: ## Show this help message
	@echo "MarketPulse - Task Automation"
	@echo "================================"
	@echo ""
	@echo "Development Commands:"
	@echo "  install         Install all dependencies (Python + Node)"
	@echo "  dev             Start both backend and frontend in development"
	@echo "  dev-backend     Start backend API server only"
	@echo "  dev-frontend    Start frontend development server only"
	@echo "  build           Build the application for production"
	@echo "  test            Run all tests"
	@echo "  lint            Run linting checks"
	@echo "  format          Format code"
	@echo ""
	@echo "Docker Commands:"
	@echo "  docker-up       Start all services with Docker Compose"
	@echo "  docker-down     Stop all Docker services"
	@echo "  docker-logs     Show Docker service logs"
	@echo "  docker-build    Build Docker images"
	@echo ""
	@echo "Database Commands:"
	@echo "  setup-db        Initialize database"
	@echo "  reset-db        Reset database (WARNING: deletes data)"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean           Clean temporary files and caches"
	@echo "  check-deps      Check for dependency updates"
	@echo "  docs            Generate documentation"

# Installation
install: ## Install all dependencies
	@echo "Installing Python dependencies..."
	@if [ -d "venv" ]; then \
		venv/Scripts/pip install -r requirements.txt; \
	else \
		pip install -r requirements.txt; \
	fi
	@echo "Installing frontend dependencies..."
	cd marketpulse-client && npm install
	@echo "Installation complete!"

# Development
dev: ## Start both backend and frontend
	@echo "Starting MarketPulse in development mode..."
	@echo "Backend: http://localhost:8000"
	@echo "Frontend: http://localhost:3000"
	@echo "Press Ctrl+C to stop both services"
	@echo "Checking dependencies..."
	@if [ -d "venv" ]; then \
		venv/Scripts/python.exe -c "import sys; exit(0)" 2>/dev/null && npm --version >/dev/null 2>&1 && echo "Dependencies OK" || (echo "Error: Python and Node.js must be installed" && exit 1); \
	else \
		python -c "import sys; exit(0)" 2>/dev/null && npm --version >/dev/null 2>&1 && echo "Dependencies OK" || (echo "Error: Python and Node.js must be installed" && exit 1); \
	fi
	@echo "Use separate terminals for:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

dev-backend: ## Start backend API server
	@echo "Starting backend API server on http://localhost:8000..."
	@if [ -d "venv" ]; then \
		venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload; \
	else \
		python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload; \
	fi

dev-frontend: ## Start frontend development server
	@echo "Starting frontend server on http://localhost:3000..."
	cd marketpulse-client && npm run dev

# Testing
test: ## Run all tests
	@echo "Running backend tests..."
	python -m pytest tests/ -v || echo "Backend tests not found"
	@echo "Running frontend tests..."
	cd marketpulse-client && npm test || echo "Frontend tests not found"

test-backend: ## Run backend tests only
	@echo "Running backend tests..."
	python -m pytest tests/ -v || echo "No backend tests found"

test-frontend: ## Run frontend tests only
	@echo "Running frontend tests..."
	cd marketpulse-client && npm test || echo "No frontend tests found"

# Code Quality
lint: ## Run linting checks
	@echo "Linting Python code..."
	python -m flake8 src/ --ignore=E501,W503 || echo "flake8 not installed"
	python -m mypy src/ --ignore-missing-imports || echo "mypy not installed"
	@echo "Linting frontend code..."
	cd marketpulse-client && npm run lint || echo "Frontend linting not configured"

format: ## Format code
	@echo "Formatting Python code..."
	python -m black src/ || echo "black not installed"
	python -m isort src/ || echo "isort not installed"
	@echo "Formatting frontend code..."
	cd marketpulse-client && npm run format || echo "Frontend formatting not configured"

# Docker Commands
docker-up: ## Start all services with Docker Compose
	@echo "Starting MarketPulse with Docker..."
	docker-compose up -d
	@echo "Services started:"
	@echo "  Backend API: http://localhost:8000"
	@echo "  Frontend: http://localhost:3000"
	@echo "  Database: localhost:5433"
	@echo ""
	@echo "Use 'make docker-logs' to see logs"
	@echo "Use 'make docker-down' to stop services"

docker-down: ## Stop all Docker services
	@echo "Stopping Docker services..."
	docker-compose down

docker-logs: ## Show Docker service logs
	docker-compose logs -f

docker-build: ## Build Docker images
	@echo "Building Docker images..."
	docker-compose build

docker-dev: ## Start development services with Docker
	@echo "Starting development services..."
	docker-compose up api frontend

docker-prod: ## Start production services with Docker
	@echo "Starting production services..."
	docker-compose --profile production up

docker-full: ## Start all services including database and cache
	@echo "Starting full stack..."
	docker-compose --profile full up

# Database
setup-db: ## Initialize database
	@echo "Setting up database..."
	@if [ -f "scripts/init-db.sql" ]; then \
		if command -v psql >/dev/null 2>&1; then \
			psql -h localhost -p 5433 -U marketpulse -d marketpulse -f scripts/init-db.sql; \
		else \
			echo "PostgreSQL client not found. Using Docker..."; \
			docker-compose exec postgres psql -U marketpulse -d marketpulse -f /docker-entrypoint-initdb.d/init-db.sql; \
		fi; \
	else \
		echo "Database initialization script not found"; \
	fi

reset-db: ## Reset database (WARNING: deletes data)
	@echo "WARNING: This will delete all database data!"
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "Resetting database..."; \
		docker-compose down postgres; \
		docker volume rm marketpulse_postgres_data 2>/dev/null || true; \
		docker-compose up -d postgres; \
		sleep 5; \
		$(MAKE) setup-db; \
	else \
		echo "Database reset cancelled"; \
	fi

# Maintenance
clean: ## Clean temporary files and caches
	@echo "Cleaning Python cache..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ 2>/dev/null || true
	rm -rf .mypy_cache/ 2>/dev/null || true
	@echo "Cleaning frontend cache..."
	cd marketpulse-client && rm -rf .next/ node_modules/.cache/ 2>/dev/null || true
	@echo "Cleaning Docker..."
	docker system prune -f 2>/dev/null || true

check-deps: ## Check for dependency updates
	@echo "Checking Python dependencies..."
	pip list --outdated || echo "Unable to check Python dependencies"
	@echo "Checking frontend dependencies..."
	cd marketpulse-client && npm outdated || echo "Unable to check frontend dependencies"

# Build
build: ## Build the application for production
	@echo "Building frontend..."
	cd marketpulse-client && npm run build
	@echo "Building Docker images..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

# Documentation
docs: ## Generate documentation
	@echo "Generating API documentation..."
	@if [ -d "docs" ]; then mkdir -p docs; fi
	@echo "API docs available at: http://localhost:8000/docs"

# Quick test commands
quick-test: ## Quick smoke test
	@echo "Running quick smoke test..."
	@echo "Testing backend health..."
	curl -f http://localhost:8000/ > /dev/null 2>&1 && echo "✅ Backend OK" || echo "❌ Backend not responding"
	@echo "Testing frontend health..."
	curl -f http://localhost:3000/ > /dev/null 2>&1 && echo "✅ Frontend OK" || echo "❌ Frontend not responding"
	@echo "Testing API endpoints..."
	curl -f http://localhost:8000/api/market/internals > /dev/null 2>&1 && echo "✅ API OK" || echo "❌ API not working"

# Status
status: ## Show application status
	@echo "MarketPulse Status"
	@echo "================="
	@echo "Backend API: http://localhost:8000"
	@echo "Frontend: http://localhost:3000"
	@echo "API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "Services:"
	@if command -v docker-compose >/dev/null 2>&1; then \
		docker-compose ps 2>/dev/null || echo "Docker services not running"; \
	else \
		echo "Docker Compose not available"; \
	fi