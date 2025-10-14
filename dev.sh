#!/bin/bash

# Development helper script for Borgmatic Web UI
# Usage: ./dev.sh [command]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Commands
cmd_start() {
    print_info "Starting development environment..."
    docker-compose up -d
    print_success "Development environment started"
    print_info "Access the application at: http://localhost:8000"
    print_info "API documentation at: http://localhost:8000/api/docs"
    echo ""
    print_info "Use './dev.sh logs' to view logs"
}

cmd_stop() {
    print_info "Stopping development environment..."
    docker-compose down
    print_success "Development environment stopped"
}

cmd_restart() {
    print_info "Restarting development environment..."
    docker-compose restart
    print_success "Development environment restarted"
}

cmd_rebuild() {
    print_info "Rebuilding containers..."
    docker-compose build --no-cache
    docker-compose up -d
    print_success "Containers rebuilt and started"
}

cmd_build() {
    print_info "Building containers (with cache)..."
    docker-compose build
    print_success "Build complete"
}

cmd_logs() {
    print_info "Showing logs (Ctrl+C to exit)..."
    docker-compose logs -f --tail=100
}

cmd_shell() {
    print_info "Opening shell in container..."
    docker-compose exec borgmatic-ui bash
}

cmd_test() {
    print_info "Running tests..."
    if [ -f "./test.sh" ]; then
        ./test.sh http://localhost:8000
    else
        print_warning "test.sh not found, running Python tests directly..."
        if [ -f "./test_app.py" ]; then
            python3 test_app.py http://localhost:8000
        else
            print_error "No test files found"
            exit 1
        fi
    fi
}

cmd_clean() {
    print_warning "This will remove all containers, volumes, and images"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cleaning up..."
        docker-compose down -v
        docker system prune -f
        print_success "Cleanup complete"
    else
        print_info "Cleanup cancelled"
    fi
}

cmd_status() {
    print_info "Container status:"
    docker-compose ps
    echo ""
    print_info "Docker stats:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" $(docker-compose ps -q) 2>/dev/null || print_warning "No containers running"
}

cmd_frontend() {
    print_info "Building frontend..."
    cd frontend
    if [ ! -d "node_modules" ]; then
        print_info "Installing frontend dependencies..."
        npm install
    fi
    npm run build
    cd ..
    print_success "Frontend built successfully"
    print_info "Restarting container to pick up changes..."
    docker-compose restart
}

cmd_backend() {
    print_info "Restarting backend (hot-reload should pick up changes)..."
    docker-compose restart
    print_success "Backend restarted"
}

cmd_db() {
    print_info "Opening database shell..."
    docker-compose exec borgmatic-ui bash -c "cd /app/data && sqlite3 borgmatic.db"
}

cmd_init() {
    print_info "Initializing development environment..."

    # Create necessary directories
    mkdir -p config backups logs data
    print_success "Directories created"

    # Check if .env exists
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            print_info "Creating .env from .env.example..."
            cp .env.example .env
            print_success ".env file created"
        else
            print_warning ".env.example not found, skipping .env creation"
        fi
    else
        print_info ".env already exists"
    fi

    # Build frontend if needed
    if [ ! -d "frontend/build" ]; then
        print_info "Frontend not built, building now..."
        cmd_frontend
    fi

    # Build and start containers
    print_info "Building containers..."
    docker-compose build

    print_info "Starting containers..."
    docker-compose up -d

    print_success "Development environment initialized!"
    print_info "Access at: http://localhost:8000"
    print_info "Default credentials: admin / admin123"
}

cmd_help() {
    cat << EOF
Borgmatic Web UI - Development Helper Script

Usage: ./dev.sh [command]

Commands:
  init        Initialize development environment (first-time setup)
  start       Start the development environment
  stop        Stop the development environment
  restart     Restart the containers
  rebuild     Rebuild containers from scratch (no cache)
  build       Build containers (with cache)
  logs        Show container logs (follow mode)
  shell       Open a bash shell in the container
  test        Run the test suite
  status      Show container status and resource usage
  frontend    Rebuild frontend and restart container
  backend     Restart backend (hot-reload should work)
  db          Open SQLite database shell
  clean       Remove all containers, volumes, and cleanup
  help        Show this help message

Examples:
  ./dev.sh init       # First-time setup
  ./dev.sh start      # Start development
  ./dev.sh logs       # Watch logs
  ./dev.sh frontend   # After frontend changes
  ./dev.sh test       # Run tests

For more information, check the README.md
EOF
}

# Main script logic
case "${1:-help}" in
    init)
        cmd_init
        ;;
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    rebuild)
        cmd_rebuild
        ;;
    build)
        cmd_build
        ;;
    logs)
        cmd_logs
        ;;
    shell)
        cmd_shell
        ;;
    test)
        cmd_test
        ;;
    status)
        cmd_status
        ;;
    frontend)
        cmd_frontend
        ;;
    backend)
        cmd_backend
        ;;
    db)
        cmd_db
        ;;
    clean)
        cmd_clean
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        cmd_help
        exit 1
        ;;
esac
