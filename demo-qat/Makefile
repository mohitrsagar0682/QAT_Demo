.PHONY: setup build run run-software run-accelerated run-both dashboard stop clean logs status help

# Default target
help:
	@echo ""
	@echo "  Intel Xeon 6 QAT Demo — Make Targets"
	@echo "  ======================================"
	@echo "  make setup           Check dependencies"
	@echo "  make build           Build Docker images"
	@echo "  make run             Build + start full stack"
	@echo "  make run-software    Run software-only benchmark (curl)"
	@echo "  make run-accelerated Run QAT-accelerated benchmark (curl)"
	@echo "  make run-both        Run full comparison benchmark (curl)"
	@echo "  make dashboard       Open Grafana in browser"
	@echo "  make stop            Stop all containers"
	@echo "  make clean           Stop + remove volumes + images"
	@echo "  make logs            Tail backend logs"
	@echo "  make status          Check backend API status"
	@echo ""

setup:
	@echo "🔧 Checking dependencies..."
	@command -v docker >/dev/null 2>&1 || { echo "❌ Docker required. Install from https://docs.docker.com/get-docker/"; exit 1; }
	@(docker compose version >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1) || { echo "❌ Docker Compose required."; exit 1; }
	@command -v curl >/dev/null 2>&1 || { echo "❌ curl required for benchmark targets."; exit 1; }
	@echo "✅ All dependencies found"
	@echo ""
	@docker --version
	@docker compose version 2>/dev/null || docker-compose version

build:
	@echo "🔨 Building Docker images..."
	docker compose build

run: setup build
	@echo "🚀 Starting Intel Xeon 6 QAT Demo Stack..."
	docker compose up -d
	@echo ""
	@sleep 3
	@echo "╔══════════════════════════════════════════════════╗"
	@echo "║        Intel Xeon 6 QAT Demo — LIVE  ⚡          ║"
	@echo "╠══════════════════════════════════════════════════╣"
	@echo "║  Demo UI:       http://localhost:8000            ║"
	@echo "║  API Docs:      http://localhost:8000/docs       ║"
	@echo "║  Grafana:       http://localhost:3000            ║"
	@echo "║    user: admin  /  password: intel2024           ║"
	@echo "║  Prometheus:    http://localhost:9090            ║"
	@echo "║  Metrics:       http://localhost:8001/metrics    ║"
	@echo "╚══════════════════════════════════════════════════╝"
	@echo ""
	@echo "  Run 'make dashboard' to open Grafana automatically"
	@echo "  Run 'make logs' to follow backend output"
	@echo ""

run-software:
	@echo "▶  Running software-only benchmark (30s)..."
	@echo ""
	@curl -s -X POST http://localhost:8000/api/benchmark \
		-H "Content-Type: application/json" \
		-d '{"mode":"software","duration":30,"chunk_size_mb":10}' | python3 -m json.tool
	@echo ""

run-accelerated:
	@echo "⚡  Running QAT-accelerated benchmark (30s)..."
	@echo ""
	@curl -s -X POST http://localhost:8000/api/benchmark \
		-H "Content-Type: application/json" \
		-d '{"mode":"accelerated","duration":30,"chunk_size_mb":10}' | python3 -m json.tool
	@echo ""

run-both:
	@echo "📊  Running full comparison benchmark (software + QAT, 30s each)..."
	@echo ""
	@curl -s -X POST http://localhost:8000/api/benchmark \
		-H "Content-Type: application/json" \
		-d '{"mode":"both","duration":30,"chunk_size_mb":10}' | python3 -m json.tool
	@echo ""

dashboard:
	@echo "📈  Opening Grafana dashboard..."
	@open http://localhost:3000 2>/dev/null || xdg-open http://localhost:3000 2>/dev/null || \
		echo "  ➜ Open http://localhost:3000 in your browser (login: admin / intel2024)"

stop:
	@echo "🛑  Stopping QAT Demo stack..."
	docker compose down
	@echo "✅  All containers stopped"

clean:
	@echo "🧹  Cleaning up containers, volumes, and images..."
	docker compose down -v --remove-orphans
	@docker rmi demo-qat-backend 2>/dev/null || true
	@echo "✅  Clean complete"

logs:
	docker compose logs -f backend

status:
	@echo "📡  Checking backend status..."
	@curl -s http://localhost:8000/api/status | python3 -m json.tool 2>/dev/null || \
		echo "⚠️  Backend not responding. Run 'make run' first."
