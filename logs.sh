#!/bin/bash

# YouTube Download Service - Docker Logs Script
# This script displays container logs with various options

set -e  # Exit on any error

# Configuration
CONTAINER_NAME="ytdl-service"
DEFAULT_LINES="100"

# Parse command line arguments
COMMAND=${1:-"tail"}
LINES=${2:-$DEFAULT_LINES}

# Function to display usage
show_usage() {
    echo "Usage: $0 [COMMAND] [LINES]"
    echo ""
    echo "Commands:"
    echo "  tail     - Show last N lines and follow (default)"
    echo "  show     - Show last N lines without following"
    echo "  all      - Show all logs"
    echo "  follow   - Follow logs in real-time"
    echo ""
    echo "Examples:"
    echo "  $0                    # Show last 100 lines and follow"
    echo "  $0 show 50           # Show last 50 lines"
    echo "  $0 all               # Show all logs"
    echo "  $0 follow            # Follow logs in real-time"
    echo ""
}

# Check if container exists
if ! docker ps -aq -f name="$CONTAINER_NAME" | grep -q .; then
    echo "❌ Container '$CONTAINER_NAME' does not exist!"
    echo ""
    echo "To create and start the container:"
    echo "  ./run.sh"
    exit 1
fi

# Get container status
CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")

echo "YouTube Download Service - Container Logs"
echo "Container: $CONTAINER_NAME"
echo "Status: $CONTAINER_STATUS"
echo "Command: $COMMAND"

if [ "$COMMAND" != "all" ] && [ "$COMMAND" != "follow" ]; then
    echo "Lines: $LINES"
fi

echo ""
echo "Press Ctrl+C to exit log viewing"
echo "----------------------------------------"

# Execute the appropriate docker logs command based on the command
case "$COMMAND" in
    "tail")
        docker logs --tail "$LINES" --follow --timestamps "$CONTAINER_NAME"
        ;;
    "show")
        docker logs --tail "$LINES" --timestamps "$CONTAINER_NAME"
        ;;
    "all")
        docker logs --timestamps "$CONTAINER_NAME"
        ;;
    "follow")
        docker logs --follow --timestamps "$CONTAINER_NAME"
        ;;
    "help"|"-h"|"--help")
        show_usage
        ;;
    *)
        echo "❌ Unknown command: $COMMAND"
        echo ""
        show_usage
        exit 1
        ;;
esac