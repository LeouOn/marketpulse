#!/bin/bash
# MarketPulse Development Script for Linux/macOS
# Bash script to start development servers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Function to check if a port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to stop processes on a port
stop_port() {
    if check_port $1; then
        echo -e "${YELLOW}Stopping process on port $1...${NC}"
        lsof -ti:$1 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

# Function to show help
show_help() {
    echo -e "${GREEN}MarketPulse Development Environment${NC}"
    echo -e "${GREEN}===================================${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -b, --backend-only    Start backend only"
    echo "  -f, --frontend-only   Start frontend only"
    echo "  -d, --docker          Use Docker instead of local services"
    echo "  -p, --production     Start production stack (with -d)"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Start both backend and frontend"
    echo "  $0 --backend-only     # Start backend only"
    echo "  $0 --docker           # Start with Docker"
    echo "  $0 -d -p              # Start production stack with Docker"
}

# Parse command line arguments
BACKEND_ONLY=false
FRONTEND_ONLY=false
DOCKER=false
PRODUCTION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--backend-only)
            BACKEND_ONLY=true
            shift
            ;;
        -f|--frontend-only)
            FRONTEND_ONLY=true
            shift
            ;;
        -d|--docker)
            DOCKER=true
            shift
            ;;
        -p|--production)
            PRODUCTION=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Check if we're in the right directory
if [[ ! -f "requirements-lite.txt" ]] || [[ ! -f "marketpulse-client/package.json" ]]; then
    echo -e "${RED}Error: Please run this script from the MarketPulse root directory${NC}"
    exit 1
fi

# Docker mode
if [[ "$DOCKER" == true ]]; then
    echo -e "${YELLOW}Starting with Docker...${NC}"

    if [[ "$PRODUCTION" == true ]]; then
        echo -e "${CYAN}Starting production services...${NC}"
        docker-compose --profile production up
    else
        echo -e "${CYAN}Starting development services...${NC}"
        docker-compose up
    fi
    exit 0
fi

# Check virtual environment
if [[ -d "venv" ]]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${YELLOW}Warning: Virtual environment not found. Using system Python.${NC}"
    echo -e "${YELLOW}Run './scripts/setup.sh' to create virtual environment.${NC}"
fi

# Check if ports are available
if [[ "$BACKEND_ONLY" == false && "$FRONTEND_ONLY" == false ]]; then
    if check_port 8000; then
        echo -e "${YELLOW}Port 8000 is already in use. Stopping existing backend...${NC}"
        stop_port 8000
    fi
    if check_port 3000; then
        echo -e "${YELLOW}Port 3000 is already in use. Stopping existing frontend...${NC}"
        stop_port 3000
    fi
fi

# Function to cleanup on exit
cleanup() {
    echo -e "${YELLOW}Stopping all services...${NC}"
    jobs 2>/dev/null | wc -l | xargs -I {} kill %1 2>/dev/null || true
    wait 2>/dev/null || true
    stop_port 8000
    stop_port 3000
    echo -e "${GREEN}All services stopped.${NC}"
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Start backend only
if [[ "$BACKEND_ONLY" == true ]]; then
    if check_port 8000; then
        echo -e "${YELLOW}Port 8000 is already in use. Stopping existing backend...${NC}"
        stop_port 8000
    fi

    echo -e "${CYAN}Starting Backend API Server...${NC}"
    echo -e "${GRAY}Backend will be available at: http://localhost:8000${NC}"
    echo -e "${GRAY}API Documentation: http://localhost:8000/docs${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
    echo ""

    python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
    exit 0
fi

# Start frontend only
if [[ "$FRONTEND_ONLY" == true ]]; then
    if check_port 3000; then
        echo -e "${YELLOW}Port 3000 is already in use. Stopping existing frontend...${NC}"
        stop_port 3000
    fi

    echo -e "${CYAN}Starting Frontend Development Server...${NC}"
    echo -e "${GRAY}Frontend will be available at: http://localhost:3000${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
    echo ""

    cd marketpulse-client
    npm run dev
    cd ..
    exit 0
fi

# Start both backend and frontend
echo -e "${CYAN}Starting MarketPulse in Development Mode...${NC}"
echo ""

# Start backend in background
echo -e "${YELLOW}Starting backend...${NC}"
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend in background
echo -e "${YELLOW}Starting frontend...${NC}"
cd marketpulse-client
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait a moment for services to start
sleep 3

# Check if services started successfully
echo -e "${YELLOW}Checking service status...${NC}"

if check_port 8000; then
    echo -e "${GREEN}✅ Backend API is running at http://localhost:8000${NC}"
    echo -e "${GRAY}   API Docs: http://localhost:8000/docs${NC}"
else
    echo -e "${RED}❌ Backend API failed to start${NC}"
fi

if check_port 3000; then
    echo -e "${GREEN}✅ Frontend is running at http://localhost:3000${NC}"
else
    echo -e "${RED}❌ Frontend failed to start${NC}"
fi

echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo -e "${GRAY}Or run './scripts/stop.sh' to stop from another terminal${NC}"

# Wait for background jobs
wait