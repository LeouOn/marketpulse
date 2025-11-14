#!/bin/bash
# MarketPulse Docker Management Script for Linux/macOS
# Bash script to manage Docker containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Default action
ACTION="up"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--build)
            BUILD=true
            shift
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        -l|--logs)
            LOGS=true
            shift
            ;;
        -p|--production)
            PRODUCTION=true
            shift
            ;;
        -f|--full)
            FULL=true
            shift
            ;;
        up|down|restart|status)
            ACTION=$1
            shift
            ;;
        -h|--help)
            echo -e "${GREEN}MarketPulse Docker Management${NC}"
            echo -e "${GREEN}==========================${NC}"
            echo ""
            echo "Usage: $0 [ACTION] [OPTIONS]"
            echo ""
            echo "Actions:"
            echo "  up                 Start services (default)"
            echo "  down               Stop services"
            echo "  restart            Restart services"
            echo "  status             Show service status"
            echo ""
            echo "Options:"
            echo "  -b, --build        Build Docker images"
            echo "  -l, --logs         Show logs"
            echo "  -p, --production   Start production stack"
            echo "  -f, --full         Start full stack (with database)"
            echo "  -c, --clean        Clean Docker resources"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                      # Start development services"
            echo "  $0 up -p               # Start production stack"
            echo "  $0 down                # Stop services"
            echo "  $0 -l                  # Show logs"
            echo "  $0 -c                  # Clean up"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}MarketPulse Docker Management${NC}"
echo -e "${GREEN}==========================${NC}"
echo ""

# Check if Docker is available
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker not found. Please install Docker.${NC}"
    exit 1
fi

if ! command -v docker compose >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker Compose not found. Please install Docker Compose.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker environment detected${NC}"

# Check if we're in the right directory
if [[ ! -f "docker-compose.yml" ]]; then
    echo -e "${RED}Error: Please run this script from the MarketPulse root directory${NC}"
    exit 1
fi

# Build images
if [[ "$BUILD" == true ]]; then
    echo -e "${YELLOW}Building Docker images...${NC}"
    docker compose build
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}✅ Docker images built successfully${NC}"
    else
        echo -e "${RED}❌ Failed to build Docker images${NC}"
        exit 1
    fi
    exit 0
fi

# Clean Docker resources
if [[ "$CLEAN" == true ]]; then
    echo -e "${YELLOW}Cleaning Docker resources...${NC}"

    echo -e "${GRAY}Stopping and removing containers...${NC}"
    docker compose down -v 2>/dev/null || true

    echo -e "${GRAY}Removing images...${NC}"
    docker rmi marketpulse-api 2>/dev/null || true
    docker rmi marketpulse-frontend 2>/dev/null || true

    echo -e "${GRAY}Cleaning unused Docker resources...${NC}"
    docker system prune -f

    echo -e "${GREEN}✅ Docker cleanup completed${NC}"
    exit 0
fi

# Show logs
if [[ "$LOGS" == true ]]; then
    echo -e "${YELLOW}Showing Docker logs...${NC}"
    echo -e "${GRAY}Press Ctrl+C to exit logs${NC}"
    docker compose logs -f
    exit 0
fi

# Main actions
case $ACTION in
    up)
        echo -e "${YELLOW}Starting Docker services...${NC}"

        if [[ "$PRODUCTION" == true ]]; then
            echo -e "${CYAN}Starting production stack...${NC}"
            docker compose --profile production up -d
        elif [[ "$FULL" == true ]]; then
            echo -e "${CYAN}Starting full stack (including database and cache)...${NC}"
            docker compose --profile full up -d
        else
            echo -e "${CYAN}Starting development stack...${NC}"
            docker compose up -d
        fi

        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✅ Services started successfully${NC}"
            echo ""
            echo -e "${WHITE}Services:${NC}"
            echo -e "${GRAY}- Backend API: http://localhost:8000${NC}"
            echo -e "${GRAY}- Frontend: http://localhost:3000${NC}"
            echo -e "${GRAY}- API Docs: http://localhost:8000/docs${NC}"

            if [[ "$PRODUCTION" == true || "$FULL" == true ]]; then
                echo -e "${GRAY}- PostgreSQL: localhost:5433${NC}"
                echo -e "${GRAY}- Redis: localhost:6379${NC}"
            fi

            echo ""
            echo -e "${CYAN}Run './docker.sh -l' to see logs${NC}"
            echo -e "${CYAN}Run './docker.sh down' to stop services${NC}"
        else
            echo -e "${RED}❌ Failed to start services${NC}"
            exit 1
        fi
        ;;

    down)
        echo -e "${YELLOW}Stopping Docker services...${NC}"
        docker compose down

        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✅ Services stopped successfully${NC}"
        else
            echo -e "${RED}❌ Failed to stop services${NC}"
            exit 1
        fi
        ;;

    restart)
        echo -e "${YELLOW}Restarting Docker services...${NC}"
        docker compose restart

        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}✅ Services restarted successfully${NC}"
        else
            echo -e "${RED}❌ Failed to restart services${NC}"
            exit 1
        fi
        ;;

    status)
        echo -e "${YELLOW}Docker service status:${NC}"
        docker compose ps
        ;;

    *)
        echo -e "${RED}Unknown action: $ACTION${NC}"
        echo "Available actions: up, down, restart, status"
        echo "Or use options: -p, -f, -b, -l, -c"
        exit 1
        ;;
esac