#!/bin/bash
set -e

# YouTube Download Service Container Entrypoint
# This script handles container initialization and graceful shutdown

echo "Starting YouTube Download Service container..."

# Function to handle graceful shutdown
cleanup() {
    echo "Received shutdown signal, stopping services gracefully..."
    if [ ! -z "$SERVICE_PID" ]; then
        kill -TERM "$SERVICE_PID" 2>/dev/null || true
        wait "$SERVICE_PID" 2>/dev/null || true
    fi
    echo "Services stopped gracefully"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Create necessary directories if they don't exist
echo "Setting up directories..."
mkdir -p "${DOWNLOADS_DIR:-/opt/ytdl_service/downloads}"
mkdir -p "${LOGS_DIR:-/var/log}"
mkdir -p "$(dirname "${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}")"

# Set proper permissions (only if we have write access)
if [ -w "${DOWNLOADS_DIR:-/opt/ytdl_service/downloads}" ]; then
    chmod 755 "${DOWNLOADS_DIR:-/opt/ytdl_service/downloads}"
fi

if [ -w "${LOGS_DIR:-/var/log}" ]; then
    chmod 755 "${LOGS_DIR:-/var/log}"
fi

# Generate API key if not provided and file doesn't exist
if [ -z "$YTDL_SERVICE_API_KEY" ] && [ ! -f "${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}" ]; then
    echo "Generating API key..."
    # Generate a secure random API key
    API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "$API_KEY" > "${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}"
    chmod 600 "${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}"
    echo "API key generated and saved to ${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}"
    export YTDL_SERVICE_API_KEY="$API_KEY"
fi

# Verify yt-dlp installation
echo "Verifying yt-dlp installation..."
if ! yt-dlp --version > /dev/null 2>&1; then
    echo "ERROR: yt-dlp is not properly installed or accessible"
    exit 1
fi

# Verify FFmpeg installation
echo "Verifying FFmpeg installation..."
if ! ffmpeg -version > /dev/null 2>&1; then
    echo "ERROR: FFmpeg is not properly installed or accessible"
    exit 1
fi

# Set default environment variables if not provided
export YTDL_SERVICE_URL="${YTDL_SERVICE_URL:-http://localhost:${PORT:-8000}}"
export YTDL_MAX_RETRIES="${YTDL_MAX_RETRIES:-3}"
export YTDL_RETRY_DELAY="${YTDL_RETRY_DELAY:-1}"

# Log configuration
echo "Container configuration:"
echo "  - Downloads directory: ${DOWNLOADS_DIR:-/opt/ytdl_service/downloads}"
echo "  - Logs directory: ${LOGS_DIR:-/var/log}"
echo "  - API key file: ${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}"
echo "  - Service URL: ${YTDL_SERVICE_URL}"
echo "  - Port: ${PORT:-8000}"
echo "  - Max retries: ${YTDL_MAX_RETRIES}"
echo "  - Retry delay: ${YTDL_RETRY_DELAY}s"

# Start the service
echo "Starting YouTube Download Service..."
cd /opt/ytdl_service/app

# Execute the command passed to the container
exec "$@" &
SERVICE_PID=$!

# Wait for the service to finish
wait "$SERVICE_PID"