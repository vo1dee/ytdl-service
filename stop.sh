#!/bin/bash

# YouTube Download Service - Docker Stop Script
# This script gracefully stops the container

set -e  # Exit on any error

# Configuration
CONTAINER_NAME="ytdl-service"
STOP_TIMEOUT=30

echo "Stopping YouTube Download Service container..."
echo "Container: $CONTAINER_NAME"
echo "Timeout: ${STOP_TIMEOUT}s"
echo ""

# Check if container exists and is running
if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
    echo "⚠️  Container '$CONTAINER_NAME' is not running"
    
    # Check if container exists but is stopped
    if docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
        echo "Container exists but is already stopped"
        echo ""
        echo "To remove the stopped container:"
        echo "  docker rm $CONTAINER_NAME"
        echo ""
        echo "To start the container:"
        echo "  ./run.sh"
    else
        echo "Container does not exist"
        echo ""
        echo "To create and start the container:"
        echo "  ./run.sh"
    fi
    exit 0
fi

# Get container info before stopping
echo "Container status before stopping:"
docker ps -f name="$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Gracefully stop the container
echo "Sending SIGTERM to container (graceful shutdown)..."
docker stop --time="$STOP_TIMEOUT" "$CONTAINER_NAME"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Container stopped successfully!"
    echo ""
    echo "Container status:"
    docker ps -a -f name="$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}"
    echo ""
    echo "Useful commands:"
    echo "  Start container:  ./run.sh"
    echo "  View logs:        ./logs.sh"
    echo "  Remove container: docker rm $CONTAINER_NAME"
    echo "  Remove image:     docker rmi ytdl-service"
else
    echo ""
    echo "❌ Failed to stop container gracefully!"
    echo "You may need to force stop with:"
    echo "  docker kill $CONTAINER_NAME"
    exit 1
fi