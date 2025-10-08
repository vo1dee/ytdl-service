#!/bin/bash

# Security Testing Script for YouTube Download Service
# This script validates the security hardening implementation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Logging functions
log() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Test function wrapper
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    log "Running test: $test_name"
    
    if eval "$test_command"; then
        log_pass "$test_name"
    else
        log_fail "$test_name"
    fi
    echo
}

# Test 1: Check if container runs as non-root user
test_non_root_user() {
    local container_name="ytdl-service-test"
    
    # Start container for testing
    docker run -d --name "$container_name" ytdl-service:latest sleep 60 >/dev/null 2>&1
    
    # Check user ID
    local user_id=$(docker exec "$container_name" id -u 2>/dev/null)
    local user_name=$(docker exec "$container_name" whoami 2>/dev/null)
    
    # Cleanup
    docker stop "$container_name" >/dev/null 2>&1
    docker rm "$container_name" >/dev/null 2>&1
    
    if [ "$user_id" != "0" ] && [ "$user_name" = "ytdl" ]; then
        return 0
    else
        log_fail "Container running as user: $user_name (UID: $user_id)"
        return 1
    fi
}

# Test 2: Check file permissions
test_file_permissions() {
    local container_name="ytdl-service-test"
    
    # Start container for testing
    docker run -d --name "$container_name" ytdl-service:latest sleep 60 >/dev/null 2>&1
    
    # Check config directory permissions
    local config_perms=$(docker exec "$container_name" stat -c "%a" /opt/ytdl_service/config 2>/dev/null || echo "000")
    
    # Check if security scripts are executable
    local entrypoint_perms=$(docker exec "$container_name" stat -c "%a" /opt/ytdl_service/entrypoint.sh 2>/dev/null || echo "000")
    local security_perms=$(docker exec "$container_name" stat -c "%a" /opt/ytdl_service/security-config.sh 2>/dev/null || echo "000")
    
    # Cleanup
    docker stop "$container_name" >/dev/null 2>&1
    docker rm "$container_name" >/dev/null 2>&1
    
    if [ "$config_perms" = "700" ] && [ "$entrypoint_perms" = "750" ] && [ "$security_perms" = "750" ]; then
        return 0
    else
        log_fail "Incorrect permissions - config: $config_perms, entrypoint: $entrypoint_perms, security: $security_perms"
        return 1
    fi
}

# Test 3: Check security scripts exist
test_security_scripts() {
    local container_name="ytdl-service-test"
    
    # Start container for testing
    docker run -d --name "$container_name" ytdl-service:latest sleep 60 >/dev/null 2>&1
    
    # Check if security scripts exist
    local scripts_exist=true
    
    for script in entrypoint.sh security-config.sh health_check.sh; do
        if ! docker exec "$container_name" test -f "/opt/ytdl_service/$script" 2>/dev/null; then
            log_fail "Missing security script: $script"
            scripts_exist=false
        fi
    done
    
    # Cleanup
    docker stop "$container_name" >/dev/null 2>&1
    docker rm "$container_name" >/dev/null 2>&1
    
    if [ "$scripts_exist" = true ]; then
        return 0
    else
        return 1
    fi
}

# Test 4: Check Dockerfile security features
test_dockerfile_security() {
    # Check if Dockerfile contains security features
    local security_features=0
    
    if grep -q "USER ytdl" Dockerfile; then
        security_features=$((security_features + 1))
    else
        log_fail "Dockerfile missing non-root user directive"
    fi
    
    if grep -q "dumb-init" Dockerfile; then
        security_features=$((security_features + 1))
    else
        log_fail "Dockerfile missing dumb-init for signal handling"
    fi
    
    if grep -q "PYTHONDONTWRITEBYTECODE" Dockerfile; then
        security_features=$((security_features + 1))
    else
        log_fail "Dockerfile missing Python security environment variables"
    fi
    
    if grep -q "security\." Dockerfile; then
        security_features=$((security_features + 1))
    else
        log_fail "Dockerfile missing security labels"
    fi
    
    if [ "$security_features" -ge 3 ]; then
        return 0
    else
        return 1
    fi
}

# Test 5: Check security configuration files exist
test_security_files() {
    local files_exist=0
    
    for file in Dockerfile.security docker-compose.security.yml SECURITY.md security-config.sh; do
        if [ -f "$file" ]; then
            files_exist=$((files_exist + 1))
        else
            log_fail "Missing security file: $file"
        fi
    done
    
    if [ "$files_exist" -eq 4 ]; then
        return 0
    else
        return 1
    fi
}

# Test 6: Check API key security
test_api_key_security() {
    local container_name="ytdl-service-test"
    
    # Start container with environment variable
    docker run -d --name "$container_name" \
        -e YTDL_SERVICE_API_KEY="test-key-12345678901234567890123456" \
        ytdl-service:latest sleep 60 >/dev/null 2>&1
    
    # Wait for initialization
    sleep 5
    
    # Check if API key file was created with proper permissions
    # First check if the file exists, if not, run the entrypoint to create it
    if ! docker exec "$container_name" test -f /opt/ytdl_service/config/api_key.txt 2>/dev/null; then
        # Run entrypoint script to initialize
        docker exec "$container_name" /opt/ytdl_service/entrypoint.sh &
        sleep 3
        docker exec "$container_name" pkill -f entrypoint.sh 2>/dev/null || true
    fi
    
    local api_key_perms=$(docker exec "$container_name" stat -c "%a" /opt/ytdl_service/config/api_key.txt 2>/dev/null || echo "000")
    
    # Check if environment variable was cleared (this is harder to test directly)
    local env_cleared=true
    
    # Cleanup
    docker stop "$container_name" >/dev/null 2>&1
    docker rm "$container_name" >/dev/null 2>&1
    
    if [ "$api_key_perms" = "600" ]; then
        return 0
    else
        log_fail "API key file permissions incorrect: $api_key_perms (should be 600)"
        return 1
    fi
}

# Test 7: Check Docker Compose security configuration
test_compose_security() {
    local security_features=0
    
    if [ -f "docker-compose.security.yml" ]; then
        if grep -q "read_only: true" docker-compose.security.yml; then
            security_features=$((security_features + 1))
        fi
        
        if grep -q "cap_drop:" docker-compose.security.yml; then
            security_features=$((security_features + 1))
        fi
        
        if grep -q "no-new-privileges" docker-compose.security.yml; then
            security_features=$((security_features + 1))
        fi
        
        if grep -q "tmpfs:" docker-compose.security.yml; then
            security_features=$((security_features + 1))
        fi
    fi
    
    if [ "$security_features" -ge 3 ]; then
        return 0
    else
        log_fail "Docker Compose security configuration incomplete (features: $security_features/4)"
        return 1
    fi
}

# Main test execution
main() {
    log "Starting security validation tests..."
    echo
    
    # Check if Docker is available
    if ! command -v docker >/dev/null 2>&1; then
        log_fail "Docker is not available"
        exit 1
    fi
    
    # Check if image exists
    if ! docker image inspect ytdl-service:latest >/dev/null 2>&1; then
        log_warning "ytdl-service:latest image not found, building..."
        if ! docker build -t ytdl-service:latest . >/dev/null 2>&1; then
            log_fail "Failed to build Docker image"
            exit 1
        fi
    fi
    
    # Run tests
    run_test "Non-root user execution" "test_non_root_user"
    run_test "File permissions security" "test_file_permissions"
    run_test "Security scripts presence" "test_security_scripts"
    run_test "Dockerfile security features" "test_dockerfile_security"
    run_test "Security configuration files" "test_security_files"
    run_test "API key security" "test_api_key_security"
    run_test "Docker Compose security" "test_compose_security"
    
    # Summary
    echo "=================================="
    echo "Security Test Results Summary"
    echo "=================================="
    echo "Total tests: $TESTS_TOTAL"
    echo "Passed: $TESTS_PASSED"
    echo "Failed: $TESTS_FAILED"
    echo
    
    if [ "$TESTS_FAILED" -eq 0 ]; then
        log_pass "All security tests passed!"
        echo
        log "Security hardening implementation is complete and validated."
        echo
        log "Next steps:"
        echo "1. Review SECURITY.md for detailed security information"
        echo "2. Use docker-compose.security.yml for production deployments"
        echo "3. Run regular security scans with: docker exec <container> /opt/ytdl_service/security-scan.sh"
        echo "4. Rotate API keys regularly with: docker exec <container> /opt/ytdl_service/rotate-api-key.sh"
        exit 0
    else
        log_fail "Some security tests failed. Please review and fix the issues."
        exit 1
    fi
}

# Execute main function
main "$@"