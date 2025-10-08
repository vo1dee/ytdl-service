#!/bin/bash

# Container Health Check Script for YouTube Download Service
# This script provides comprehensive health monitoring for Docker HEALTHCHECK instruction
# and can be used independently for container health validation

set -e

# Configuration from environment variables
PORT="${PORT:-8000}"
DOWNLOADS_DIR="${DOWNLOADS_DIR:-/opt/ytdl_service/downloads}"
LOGS_DIR="${LOGS_DIR:-/var/log}"
API_KEY_FILE="${API_KEY_FILE:-/opt/ytdl_service/api_key.txt}"

# Health check thresholds
DISK_USAGE_THRESHOLD=90  # Percentage
RESPONSE_TIMEOUT=10      # Seconds
MAX_LOAD_AVERAGE=10.0    # System load threshold

# Colors for output (only if terminal supports it)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Health check functions
check_service_response() {
    log_info "Checking FastAPI service response..."
    
    # Try to connect to health endpoint
    if curl -f -s --max-time "$RESPONSE_TIMEOUT" "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        log_success "FastAPI service is responding"
        return 0
    else
        log_error "FastAPI service is not responding on port $PORT"
        return 1
    fi
}

check_service_dependencies() {
    log_info "Checking service dependencies..."
    local deps_ok=0
    
    # Check Python
    if command -v python3 >/dev/null 2>&1; then
        log_success "Python3 is available"
    else
        log_error "Python3 is not available"
        deps_ok=1
    fi
    
    # Check FFmpeg
    if command -v ffmpeg >/dev/null 2>&1; then
        log_success "FFmpeg is available"
    else
        log_error "FFmpeg is not available"
        deps_ok=1
    fi
    
    # Check yt-dlp availability
    if python3 -c "import yt_dlp" >/dev/null 2>&1; then
        log_success "yt-dlp is available"
    else
        log_error "yt-dlp is not available"
        deps_ok=1
    fi
    
    # Check FastAPI availability
    if python3 -c "import fastapi" >/dev/null 2>&1; then
        log_success "FastAPI is available"
    else
        log_error "FastAPI is not available"
        deps_ok=1
    fi
    
    return $deps_ok
}

check_disk_space() {
    log_info "Checking disk space..."
    local disk_ok=0
    
    # Check downloads directory disk space
    if [ -d "$DOWNLOADS_DIR" ]; then
        local usage_percent=$(df "$DOWNLOADS_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
        
        if [ "$usage_percent" -lt "$DISK_USAGE_THRESHOLD" ]; then
            log_success "Downloads directory disk usage: ${usage_percent}% (threshold: ${DISK_USAGE_THRESHOLD}%)"
        else
            log_error "Downloads directory disk usage too high: ${usage_percent}% (threshold: ${DISK_USAGE_THRESHOLD}%)"
            disk_ok=1
        fi
    else
        log_error "Downloads directory does not exist: $DOWNLOADS_DIR"
        disk_ok=1
    fi
    
    # Check logs directory disk space
    if [ -d "$LOGS_DIR" ]; then
        local logs_usage_percent=$(df "$LOGS_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
        
        if [ "$logs_usage_percent" -lt "$DISK_USAGE_THRESHOLD" ]; then
            log_success "Logs directory disk usage: ${logs_usage_percent}% (threshold: ${DISK_USAGE_THRESHOLD}%)"
        else
            log_warning "Logs directory disk usage high: ${logs_usage_percent}% (threshold: ${DISK_USAGE_THRESHOLD}%)"
            # Don't fail for logs directory, just warn
        fi
    else
        log_warning "Logs directory does not exist: $LOGS_DIR"
    fi
    
    return $disk_ok
}

check_directory_permissions() {
    log_info "Checking directory permissions..."
    local perms_ok=0
    
    # Check downloads directory
    if [ -d "$DOWNLOADS_DIR" ]; then
        if [ -r "$DOWNLOADS_DIR" ] && [ -w "$DOWNLOADS_DIR" ]; then
            log_success "Downloads directory permissions OK"
        else
            log_error "Downloads directory permissions insufficient"
            perms_ok=1
        fi
    else
        log_error "Downloads directory does not exist: $DOWNLOADS_DIR"
        perms_ok=1
    fi
    
    # Check logs directory
    if [ -d "$LOGS_DIR" ]; then
        if [ -w "$LOGS_DIR" ]; then
            log_success "Logs directory permissions OK"
        else
            log_error "Logs directory permissions insufficient"
            perms_ok=1
        fi
    else
        log_error "Logs directory does not exist: $LOGS_DIR"
        perms_ok=1
    fi
    
    # Check API key file
    if [ -f "$API_KEY_FILE" ]; then
        if [ -r "$API_KEY_FILE" ]; then
            log_success "API key file accessible"
        else
            log_error "API key file not readable"
            perms_ok=1
        fi
    else
        log_warning "API key file does not exist: $API_KEY_FILE"
        # Don't fail if API key is provided via environment
    fi
    
    return $perms_ok
}

check_system_resources() {
    log_info "Checking system resources..."
    local resources_ok=0
    
    # Check memory usage
    if command -v free >/dev/null 2>&1; then
        local mem_usage=$(free | awk 'NR==2{printf "%.1f", $3*100/$2}')
        log_success "Memory usage: ${mem_usage}%"
    else
        log_warning "Cannot check memory usage (free command not available)"
    fi
    
    # Check load average
    if [ -f /proc/loadavg ]; then
        local load_avg=$(awk '{print $1}' /proc/loadavg)
        local load_check=$(awk -v load="$load_avg" -v threshold="$MAX_LOAD_AVERAGE" 'BEGIN {print (load < threshold) ? "ok" : "high"}')
        
        if [ "$load_check" = "ok" ]; then
            log_success "System load average: $load_avg (threshold: $MAX_LOAD_AVERAGE)"
        else
            log_warning "System load average high: $load_avg (threshold: $MAX_LOAD_AVERAGE)"
            # Don't fail for high load, just warn
        fi
    else
        log_warning "Cannot check load average (/proc/loadavg not available)"
    fi
    
    return $resources_ok
}

check_process_health() {
    log_info "Checking process health..."
    local process_ok=0
    
    # Check if FastAPI process is running
    if pgrep -f "download_service.py" >/dev/null 2>&1; then
        log_success "FastAPI process is running"
    else
        log_error "FastAPI process is not running"
        process_ok=1
    fi
    
    # Check if Telegram bot is running (optional)
    if pgrep -f "video_downloader.py" >/dev/null 2>&1; then
        log_success "Telegram bot process is running"
    else
        log_info "Telegram bot process is not running (may be intentional)"
    fi
    
    return $process_ok
}

# Main health check function
perform_health_check() {
    local overall_status=0
    local start_time=$(date +%s)
    
    echo "=== Container Health Check Started at $(date) ==="
    echo
    
    # Run all health checks
    check_service_dependencies || overall_status=1
    echo
    
    check_directory_permissions || overall_status=1
    echo
    
    check_disk_space || overall_status=1
    echo
    
    check_system_resources || overall_status=1
    echo
    
    check_process_health || overall_status=1
    echo
    
    check_service_response || overall_status=1
    echo
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo "=== Health Check Completed in ${duration}s ==="
    
    if [ $overall_status -eq 0 ]; then
        log_success "Overall health status: HEALTHY"
        echo
        return 0
    else
        log_error "Overall health status: UNHEALTHY"
        echo
        return 1
    fi
}

# Quick health check for Docker HEALTHCHECK
quick_health_check() {
    # Minimal checks for Docker HEALTHCHECK (fast execution)
    
    # Check if service responds
    if ! curl -f -s --max-time 5 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
        return 1
    fi
    
    # Check critical directories exist and are accessible
    if [ ! -d "$DOWNLOADS_DIR" ] || [ ! -w "$DOWNLOADS_DIR" ]; then
        return 1
    fi
    
    # Check disk space (critical threshold)
    if [ -d "$DOWNLOADS_DIR" ]; then
        local usage_percent=$(df "$DOWNLOADS_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
        if [ "$usage_percent" -ge 95 ]; then
            return 1
        fi
    fi
    
    return 0
}

# Usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Container health check script for YouTube Download Service"
    echo
    echo "Options:"
    echo "  --quick, -q     Perform quick health check (for Docker HEALTHCHECK)"
    echo "  --verbose, -v   Perform comprehensive health check with detailed output"
    echo "  --help, -h      Show this help message"
    echo
    echo "Environment Variables:"
    echo "  PORT                 FastAPI service port (default: 8000)"
    echo "  DOWNLOADS_DIR        Downloads directory path"
    echo "  LOGS_DIR            Logs directory path"
    echo "  API_KEY_FILE        API key file path"
    echo
    echo "Exit Codes:"
    echo "  0  Healthy"
    echo "  1  Unhealthy"
}

# Main execution
main() {
    case "${1:-}" in
        --quick|-q)
            quick_health_check
            exit $?
            ;;
        --verbose|-v)
            perform_health_check
            exit $?
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        "")
            # Default behavior for Docker HEALTHCHECK
            quick_health_check
            exit $?
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@"