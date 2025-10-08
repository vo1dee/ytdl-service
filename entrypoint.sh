#!/bin/bash

# YouTube Download Service Container Entrypoint Script
# This script handles container initialization, directory setup, API key generation,
# logging configuration, and graceful shutdown handling

set -e

# Configuration from environment variables
DOWNLOADS_DIR="${DOWNLOADS_DIR:-/opt/ytdl_service/downloads}"
LOGS_DIR="${LOGS_DIR:-/var/log}"
API_KEY_FILE="${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}"
PORT="${PORT:-8000}"
YTDL_SERVICE_API_KEY="${YTDL_SERVICE_API_KEY:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1"
}

# Function to create directories with proper permissions
create_directories() {
    log "Creating necessary directories..."
    
    # Create downloads directory
    if [ ! -d "$DOWNLOADS_DIR" ]; then
        mkdir -p "$DOWNLOADS_DIR"
        log_success "Created downloads directory: $DOWNLOADS_DIR"
    else
        log "Downloads directory already exists: $DOWNLOADS_DIR"
    fi
    
    # Create logs directory
    if [ ! -d "$LOGS_DIR" ]; then
        mkdir -p "$LOGS_DIR"
        log_success "Created logs directory: $LOGS_DIR"
    else
        log "Logs directory already exists: $LOGS_DIR"
    fi
    
    # Create application directory
    APP_DIR="/opt/ytdl_service"
    if [ ! -d "$APP_DIR" ]; then
        mkdir -p "$APP_DIR"
        log_success "Created application directory: $APP_DIR"
    else
        log "Application directory already exists: $APP_DIR"
    fi
    
    # Set proper permissions for ytdl user
    if id "ytdl" &>/dev/null; then
        chown -R ytdl:ytdl "$DOWNLOADS_DIR" "$LOGS_DIR" "$APP_DIR"
        chmod -R 755 "$DOWNLOADS_DIR" "$LOGS_DIR" "$APP_DIR"
        log_success "Set proper permissions for ytdl user"
    else
        log_warning "ytdl user not found, using current user permissions"
    fi
}

# Function to generate API key if not provided
generate_api_key() {
    log "Checking API key configuration..."
    
    # If API key is provided via environment variable, use it
    if [ -n "$YTDL_SERVICE_API_KEY" ]; then
        log "Using API key from environment variable"
        echo "$YTDL_SERVICE_API_KEY" > "$API_KEY_FILE"
        log_success "API key written to file: $API_KEY_FILE"
        return
    fi
    
    # If API key file already exists, use it
    if [ -f "$API_KEY_FILE" ]; then
        log "Using existing API key file: $API_KEY_FILE"
        return
    fi
    
    # Generate new API key
    log "Generating new API key..."
    API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "$API_KEY" > "$API_KEY_FILE"
    
    # Set proper permissions
    if id "ytdl" &>/dev/null; then
        chown ytdl:ytdl "$API_KEY_FILE"
    fi
    chmod 600 "$API_KEY_FILE"
    
    log_success "Generated new API key and saved to: $API_KEY_FILE"
    log_warning "IMPORTANT: Your API key is: $API_KEY"
    log_warning "Please save this key securely for API access"
}

# Function to configure logging
configure_logging() {
    log "Configuring logging setup..."
    
    # Create log files if they don't exist
    YTDL_LOG_FILE="$LOGS_DIR/ytdl_service.log"
    ACCESS_LOG_FILE="$LOGS_DIR/access.log"
    ERROR_LOG_FILE="$LOGS_DIR/error.log"
    
    touch "$YTDL_LOG_FILE" "$ACCESS_LOG_FILE" "$ERROR_LOG_FILE"
    
    # Set proper permissions
    if id "ytdl" &>/dev/null; then
        chown ytdl:ytdl "$YTDL_LOG_FILE" "$ACCESS_LOG_FILE" "$ERROR_LOG_FILE"
    fi
    chmod 644 "$YTDL_LOG_FILE" "$ACCESS_LOG_FILE" "$ERROR_LOG_FILE"
    
    # Configure log rotation (basic setup)
    cat > /etc/logrotate.d/ytdl_service << EOF
$LOGS_DIR/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 644 ytdl ytdl
    postrotate
        # Send USR1 signal to reload logs if service supports it
        pkill -USR1 -f "python.*download_service.py" || true
    endscript
}
EOF
    
    log_success "Logging configuration completed"
    log "Log files:"
    log "  - Application: $YTDL_LOG_FILE"
    log "  - Access: $ACCESS_LOG_FILE"
    log "  - Error: $ERROR_LOG_FILE"
}

# Function to validate environment
validate_environment() {
    log "Validating environment..."
    
    # Check Python installation
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 is not installed"
        exit 1
    fi
    
    # Check FFmpeg installation
    if ! command -v ffmpeg &> /dev/null; then
        log_error "FFmpeg is not installed"
        exit 1
    fi
    
    # Check yt-dlp installation
    if ! python3 -c "import yt_dlp" &> /dev/null; then
        log_error "yt-dlp is not installed"
        exit 1
    fi
    
    # Check FastAPI installation
    if ! python3 -c "import fastapi" &> /dev/null; then
        log_error "FastAPI is not installed"
        exit 1
    fi
    
    # Validate port
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        log_error "Invalid port number: $PORT"
        exit 1
    fi
    
    log_success "Environment validation completed"
}

# Function to handle graceful shutdown
cleanup() {
    log "Received shutdown signal, performing graceful shutdown..."
    
    # Kill FastAPI service gracefully
    if [ -n "$FASTAPI_PID" ]; then
        log "Stopping FastAPI service (PID: $FASTAPI_PID)..."
        kill -TERM "$FASTAPI_PID" 2>/dev/null || true
        
        # Wait for graceful shutdown
        for i in {1..10}; do
            if ! kill -0 "$FASTAPI_PID" 2>/dev/null; then
                log_success "FastAPI service stopped gracefully"
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if kill -0 "$FASTAPI_PID" 2>/dev/null; then
            log_warning "Force killing FastAPI service"
            kill -KILL "$FASTAPI_PID" 2>/dev/null || true
        fi
    fi
    
    # Kill Telegram bot if running
    if [ -n "$TELEGRAM_PID" ]; then
        log "Stopping Telegram bot (PID: $TELEGRAM_PID)..."
        kill -TERM "$TELEGRAM_PID" 2>/dev/null || true
        
        # Wait for graceful shutdown
        for i in {1..5}; do
            if ! kill -0 "$TELEGRAM_PID" 2>/dev/null; then
                log_success "Telegram bot stopped gracefully"
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if kill -0 "$TELEGRAM_PID" 2>/dev/null; then
            log_warning "Force killing Telegram bot"
            kill -KILL "$TELEGRAM_PID" 2>/dev/null || true
        fi
    fi
    
    log_success "Graceful shutdown completed"
    exit 0
}

# Function to start services
start_services() {
    log "Starting YouTube Download Service..."
    
    # Change to application directory
    cd /opt/ytdl_service
    
    # Start FastAPI service
    log "Starting FastAPI service on port $PORT..."
    if id "ytdl" &>/dev/null; then
        # Run as ytdl user
        su -s /bin/bash ytdl -c "python3 download_service.py" &
    else
        # Run as current user
        python3 download_service.py &
    fi
    FASTAPI_PID=$!
    
    log_success "FastAPI service started (PID: $FASTAPI_PID)"
    
    # Start Telegram bot if token is provided
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        log "Starting Telegram bot..."
        if id "ytdl" &>/dev/null; then
            # Run as ytdl user
            su -s /bin/bash ytdl -c "python3 video_downloader.py" &
        else
            # Run as current user
            python3 video_downloader.py &
        fi
        TELEGRAM_PID=$!
        log_success "Telegram bot started (PID: $TELEGRAM_PID)"
    else
        log "Telegram bot token not provided, skipping bot startup"
    fi
    
    # Display service information
    log_success "YouTube Download Service is running!"
    log "Service Information:"
    log "  - FastAPI URL: http://localhost:$PORT"
    log "  - Health Check: http://localhost:$PORT/health"
    log "  - Downloads Directory: $DOWNLOADS_DIR"
    log "  - Logs Directory: $LOGS_DIR"
    log "  - API Key File: $API_KEY_FILE"
    
    if [ -f "$API_KEY_FILE" ]; then
        API_KEY_DISPLAY=$(cat "$API_KEY_FILE")
        log "  - API Key: $API_KEY_DISPLAY"
    fi
}

# Function to wait for services
wait_for_services() {
    log "Monitoring services..."
    
    while true; do
        # Check FastAPI service
        if [ -n "$FASTAPI_PID" ] && ! kill -0 "$FASTAPI_PID" 2>/dev/null; then
            log_error "FastAPI service died unexpectedly"
            exit 1
        fi
        
        # Check Telegram bot
        if [ -n "$TELEGRAM_PID" ] && ! kill -0 "$TELEGRAM_PID" 2>/dev/null; then
            log_warning "Telegram bot died unexpectedly"
            # Don't exit for Telegram bot failure, just log it
        fi
        
        sleep 5
    done
}

# Main execution
main() {
    log "YouTube Download Service Container Starting..."
    log "Container initialization started at $(date)"
    
    # Set up signal handlers for graceful shutdown
    trap cleanup SIGTERM SIGINT SIGQUIT
    
    # Initialize container
    validate_environment
    create_directories
    generate_api_key
    configure_logging
    
    # Start services
    start_services
    
    # Wait for services and handle signals
    wait_for_services
}

# Execute main function
main "$@"