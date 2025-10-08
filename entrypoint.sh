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

# Function to generate API key if not provided (Security Hardened)
generate_api_key() {
    log "Checking API key configuration..."
    
    # Security: Validate API key file path
    if [[ ! "$API_KEY_FILE" =~ ^/opt/ytdl_service/ ]]; then
        log_error "Invalid API key file path: $API_KEY_FILE"
        exit 1
    fi
    
    # Security: Create config directory with restrictive permissions
    CONFIG_DIR=$(dirname "$API_KEY_FILE")
    if [ ! -d "$CONFIG_DIR" ]; then
        mkdir -p "$CONFIG_DIR"
        chmod 700 "$CONFIG_DIR"
        log_success "Created secure config directory: $CONFIG_DIR"
    fi
    
    # Security: Check for Docker secrets first (recommended for production)
    DOCKER_SECRET_FILE="/run/secrets/ytdl_api_key"
    if [ -f "$DOCKER_SECRET_FILE" ]; then
        log "Using API key from Docker secret"
        cp "$DOCKER_SECRET_FILE" "$API_KEY_FILE"
        chmod 600 "$API_KEY_FILE"
        log_success "API key loaded from Docker secret"
        return
    fi
    
    # Security: Check for mounted secret file
    MOUNTED_SECRET_FILE="/opt/ytdl_service/secrets/api_key"
    if [ -f "$MOUNTED_SECRET_FILE" ]; then
        log "Using API key from mounted secret file"
        cp "$MOUNTED_SECRET_FILE" "$API_KEY_FILE"
        chmod 600 "$API_KEY_FILE"
        log_success "API key loaded from mounted secret"
        return
    fi
    
    # If API key is provided via environment variable, use it
    if [ -n "$YTDL_SERVICE_API_KEY" ]; then
        log "Using API key from environment variable"
        # Security: Validate API key format (base64url, 32+ chars)
        if [[ ${#YTDL_SERVICE_API_KEY} -lt 32 ]]; then
            log_error "API key too short (minimum 32 characters required)"
            exit 1
        fi
        echo "$YTDL_SERVICE_API_KEY" > "$API_KEY_FILE"
        chmod 600 "$API_KEY_FILE"
        log_success "API key written to file: $API_KEY_FILE"
        # Security: Clear environment variable after use
        unset YTDL_SERVICE_API_KEY
        return
    fi
    
    # If API key file already exists, validate and use it
    if [ -f "$API_KEY_FILE" ]; then
        # Security: Validate existing API key
        if [ -r "$API_KEY_FILE" ]; then
            EXISTING_KEY=$(cat "$API_KEY_FILE" 2>/dev/null)
            if [[ ${#EXISTING_KEY} -ge 32 ]]; then
                log "Using existing valid API key file: $API_KEY_FILE"
                chmod 600 "$API_KEY_FILE"
                return
            else
                log_warning "Existing API key is too short, generating new one"
            fi
        else
            log_warning "Cannot read existing API key file, generating new one"
        fi
    fi
    
    # Generate new API key with enhanced security
    log "Generating new secure API key..."
    # Security: Use cryptographically secure random generation
    API_KEY=$(python3 -c "
import secrets
import string
# Generate 48-character URL-safe key for enhanced security
key = secrets.token_urlsafe(36)
print(key)
")
    
    # Security: Validate generated key
    if [[ ${#API_KEY} -lt 32 ]]; then
        log_error "Failed to generate secure API key"
        exit 1
    fi
    
    # Security: Write key with atomic operation
    echo "$API_KEY" > "$API_KEY_FILE.tmp"
    chmod 600 "$API_KEY_FILE.tmp"
    mv "$API_KEY_FILE.tmp" "$API_KEY_FILE"
    
    log_success "Generated new API key and saved to: $API_KEY_FILE"
    log_warning "IMPORTANT: Your API key is: $API_KEY"
    log_warning "Please save this key securely for API access"
    log_warning "For production, use Docker secrets or mounted secret files"
    
    # Security: Clear API key from memory
    unset API_KEY
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
    
    # Configure log rotation (user-level setup since we don't have root access)
    # Create a local logrotate configuration
    cat > /opt/ytdl_service/logrotate.conf << EOF
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
    
    # Note: In production, the system administrator should configure logrotate
    log_warning "Log rotation configured locally. For production, configure system logrotate."
    
    log_success "Logging configuration completed"
    log "Log files:"
    log "  - Application: $YTDL_LOG_FILE"
    log "  - Access: $ACCESS_LOG_FILE"
    log "  - Error: $ERROR_LOG_FILE"
}

# Function to validate environment (Security Enhanced)
validate_environment() {
    log "Validating environment and security configuration..."
    
    # Security: Check if running as root (should not be)
    if [ "$(id -u)" -eq 0 ]; then
        log_error "Container is running as root user - security violation"
        exit 1
    fi
    
    # Security: Validate user identity
    CURRENT_USER=$(whoami)
    if [ "$CURRENT_USER" != "ytdl" ]; then
        log_warning "Running as user: $CURRENT_USER (expected: ytdl)"
    fi
    
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
    
    # Security: Validate port range (avoid privileged ports)
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
        log_error "Invalid or privileged port number: $PORT (use 1024-65535)"
        exit 1
    fi
    
    # Security: Validate directory permissions
    validate_directory_security
    
    # Security: Check for sensitive environment variables
    validate_environment_security
    
    log_success "Environment and security validation completed"
}

# Function to validate directory security
validate_directory_security() {
    log "Validating directory security..."
    
    # Check downloads directory permissions
    if [ -d "$DOWNLOADS_DIR" ]; then
        DOWNLOADS_PERMS=$(stat -c "%a" "$DOWNLOADS_DIR" 2>/dev/null || echo "000")
        if [ "$DOWNLOADS_PERMS" != "755" ] && [ "$DOWNLOADS_PERMS" != "750" ]; then
            log_warning "Downloads directory has unusual permissions: $DOWNLOADS_PERMS"
        fi
    fi
    
    # Check config directory permissions (should be restrictive)
    CONFIG_DIR=$(dirname "$API_KEY_FILE")
    if [ -d "$CONFIG_DIR" ]; then
        CONFIG_PERMS=$(stat -c "%a" "$CONFIG_DIR" 2>/dev/null || echo "000")
        if [ "$CONFIG_PERMS" != "700" ]; then
            log_warning "Config directory permissions not secure: $CONFIG_PERMS (should be 700)"
            chmod 700 "$CONFIG_DIR" 2>/dev/null || log_warning "Cannot fix config directory permissions"
        fi
    fi
    
    # Security: Check for world-writable directories
    WORLD_WRITABLE=$(find /opt/ytdl_service -type d -perm -002 2>/dev/null | head -5)
    if [ -n "$WORLD_WRITABLE" ]; then
        log_warning "Found world-writable directories:"
        echo "$WORLD_WRITABLE"
    fi
    
    log_success "Directory security validation completed"
}

# Function to validate environment variable security
validate_environment_security() {
    log "Validating environment variable security..."
    
    # Security: Check for sensitive data in environment
    SENSITIVE_VARS="PASSWORD PASS SECRET TOKEN KEY"
    for var in $SENSITIVE_VARS; do
        if env | grep -i "$var" | grep -v "API_KEY_FILE" | grep -v "YTDL_SERVICE_API_KEY" >/dev/null 2>&1; then
            log_warning "Potentially sensitive environment variable detected containing: $var"
        fi
    done
    
    # Security: Validate critical path variables
    for path_var in DOWNLOADS_DIR LOGS_DIR API_KEY_FILE; do
        eval "path_value=\$$path_var"
        if [[ ! "$path_value" =~ ^/opt/ytdl_service/ ]] && [[ ! "$path_value" =~ ^/var/log ]] && [[ ! "$path_value" =~ ^/tmp/ytdl ]]; then
            log_warning "Suspicious path in $path_var: $path_value"
        fi
    done
    
    # Security: Check umask
    CURRENT_UMASK=$(umask)
    if [ "$CURRENT_UMASK" != "0027" ] && [ "$CURRENT_UMASK" != "0022" ]; then
        log_warning "Unusual umask: $CURRENT_UMASK (setting to 0027)"
        umask 0027
    fi
    
    log_success "Environment security validation completed"
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
    # Check if we're already running as ytdl user
    CURRENT_USER=$(whoami)
    if [ "$CURRENT_USER" = "ytdl" ]; then
        # Already running as ytdl user, start directly
        cd /opt/ytdl_service/app
        python3 download_service.py &
    elif id "ytdl" &>/dev/null; then
        # Run as ytdl user
        su -s /bin/bash ytdl -c "cd /opt/ytdl_service/app && python3 download_service.py" &
    else
        # Run as current user
        cd /opt/ytdl_service/app
        python3 download_service.py &
    fi
    FASTAPI_PID=$!
    
    log_success "FastAPI service started (PID: $FASTAPI_PID)"
    
    # Start Telegram bot if token is provided
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        log "Starting Telegram bot..."
        if [ "$CURRENT_USER" = "ytdl" ]; then
            # Already running as ytdl user, start directly
            cd /opt/ytdl_service/app
            python3 video_downloader.py &
        elif id "ytdl" &>/dev/null; then
            # Run as ytdl user
            su -s /bin/bash ytdl -c "cd /opt/ytdl_service/app && python3 video_downloader.py" &
        else
            # Run as current user
            cd /opt/ytdl_service/app
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
    
    # Security: Run security configuration
    if [ -f "/opt/ytdl_service/security-config.sh" ]; then
        log "Running security configuration..."
        bash /opt/ytdl_service/security-config.sh
    fi
    
    generate_api_key
    configure_logging
    
    # Start services
    start_services
    
    # Wait for services and handle signals
    wait_for_services
}

# Execute main function
main "$@"