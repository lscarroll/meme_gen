#!/bin/bash

echo "Starting Meme Generator with Kafka..."

# Function to handle cleanup
cleanup() {
    echo -e "\nShutting down services..."
    docker-compose down
    exit 0
}

# Trap CTRL+C and call cleanup
trap cleanup SIGINT SIGTERM

# Start the services in background
docker-compose up -d --build

echo "Meme Generator services started!"
echo "Press CTRL+C to stop all services"
echo ""
echo "To send custom tasks, use:"
echo "  docker-compose exec orchestrator python services/orchestrator/orchestrator.py --duration 300 --download-only"
echo "  docker-compose exec orchestrator python services/orchestrator/orchestrator.py --duration 300 --compile-only"
echo ""
echo "=== Live Logs (CTRL+C to stop) ==="

# Follow logs from all services
docker-compose logs -f