#!/bin/bash

# YouTube Download Service - Docker Run Script
# This script runs the container with proper volume mounts and environment setup

set -e  # Exit on any error

# Configuration
IMAGE_NAME="ytdl-service"
CONTAINER_NAME="ytdl-service"
DEFAULT_TAG="latest"
DEFAULT_PORT="8000"

# Parse command line arguments
TAG=${1:-$DEFAULT_TAG}
PORT=${2:-$DEFAULT_PORT}

echo "Starting YouTube Download Service container..."
echo "Image: ${IMAGE_NAME}:${TAG}"
echo "Container: ${CONTAINER_NAME}"
echo "Port: ${PORT}:8000"
echo ""

# Create necessary directories if they don't exist
echo "Creating directories..."
mkdir -p downloads
mkdir -p logs
mkdir -p config

# Set proper permissions
chmod 755 downloads logs config

# Check if container is already running
if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "⚠️  Container '$CONTAINER_NAME' is already running!"
    echo "To stop it first, run: ./stop.sh"
    echo "To view logs, run: ./logs.sh"
    exit 1
fi

# Remove existing stopped container if it exists
if docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
    echo "Removing existing stopped container..."
    docker rm "$CONTAINER_NAME"
fi

# Load environment variables from .env file if it exists
ENV_FILE=""
if [ -f ".env" ]; then
    ENV_FILE="--env-file .env"
    echo "Loading environment variables from .env file"
fi

# Run the container
echo "Starting container..."
docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    -p "${PORT}:8000" \
    -v "$(pwd)/downloads:/opt/ytdl_service/downloads" \
    -v "$(pwd)/logs:/var/log" \
    -v "$(pwd)/config:/opt/ytdl_service/config" \
    -e "YTDL_SERVICE_URL=http://localhost:${PORT}" \
    -e "PORT=8000" \
    $ENV_FILE \
    "${IMAGE_NAME}:${TAG}"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Container started successfully!"
    echo "Container Name: $CONTAINER_NAME"
    echo "Service URL: http://localhost:${PORT}"
    echo "Health Check: http://localhost:${PORT}/health"
    echo ""
    echo "Useful commands:"
    echo "  View logs:     ./logs.sh"
    echo "  Stop container: ./stop.sh"
    echo "  Container status: docker ps -f name=$CONTAINER_NAME"
    echo ""
    echo "Waiting for service to be ready..."
    sleep 3
    
    # Check if service is responding
    if command -v curl >/dev/null 2>&1; then
        if curl -s "http://localhost:${PORT}/health" >/dev/null; then
            echo "✅ Service is responding on http://localhost:${PORT}"
        else
            echo "⚠️  Service may still be starting up. Check logs with: ./logs.sh"
        fi
    else
        echo "💡 Install curl to automatically check service health"
    fi
else
    echo ""
    echo "❌ Failed to start container!"
    exit 1
fi