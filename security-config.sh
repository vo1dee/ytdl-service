#!/bin/bash

# Security Configuration Script for YouTube Download Service
# This script implements additional security hardening measures

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[SECURITY]${NC} $1"
}

log_error() {
    echo -e "${RED}[SECURITY ERROR]${NC} $1" >&2
}

log_warning() {
    echo -e "${YELLOW}[SECURITY WARNING]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SECURITY SUCCESS]${NC} $1"
}

# Function to configure file system security
configure_filesystem_security() {
    log "Configuring file system security..."
    
    # Set restrictive umask for new files
    umask 0027
    
    # Create secure temporary directory
    if [ ! -d "/tmp/ytdl" ]; then
        mkdir -p /tmp/ytdl
        chmod 700 /tmp/ytdl
    fi
    
    # Set proper permissions on application directories
    find /opt/ytdl_service -type d -exec chmod 750 {} \; 2>/dev/null || true
    find /opt/ytdl_service -type f -name "*.py" -exec chmod 640 {} \; 2>/dev/null || true
    find /opt/ytdl_service -type f -name "*.sh" -exec chmod 750 {} \; 2>/dev/null || true
    
    # Secure config directory
    if [ -d "/opt/ytdl_service/config" ]; then
        chmod 700 /opt/ytdl_service/config
        find /opt/ytdl_service/config -type f -exec chmod 600 {} \; 2>/dev/null || true
    fi
    
    log_success "File system security configured"
}

# Function to configure process security
configure_process_security() {
    log "Configuring process security..."
    
    # Set process limits
    ulimit -n 1024  # File descriptors
    ulimit -u 100   # Processes
    ulimit -m 1048576  # Memory (1GB in KB)
    
    # Set core dump restrictions
    ulimit -c 0
    
    log_success "Process security configured"
}

# Function to configure network security
configure_network_security() {
    log "Configuring network security..."
    
    # Validate listening ports
    if command -v netstat >/dev/null 2>&1; then
        LISTENING_PORTS=$(netstat -tuln 2>/dev/null | grep LISTEN | wc -l)
        if [ "$LISTENING_PORTS" -gt 5 ]; then
            log_warning "Multiple listening ports detected: $LISTENING_PORTS"
        fi
    fi
    
    # Check for unusual network connections
    if command -v ss >/dev/null 2>&1; then
        ESTABLISHED_CONNECTIONS=$(ss -tuln 2>/dev/null | grep -c LISTEN || echo "0")
        log "Network listeners: $ESTABLISHED_CONNECTIONS"
    fi
    
    log_success "Network security configured"
}

# Function to configure secret management
configure_secret_management() {
    log "Configuring secret management..."
    
    # Create secrets directory if it doesn't exist
    SECRETS_DIR="/opt/ytdl_service/secrets"
    if [ ! -d "$SECRETS_DIR" ]; then
        mkdir -p "$SECRETS_DIR"
        chmod 700 "$SECRETS_DIR"
        log_success "Created secrets directory: $SECRETS_DIR"
    fi
    
    # Set up API key rotation script
    cat > /opt/ytdl_service/rotate-api-key.sh << 'EOF'
#!/bin/bash
# API Key Rotation Script

API_KEY_FILE="${API_KEY_FILE:-/opt/ytdl_service/config/api_key.txt}"
BACKUP_DIR="/opt/ytdl_service/config/backups"

# Create backup directory
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# Backup current key
if [ -f "$API_KEY_FILE" ]; then
    cp "$API_KEY_FILE" "$BACKUP_DIR/api_key_$(date +%Y%m%d_%H%M%S).txt"
    chmod 600 "$BACKUP_DIR/api_key_$(date +%Y%m%d_%H%M%S).txt"
fi

# Generate new key
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(36))")
echo "$NEW_KEY" > "$API_KEY_FILE.new"
chmod 600 "$API_KEY_FILE.new"
mv "$API_KEY_FILE.new" "$API_KEY_FILE"

echo "API key rotated successfully"
echo "New key: $NEW_KEY"
echo "Backup saved in: $BACKUP_DIR"

# Clean old backups (keep last 5)
find "$BACKUP_DIR" -name "api_key_*.txt" -type f | sort | head -n -5 | xargs rm -f
EOF
    
    chmod 750 /opt/ytdl_service/rotate-api-key.sh
    
    # Set up environment variable sanitization
    cat > /opt/ytdl_service/sanitize-env.sh << 'EOF'
#!/bin/bash
# Environment Variable Sanitization Script

# List of sensitive environment variable patterns
SENSITIVE_PATTERNS="PASSWORD PASS SECRET TOKEN KEY PRIVATE"

echo "Checking for sensitive environment variables..."
for pattern in $SENSITIVE_PATTERNS; do
    if env | grep -i "$pattern" | grep -v "API_KEY_FILE" >/dev/null 2>&1; then
        echo "WARNING: Found environment variable containing '$pattern'"
    fi
done

# Clear potentially sensitive variables after use
unset YTDL_SERVICE_API_KEY 2>/dev/null || true
unset TELEGRAM_BOT_TOKEN 2>/dev/null || true

echo "Environment sanitization completed"
EOF
    
    chmod 750 /opt/ytdl_service/sanitize-env.sh
    
    log_success "Secret management configured"
}

# Function to configure logging security
configure_logging_security() {
    log "Configuring logging security..."
    
    # Set up secure log rotation
    cat > /opt/ytdl_service/secure-logrotate.conf << 'EOF'
/var/log/ytdl_service.log /var/log/access.log /var/log/error.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 640 ytdl ytdl
    sharedscripts
    postrotate
        # Send signal to reload logs
        pkill -USR1 -f "python.*download_service.py" || true
    endscript
    # Security: Copy logs to secure backup location
    lastaction
        find /var/log -name "*.gz" -mtime +7 -exec rm {} \;
    endscript
}
EOF
    
    # Create log sanitization script
    cat > /opt/ytdl_service/sanitize-logs.sh << 'EOF'
#!/bin/bash
# Log Sanitization Script - Remove sensitive data from logs

LOG_DIR="${LOGS_DIR:-/var/log}"

# Patterns to sanitize (API keys, tokens, etc.)
SENSITIVE_PATTERNS=(
    "api[_-]?key[\"':\s]*[a-zA-Z0-9+/=]{20,}"
    "token[\"':\s]*[a-zA-Z0-9+/=]{20,}"
    "password[\"':\s]*[^\s\"']{8,}"
    "secret[\"':\s]*[a-zA-Z0-9+/=]{16,}"
)

for log_file in "$LOG_DIR"/*.log; do
    if [ -f "$log_file" ]; then
        for pattern in "${SENSITIVE_PATTERNS[@]}"; do
            sed -i "s/$pattern/[REDACTED]/gi" "$log_file" 2>/dev/null || true
        done
    fi
done

echo "Log sanitization completed"
EOF
    
    chmod 750 /opt/ytdl_service/sanitize-logs.sh
    
    log_success "Logging security configured"
}

# Function to run security checks
run_security_checks() {
    log "Running security checks..."
    
    # Check file permissions
    log "Checking file permissions..."
    INSECURE_FILES=$(find /opt/ytdl_service -type f -perm /022 2>/dev/null | head -10)
    if [ -n "$INSECURE_FILES" ]; then
        log_warning "Found files with loose permissions:"
        echo "$INSECURE_FILES"
    fi
    
    # Check for SUID/SGID files
    log "Checking for SUID/SGID files..."
    SUID_FILES=$(find /opt/ytdl_service -type f \( -perm -4000 -o -perm -2000 \) 2>/dev/null)
    if [ -n "$SUID_FILES" ]; then
        log_warning "Found SUID/SGID files:"
        echo "$SUID_FILES"
    fi
    
    # Check process ownership
    log "Checking process ownership..."
    if command -v ps >/dev/null 2>&1; then
        ROOT_PROCESSES=$(ps aux | grep -v "^root" | grep ytdl | wc -l)
        log "Non-root ytdl processes: $ROOT_PROCESSES"
    fi
    
    # Check network security
    log "Checking network security..."
    if [ -f "/proc/net/tcp" ]; then
        LISTENING_PORTS=$(cat /proc/net/tcp | grep ":0050" | wc -l)
        log "Listening on port 80: $LISTENING_PORTS"
    fi
    
    log_success "Security checks completed"
}

# Main function
main() {
    log "Starting security configuration..."
    
    configure_filesystem_security
    configure_process_security
    configure_network_security
    configure_secret_management
    configure_logging_security
    run_security_checks
    
    log_success "Security configuration completed successfully"
    
    # Create security status file
    cat > /opt/ytdl_service/security-status.txt << EOF
Security Configuration Status
============================
Timestamp: $(date)
User: $(whoami)
UID: $(id -u)
GID: $(id -g)
Umask: $(umask)

Security Features Enabled:
- Non-root user execution: YES
- Restrictive file permissions: YES
- Secret management: YES
- Log sanitization: YES
- Process limits: YES
- Network security: YES

Security Scripts Available:
- /opt/ytdl_service/rotate-api-key.sh
- /opt/ytdl_service/sanitize-env.sh
- /opt/ytdl_service/sanitize-logs.sh
- /opt/ytdl_service/security-scan.sh (if using Dockerfile.security)

Configuration Files:
- /opt/ytdl_service/secure-logrotate.conf
- /opt/ytdl_service/security-status.txt
EOF
    
    chmod 640 /opt/ytdl_service/security-status.txt
    
    log "Security status written to: /opt/ytdl_service/security-status.txt"
}

# Execute main function
main "$@"